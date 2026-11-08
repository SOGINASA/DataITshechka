# Публичный API с Qwen для проверки судьями

Инструкция публикует **только API** BimBomBam на компьютере B. Судья обращается к HTTPS-адресу; Flask и Ollama остаются на localhost, frontend пока не нужен. Примеры рассчитаны на отдельный Ubuntu/Debian сервер. Для постоянно доступной проверки лучше использовать VPS, а не личный ноутбук: компьютер должен быть включён, не спать и иметь стабильный интернет.

## Важно перед публикацией

Текущий API прототипа не имеет встроенной авторизации: через него можно не только читать оценки, но и создавать/импортировать диалоги, запускать оценки и подавать апелляции. Поэтому не открывай Flask `:6767`, Ollama `:11434` или PostgreSQL в интернет.

Ниже HTTPS-вход делает Caddy, а HTTP Basic Auth просит логин и пароль на каждом API-запросе. Передай эти данные судьям отдельно. Если проверяющая система не умеет присылать учётные данные, остановись перед публикацией и согласуй с организаторами IP-адреса для firewall allowlist либо добавь согласованную авторизацию в API. Оставлять этот прототип без защиты в публичном интернете нельзя.

## Схема подключения

```text
Судья ── HTTPS + логин/пароль ──> домен ──> Caddy :443
                                          └──> Flask/Gunicorn 127.0.0.1:6767
                                                    └──> Ollama 127.0.0.1:11434
```

Домен должен указывать A-записью на публичный IP компьютера B. Тогда судья подключается к приложению, размещённому на этом публичном IP, по адресу вроде `https://cqa.example.org/api`. Для этого туториала используй домен, указывающий на публичный IP: судьи всё равно подключаются к компьютеру B, но HTTPS будет проверяться нормально. Caddy по умолчанию выдаёт для IP локальный сертификат, которому внешние клиенты не доверяют. Сертификаты Let’s Encrypt для IP теперь существуют, но короткоживущие (160 часов) и требуют автоматического обновления; здесь этот путь не настраиваем. Не отправляй логин/пароль через обычный `http://<ip>`.

## 1. Проверить доступность компьютера B из интернета

На B проверь публичный IPv4 в настройках роутера и сравни его с внешним адресом, например на `https://ifconfig.me`. Если адрес роутера отличается, либо WAN-адрес входит в диапазон CGNAT (`100.64.0.0/10`), входящий порт-форвардинг обычно не сработает. Тогда используй VPS с публичным IP или попроси провайдера выдать публичный адрес.

Для домашнего компьютера:

1. Закрепи за B постоянный локальный адрес в роутере.
2. Создай DNS A-запись своего домена на публичный IP B.
3. Перенаправь на B только TCP-порты **80 и 443**.
4. Не перенаправляй порты `6767`, `11434`, `5432`.

Если публичный IP меняется, настрой DDNS для DNS-записи. Если домена нет, судьи могут подключаться по числовому IP только при отдельно настроенном доверенном TLS сертификате; сам Caddy для IP обычно выдаёт локальный сертификат, которому внешние клиенты не доверяют. Поэтому домен — самый простой рабочий вариант.

## 2. Установить приложение и Qwen

На B установи Git, Python 3.11+, Ollama и Caddy. Для Qwen нужен запас памяти; модель `qwen3:4b` весит около 2,5 ГБ плюс память на контекст.

```bash
git clone <URL-репозитория>
cd BimBomBam
ollama pull qwen3:4b
ollama list
```

Если Ollama ещё не работает как сервис:

```bash
ollama serve
```

Оставь службу Ollama включённой после перезагрузки. Проверь, что она отвечает только локально:

```bash
curl -fsS http://127.0.0.1:11434/api/version
```

## 3. Подготовить Flask API

Создай локальное окружение. Не коммить `backend/.env`:

```bash
cd BimBomBam/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
```

Открой `backend/.env` и задай:

```dotenv
FLASK_ENV=production
DATABASE_ENGINE=sqlite
PORT=6767
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT=300
OLLAMA_NUM_CTX=24576
OLLAMA_NUM_PREDICT=4096
OLLAMA_NUM_CTX_CALL=40960
OLLAMA_NUM_PREDICT_CALL=3072
OLLAMA_THINK=false
```

Подготовь схему БД и официальный чек-лист:

```bash
.venv/bin/flask --app app:create_app db upgrade
.venv/bin/flask --app app:create_app seed-checklist
```

Запусти Gunicorn только на loopback:

```bash
.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:6767 --timeout 360 'app:create_app()'
```

Оставь процесс в foreground на первом запуске. В другом терминале проверь:

```bash
curl -fsS http://127.0.0.1:6767/api/health
curl -fsS http://127.0.0.1:6767/api/ready
curl -fsS http://127.0.0.1:6767/api/openapi.json -o /tmp/cqa-openapi.json
```

`/api/ready` должен вернуть `{"status":"ready"}`. Сам по себе этот статус проверяет базу, не модель; готовность Qwen проверь локальным запросом из следующего раздела после запуска оценки.

## 4. Настроить Caddy как единственную публичную точку входа

