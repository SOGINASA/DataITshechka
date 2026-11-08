# Действующая связка: Mac Qwen → ngrok → VPS

Настроено 8 ноября 2026 года для ITshechka.

Схема запроса:

```text
Клиент / судьи
  → https://foodtrack.beast-inside.kz/fbroker/api
  → backend BimBomBam на VPS 46.225.138.70
  → HTTPS ngrok
  → Ollama на Mac, 127.0.0.1:11434
  → qwen3:8b
```

Адрес модели в текущем запуске: `https://586a-85-159-27-203.ngrok-free.app`.
Это адрес только для VPS. Судьям нужен публичный API приложения выше, а не ngrok модели.

## Что работает

- Существующая локальная `qwen3:8b`, без загрузки другой модели.
- Контекст 32768, ответ до 2048 токенов, thinking=false, таймаут backend 300 секунд; те же параметры для звонков.
- Локальная Ollama использует flash attention, KV cache q8_0 и одну параллельную генерацию.
- Ngrok разрешает только адреса VPS: IPv4 `46.225.138.70` и IPv6 `2a01:4f8:1c1a:a433::1`.
- Через туннель доступны только `/api/chat`, `/api/tags`, `/api/version`. Управление моделями закрыто.
- Host при передаче в Ollama заменяется на `127.0.0.1:11434`: сама Ollama отклоняет внешний Host с 403.
- Инспекция содержимого запросов ngrok отключена.
- Ngrok запущен как пользовательский LaunchAgent, с перезапуском процесса при сбое. `caffeinate -i` предотвращает обычный автоматический сон, пока работает туннель.
- На VPS изменена только конфигурация backend BimBomBam. База, образ приложения, nginx и остальные проекты не заменялись.

Правила доступа реализованы обычным условием `deny` в [Traffic Policy](https://ngrok.com/docs/gateway/traffic-policy/variables/connection). Отдельное платное действие `restrict-ips` не используется.

## Файлы конфигурации

На Mac:

- `~/Library/Application Support/ngrok/ngrok.yml` — секретный authtoken, права 600; не копировать в репозиторий.
- `~/Library/Application Support/BimBomBam/ngrok-policy.yml` — правила доступа и Host.
- `~/Library/Application Support/BimBomBam/ngrok.log` — журнал соединения.
- `~/Library/LaunchAgents/kz.itshechka.bimbombam.ngrok.plist` — запуск ngrok.

На VPS:

- `/root/BimBomBam/backend/compose.mac-qwen.yml` — адрес туннеля и параметры модели.
- `/root/bimbombam-backups/mac-qwen-20261108/` — снимок прежнего контейнера и конфигурация отката, доступ только root.

## Проверить

На Mac:

```sh
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:4040/api/tunnels
launchctl list kz.itshechka.bimbombam.ngrok
```

На любом компьютере:

```sh
curl -fsS https://foodtrack.beast-inside.kz/fbroker/api/health
```

На VPS:

```sh
cd /root/BimBomBam/backend
docker exec bimbombam-backend-1 python -c 'import os,urllib.request; print(urllib.request.urlopen(os.environ["OLLAMA_BASE_URL"]+"/api/tags",timeout=15).status)'
```

Это проверяет соединение из контейнера. Полная оценка делается обычным `POST /api/conversations/{id}/evaluations` с `checklist_id` и `engine: "auto"` или `"ollama"`.

## Если туннель перезапустился

На текущем бесплатном аккаунте ngrok адрес назначается динамически. После нового запуска процесса проверь URL в `http://127.0.0.1:4040/api/tunnels`. LaunchAgent перезапускает ngrok, но **не обновляет адрес на VPS автоматически**.

Если URL изменился, замени только `OLLAMA_BASE_URL` в `/root/BimBomBam/backend/compose.mac-qwen.yml`, затем на VPS:

```sh
cd /root/BimBomBam/backend
docker compose -p bimbombam \
  -f docker-compose.yml -f compose.production.yml -f compose.mac-qwen.yml \
  up -d --no-deps --no-build backend
```

При дальнейших деплоях нужно сохранять третий файл `-f compose.mac-qwen.yml`, иначе подключение к Mac будет заменено настройками основного compose.

Mac должен оставаться включённым, с работающей Ollama и интернетом. Закрытие крышки или принудительный сон могут оборвать связь; `caffeinate -i` этого не отменяет. После полного перезапуска Mac также потребуется запустить Ollama с прежними параметрами:

```sh
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NO_CLOUD=1 \
ollama serve
```

Не запускай второй `ollama serve`, если порт 11434 уже занят работающим экземпляром.

## Откат VPS на прежнюю конфигурацию

```sh
cd /root/BimBomBam/backend
docker compose -p bimbombam \
  -f docker-compose.yml -f compose.production.yml \
  -f /root/bimbombam-backups/mac-qwen-20261108/rollback.json \
  up -d --no-deps --no-build --pull never backend
```

Старый SSH-туннель и связанные с ним systemd units сохранены. Не публикуй содержимое каталога резервной копии: там могут быть секреты среды приложения.

## Проверка полного пути

Локальные доказательства проверки находятся в `data/runs/mac-vps-ngrok-20261108/` (не входят в Git): вход технического диалога, ответ публичного API, сохранённая оценка и `smoke-summary.json` с фактической длительностью. Этот тест не относится к DEV или PROD и не является замером точности модели.

Проверка выполнена: HTTP 201 через публичный HTTPS API, `engine=ollama:qwen3:8b`, 8 критериев без неоценённых пунктов, 77.58 секунды. Оценка `28bf3502-4feb-4aec-afa9-90611749fa63` сохранена на VPS и повторно прочитана через API. Итог 100 относится только к техническому диалогу, а не к точности модели.
