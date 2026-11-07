# GitHub Actions: деплой только бэкенда

Workflow: [Backend CI and Deploy](https://github.com/SOGINASA/BimBomBam/actions/workflows/backend-deploy.yml).
Файл: [backend-deploy.yml](../../.github/workflows/backend-deploy.yml).

Push в `master` с изменениями в `backend/` или workflow запускает:

1. Тесты Python и проверки скрипта деплоя на GitHub-hosted runner.
2. Сборку Docker-образа с тегом и меткой точного SHA коммита.
3. Запуск этого образа с отдельной PostgreSQL на runner: миграции, seed и `/api/ready`.
4. Передачу готового образа и скрипта по SSH на VPS.
5. Резервную копию БД, запуск образа и проверку готовности на VPS и через HTTPS.

Pull request запускает проверки и сборку без доступа к SSH-секретам и без деплоя.
Ручной запуск доступен через **Actions → Backend CI and Deploy → Run workflow** на ветке `master`.
Изменения только фронтенда не запускают workflow. Сборка фронтенда отсутствует.

VPS больше не опрашивает GitHub по таймеру и не собирает образ. Сервер выполняет
загрузку образа, резервное копирование, миграции и запуск. Импорт образа и эти операции
всё ещё требуют CPU/диска на VPS. Конкурентные деплои ограничены Actions и `flock`.
Старая версия не может перезаписать более новый checkout.

## Доступ и расположение

- VPS: `46.225.138.70`, checkout: `/root/BimBomBam`, ветка: `master`.
- Порт: `127.0.0.1:6767`, URL API: `https://foodtrack.beast-inside.kz/fbroker/api`.
- Compose-проект: **bimbombam**, том PostgreSQL: **bimbombam_postgres_data**.
- `.env`: `/root/BimBomBam/backend/.env`, права `600`; Actions его не заменяет.
- Бэкапы и состояние: `/root/BimBomBam/.deploy/`, вне Git и Docker-образа.

Проект `backend` и том `backend_postgres_data` принадлежат другому приложению.
Не переименовывайте действующий проект и не выполняйте `down -v` на VPS.
Удаление томов в workflow относится только к изолированной БД GitHub runner.

В GitHub Repository Secrets используются:

| Secret | Значение |
|---|---|
| `BIMBOMBAM_VPS_HOST` | Адрес VPS |
| `BIMBOMBAM_VPS_USER` | SSH-пользователь |
| `BIMBOMBAM_SSH_KEY` | Отдельный приватный ключ только для Actions |
| `BIMBOMBAM_KNOWN_HOSTS` | Проверенный публичный SSH host key VPS |

Приватный ключ FoodTrack не используется в Actions. SSH проверяет host key;
при смене сервера обновите `KNOWN_HOSTS` после проверки нового ключа.
Существующие GitHub-credentials на VPS нужны только для fetch точной версии при деплое.

## Окружение

```dotenv
COMPOSE_PROJECT_NAME=bimbombam
FLASK_ENV=production
DATABASE_ENGINE=postgresql
PORT=6767
POSTGRES_DB=cqa
POSTGRES_USER=cqa
POSTGRES_PASSWORD=<случайный пароль>
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173
FREEDOM_API_URL=<подписанный URL>
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=32768
OLLAMA_NUM_PREDICT=4096
```

PostgreSQL создаёт базу и пользователя при первом запуске пустого тома. Изменение
`POSTGRES_PASSWORD` в `.env` не меняет пароль уже существующего пользователя БД.
Миграции и официальный чек-лист применяются entrypoint. SQLite автоматически не переносится.
Ollama в этот деплой не входит; без модели смысловое оценивание возвращает 503.

Адрес фронтенда на Vercel пока неизвестен. После публикации добавьте точный origin
`https://<project>.vercel.app` в `CORS_ORIGINS` и примените `.env`:

```bash
cd /root/BimBomBam/backend
docker compose -p bimbombam -f docker-compose.yml -f compose.production.yml \
  up -d --no-deps --no-build --force-recreate --wait backend
```

## Проверка и восстановление

```bash
cd /root/BimBomBam/backend
docker compose -p bimbombam -f docker-compose.yml -f compose.production.yml ps
curl -fsS http://127.0.0.1:6767/api/ready
docker compose -p bimbombam -f docker-compose.yml -f compose.production.yml logs --tail 100 backend
cat /root/BimBomBam/.deploy/deployed-revision
```

Логи деплоя находятся во вкладке Actions. После ошибки исправьте причину и используйте
**Re-run failed jobs** либо отправьте исправленный коммит. Локальные изменения на VPS
останавливают деплой без reset/stash. Никакого фонового повторения не происходит.

Перед миграциями бэкенд останавливается, выполняются `pg_dump -Fc` и `pg_restore --list`;
на время этих операций есть короткий перерыв в обслуживании. После успешного запуска
образ получает тег `bimbombam-backend:current`, предыдущий — `bimbombam-backend:previous`.
Бэкапы не удаляются автоматически. Не откатывайте код поверх несовместимой схемы;
восстановление БД выполняется отдельно. Историческая проверка восстановления — [VERIFICATION.md](VERIFICATION.md).

При переходе на Actions прежний `bimbombam-deploy.timer` отключается. Его файлы
удалены из репозитория. Проверка: `systemctl is-enabled bimbombam-deploy.timer` должна
возвращать `disabled` или `not-found`.
