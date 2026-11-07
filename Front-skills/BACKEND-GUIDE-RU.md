# Backend-скилл для Codex и Claude Code

Отдельный [backend-engineering](skills/backend-engineering/SKILL.md) добавлен в комплект. Он помогает создавать и исправлять серверную часть: API, бизнес-логику, доступ к данным, миграции, фоновые задачи, webhooks и эксплуатацию.

## Как вызвать

- Codex: **`$backend-engineering`**.
- Claude Code: **`/backend-engineering`**.
- Обычным текстом: «Используй backend-engineering».

Скилл использует текущий стек проекта. Он не заставляет переносить приложение на Node.js, Python, микросервисы или Kubernetes. Если текущая сессия ещё не видит новый скилл, открой новую; запасной вариант — попросить прочитать SKILL.md по полному пути.

Примеры запросов:

> Используй backend-engineering. Добавь API заказов в текущий проект. Сохрани действующую авторизацию, проверь доступ по пользователю и организации, защитись от повторного создания заказа и протестируй реальные ответы API.

> Используй backend-engineering. Нужно изменить схему этой таблицы без потери данных. Изучи текущую базу и миграции, подготовь совместимое изменение, backfill и план восстановления. Проверь на изолированной базе.

> Используй backend-engineering. Webhook иногда приходит повторно и меняет баланс дважды. Воспроизведи проблему, исправь обработку повторов и проверь конкурентную доставку и перезапуск worker.

> Используй backend-engineering. Найди причину медленного endpoint: измерь запросы к базе, ожидание соединений и внешние вызовы, исправь установленную причину и сравни результат на том же сценарии.

## Что внутри

| Материал | Для чего |
|---|---|
| [API и контракты](skills/backend-engineering/references/api-contracts.md) | Поля, сериализация, ошибки, HTTP, пагинация и совместимость клиентов |
| [Данные и миграции](skills/backend-engineering/references/data-and-migrations.md) | Ограничения БД, гонки, транзакции, запросы, backfill и восстановление |
| [Безопасность](skills/backend-engineering/references/security-boundaries.md) | Доступ к объекту/организации, JWT, CSRF, входные данные и SSRF |
| [Очереди и интеграции](skills/backend-engineering/references/jobs-and-integrations.md) | Идемпотентность, retries, durable jobs, outbox и webhooks |
| [Эксплуатация](skills/backend-engineering/references/runtime-and-operations.md) | Производительность, pools, кэш, shutdown, probes и rollout |
| [Тестирование](skills/backend-engineering/references/testing-and-evidence.md) | Какие проверки действительно доказывают нужное поведение |
| [План изменения](skills/backend-engineering/assets/change-brief.md) | Кратко сформулировать контракт, инвариант и границы задачи |
| [План миграции](skills/backend-engineering/assets/migration-plan.md) | Порядок действий, совместимость, остановка и восстановление |
| [Отчёт о проверках](skills/backend-engineering/assets/verification-report.md) | Зафиксировать выполненные проверки, результат и ограничения |

Для одной небольшой правки агент читает нужный раздел, а не весь справочник. Для серверной части ML-продукта можно сочетать с `ml-engineering`, для пользовательского интерфейса — с `frontend-craft` и `frontend-qa`, разделяя конкретные задачи.

## Источники и проверка

Полностью изучены четыре entrypoint ECC: backend-patterns, api-design, database-migrations и contract-first. Из security-review и deployment-patterns взяты подходящие разделы. Проверены 15 первичных страниц: RFC, OpenAPI, OWASP, PostgreSQL, Prisma, AWS, Stripe и Kubernetes. [Ссылки и исправления исходных примеров](skills/backend-engineering/references/sources.md).

При сборке проверяются структура, ссылки, метаданные и установка комплекта. Качество будущего backend нужно проверять на его реальных API/БД/интеграциях; такие проверки не заменены шаблонным сканером. [Сценарии для последующей оценки скилла](tests/backend-scenarios.md).

## Подключение и перенос

Установщик комплекта: `python3 scripts/manage_skills.py install --apply`. Он подключает пять собственных скиллов к Codex и Claude Code; существующие чужие файлы не перезаписывает. Проверка: `python3 scripts/manage_skills.py status`.

Для отдельного переноса скопируй всю папку `skills/backend-engineering` в `~/.agents/skills/backend-engineering` для Codex или `~/.claude/skills/backend-engineering` для Claude Code. Сохраняй references, assets и agents вместе. Перед заменой одноимённого скилла проверь его содержимое. Полная библиотека ECC для основной работы этого скилла не обязательна.