Установи Caddy по [официальной инструкции](https://caddyserver.com/docs/install). Он автоматизирует HTTPS для домена с правильной DNS-записью и доступными снаружи портами 80/443. Создай пароль судей и сгенерируй его хеш:

```bash
caddy hash-password
```

Сохрани выданный хеш. Не записывай открытый пароль в Caddyfile. Создай `/etc/caddy/Caddyfile`, заменив домен и хеш:

```caddyfile
cqa.example.org {
    basic_auth {
        judge $2a$14$ВСТАВЬ_СЮДА_ХЕШ_ИЗ_caddy_hash-password
    }

    handle /api/* {
        reverse_proxy 127.0.0.1:6767
    }

    handle {
        respond "API only" 404
    }
}
```

Caddy сам получит и будет обновлять публичный TLS-сертификат, если DNS домена уже указывает на B и порты 80/443 доступны снаружи. Проверь конфигурацию и перезапусти службу:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Если reload не сработал, посмотри `sudo journalctl -u caddy -n 100 --no-pager`.

В firewall оставь только SSH для администрирования и веб-порты Caddy. Например, на Ubuntu с UFW сначала разреши SSH, чтобы не потерять подключение:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Проверь в правилах роутера и firewall, что `6767`, `11434` и `5432` не опубликованы.

### Если судейский клиент не поддерживает логин и пароль

Используй этот вариант только если организаторы заранее дали фиксированные публичные IP судей. Удали `basic_auth` из Caddyfile и вместо него ограничь запросы:

```caddyfile
cqa.example.org {
    @not_judges not remote_ip 198.51.100.10/32 198.51.100.11/32
    respond @not_judges 403

    handle /api/* {
        reverse_proxy 127.0.0.1:6767
    }

    handle {
        respond "API only" 404
    }
}
```

Замени тестовые адреса примера на IP, которые предоставили судьи. Ограничь теми же адресами входящий TCP `443` в firewall; порт `80` оставь доступным Caddy для перенаправления на HTTPS и проверки сертификата. Caddy matcher `remote_ip` проверяет адрес TCP-клиента. Если запросы идут через CDN или другой proxy, сначала отдельно настрой доверенные proxy ranges; иначе matcher увидит адрес proxy. Если у судей нет ни поддерживаемой авторизации, ни фиксированных IP, безопасно публиковать этот API для их тестов в текущем виде нельзя.

## 5. Проверить публичный API

С внешней сети, не с самого сервера:

```bash
curl -i -u judge:'ПАРОЛЬ' https://cqa.example.org/api/health
curl -i -u judge:'ПАРОЛЬ' https://cqa.example.org/api/ready
curl -u judge:'ПАРОЛЬ' https://cqa.example.org/api/openapi.json
```

Проверка без пароля должна вернуть `401`, с верным паролем health должен вернуть `200`. Адрес для передачи судьям:

```text
https://cqa.example.org/api
```

Передай логин/пароль отдельно от публичного адреса. Не клади пароль в Git, URL, frontend или query string.

## 6. Проверить оценку через API

Судьям понадобятся диалог и ID чек-листа. Получить чек-листы:

```bash
curl -fsS -u judge:'ПАРОЛЬ' https://cqa.example.org/api/checklists
```

Импортировать тестовый диалог можно через `POST /api/conversations/import`. Затем взять его `id` и ID чек-листа из ответов и отправить:

```bash
curl -X POST -u judge:'ПАРОЛЬ' \
  -H 'Content-Type: application/json' \
  -d '{"checklist_id":"ID_ЧЕК_ЛИСТА","engine":"ollama"}' \
  https://cqa.example.org/api/conversations/ID_ДИАЛОГА/evaluations
```

Оценка синхронная и может выполняться несколько минут. Ответ `503` обычно означает, что Ollama или указанная модель не готовы; `422` может означать слишком большой диалог или некорректный ввод. Полные схемы запросов и ответов находятся в `/api/openapi.json`.

## 7. Что сообщить судьям

- Base URL: `https://cqa.example.org/api`.
- Схема запросов: `https://cqa.example.org/api/openapi.json`.
- Учётные данные Basic Auth передать отдельным защищённым каналом.
- Модель: `qwen3:4b` через локальную Ollama.
- API пока синхронный; модель и компьютер должны быть доступны в течение всего тестирования.

Перед тестом с судьями проверь доступность из мобильной сети или другой внешней сети. `localhost` и локальный адрес вроде `192.168.x.x` извне не работают. Если компьютер выключится, уснёт, потеряет интернет или изменится IP без обновления DNS, API станет недоступен.

## Когда API будет готов, а веб появится позже

Этот этап проксирует только `/api/*`; frontend здесь намеренно не публикуется. Когда понадобится веб, добавь отдельный маршрут Caddy на frontend и пересобери frontend с HTTPS API URL. Не открывай напрямую порт frontend dev-сервера.

Официальные инструкции: [Caddy Basic Auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth), [matcher IP-адресов Caddy](https://caddyserver.com/docs/caddyfile/matchers), [автоматический HTTPS в Caddy](https://caddyserver.com/docs/automatic-https), [Flask deployment](https://flask.palletsprojects.com/en/stable/deploying/), [короткоживущие IP-сертификаты Let’s Encrypt](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability).

Сведения о рабочем Qwen baseline и его ограничениях: [локальный запуск Qwen](QWEN_FALLBACK_REMOTE_SETUP_RU.md), [отчёт baseline](ML_BASELINE_RESULTS_RU.md).
