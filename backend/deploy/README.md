# Бэкенд на VPS и автодеплой

Сервер: `46.225.138.70`, checkout: `/root/BimBomBam`, ветка: `master`.
Публикуются только Flask-бэкенд на `127.0.0.1:6767` и внутренняя PostgreSQL 16.
Nginx уже направляет `/fbroker/` на этот порт. Фронтенд не собирается и не запускается.

## Окружение и база

Настройки хранятся в `/root/BimBomBam/backend/.env` с правами `600`:

```dotenv
COMPOSE_PROJECT_NAME=bimbombam
FLASK_ENV=production
DATABASE_ENGINE=postgresql
PORT=6767
POSTGRES_DB=cqa
POSTGRES_USER=cqa
POSTGRES_PASSWORD=<случайный пароль, например openssl rand -hex 32>
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173
FREEDOM_API_URL=<подписанный URL из локального .env>
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=32768
OLLAMA_NUM_PREDICT=4096
```

В CORS указывается origin фронтенда: схема, домен и порт, без пути `/fbroker/`.
Адрес фронтенда на Vercel пока не определён. После публикации добавьте точный
`https://<project>.vercel.app` в этот список и выполните `deploy.sh --force`.
В Compose выбор PostgreSQL задан явно; `DATABASE_URL` для этого запуска не нужен.
PostgreSQL создаёт пользователя и базу из `POSTGRES_*` при первом запуске пустого тома.
Изменение пароля в `.env` не меняет пароль уже созданного пользователя БД.
Миграции и начальный официальный чек-лист применяются entrypoint при запуске бэкенда.
Локальная SQLite и её диалоги автоматически не переносятся.

Имя проекта **bimbombam** и том **bimbombam_postgres_data** закреплены для этого нового развёртывания.
Проект `backend` и `backend_postgres_data` на этом VPS принадлежат другому приложению.
Не используйте их и не меняйте имя действующего проекта.
Не выполняйте `docker compose down -v`: это удаляет базу.

Ollama не входит в этот деплой. Пока модель не настроена, смысловое оценивание вернёт 503;
CRUD, чек-листы, импорт и ручная работа доступны. Порт 11434 не требуется открывать в интернет.

## Автодеплой

`bimbombam-deploy.timer` раз в минуту запускает `bimbombam-deploy.service`.
Скрипт делает fetch и fast-forward `origin/master`. Доступ к GitHub использует существующие
credentials VPS; приватный SSH-ключ с компьютера на сервер или в GitHub не копируется.

Если с последнего успешного запуска в `backend/` нет изменений, контейнеры не пересоздаются.
Обновление checkout включает весь репозиторий, но сборка и запуск ограничены бэкендом.
Локальные изменения или разошедшаяся история останавливают деплой без reset/stash.
`flock` исключает одновременные ручные и автоматические запуски.

При обновлении скрипт сначала собирает образ, затем останавливает бэкенд, делает
`pg_dump -Fc` и проверяет чтение архива через `pg_restore --list`. После этого запускает
бэкенд с миграциями и ожидает успешного `/api/ready`. На время дампа и запуска будет
короткий перерыв в обслуживании. PostgreSQL не пересоздаётся и не обновляется автоматически.

Состояние и резервные копии находятся в `/root/BimBomBam/.deploy/` (вне Git и Docker-образа).
Успешная ревизия записана в `deployed-revision`. После ошибки тот же коммит автоматически
не повторяется: исправьте причину и запустите `--force`. Новый коммит допускает новую попытку.
Бэкапы не удаляются автоматически; контролируйте место и храните отдельную копию вне VPS.
Проверка структуры дампа не заменяет проверку восстановления.

Установка после настройки `.env` и проверки первого запуска:

```bash
cd /root/BimBomBam
bash backend/deploy/deploy.sh
install -m 644 backend/deploy/bimbombam-deploy.service /etc/systemd/system/
install -m 644 backend/deploy/bimbombam-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bimbombam-deploy.timer
```

После изменения файлов `.service`/`.timer` повторите их установку и `daemon-reload`.
Скрипт деплоя обновляется с репозиторием; новая логика используется со следующего запуска.

## Проверка и управление

```bash
systemctl list-timers bimbombam-deploy.timer
journalctl -u bimbombam-deploy.service -n 80 --no-pager
cd /root/BimBomBam/backend
docker compose -p bimbombam ps
curl -fsS http://127.0.0.1:6767/api/ready
docker compose -p bimbombam exec backend flask --app app:create_app db current
```

Изменения `.env` не отслеживаются Git. Применить их или повторить неуспешный деплой:

```bash
cd /root/BimBomBam
bash backend/deploy/deploy.sh --force
```

Остановить автоматические проверки: `systemctl disable --now bimbombam-deploy.timer`.
Это не останавливает уже работающие контейнеры или уже начавшийся деплой.

При сбое сначала проверьте журнал и `docker compose -p bimbombam logs --tail 100 backend`.
Предыдущий образ сохранён под тегом `bimbombam-backend:previous`; откат кода и восстановление
БД — отдельные операции. Не запускайте старый образ поверх несовместимой схемы.
Для обычного исправления отправьте исправленный коммит. При повреждении данных остановите
таймер и бэкенд, выберите проверенный дамп и подготовьте отдельное восстановление БД.

## Проверки скрипта

`bash backend/deploy/test-deploy.sh` выполняет изолированные проверки Git и порядка операций
с подставным Docker. Это не замена проверке контейнеров и PostgreSQL на VPS.

Механика: [Compose project name](https://docs.docker.com/compose/how-tos/project-name/),
[Compose up и ожидание healthcheck](https://docs.docker.com/reference/cli/docker/compose/up/).
