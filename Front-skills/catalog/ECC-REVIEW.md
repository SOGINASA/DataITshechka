# Разбор ECC и решения сборки

Просмотрены метаданные всех 311 канонических скиллов; структура сохранена полностью. Полностью прочитаны 19 entrypoint-файлов: accessibility, api-design, backend-patterns, browser-qa, contract-first, database-migrations, design-system, frontend-a11y, frontend-design-direction, inherit-legacy-style, make-interfaces-feel-better, ml-adoption-playbook, mle-workflow, pytorch-patterns, react-patterns, react-performance, react-testing, skill-host-compat, verification-loop. В 8 материалах изучены выбранные разделы: coding-standards, deployment-patterns, e2e-testing, frontend-patterns, motion-foundations, motion-patterns, search-first, security-review. Исполняемые скрипты upstream и все вложенные ссылки не проходили полный аудит; реальные приложения этими скиллами не прогонялись.

## Что отобрано для frontend

- `frontend-design-direction`: связь визуального решения с задачей, типом продукта, состояниями и rendered evidence.
- `make-interfaces-feel-better`: радиусы, оптическое выравнивание, tabular numbers, переходы и hit areas.
- `design-system`: извлечение токенов и поиск визуальной несогласованности.
- `frontend-a11y`, `accessibility`: семантика, focus, labels и проверка доступности.
- `react-patterns`, `react-performance`, `react-testing`: компоненты/state, измеряемая производительность, поведенческие тесты.
- `browser-qa`, `e2e-testing`, `verification-loop`: реальные сценарии, screenshots, проверки проекта.
- `motion-*`: дополнительный материал для подходящего React/Motion стека.

## Что требует осторожной адаптации

Найдены учебные, неполные или устаревшие примеры и чрезмерно универсальные требования. Конкретные замечания и официальные исправления находятся в [compatibility.md](../skills/ecc-library/references/compatibility.md). Поэтому исходные 311 скиллов лежат в библиотеке, а глобально обнаруживаются пять коротких совместимых entrypoint-скиллов.

`frontend-craft` переводит пользовательские изображения в проверяемые проектные решения; `frontend-qa` отделяет визуальную проверку от компиляции; `ecc-library` выбирает нужную часть ECC, сохраняя исходные пути и зависимости.

Отдельные семейства требуют своего контекста: `taste*` — видео; native mobile — платформенных правил; ops/outreach — соответствующего аккаунта и авторизации; hooks/loops/memory — runtime-настройки. Они сохранены, но сам факт наличия каталога их не запускает.

## Отдельный ML-скилл

Полностью изучены mle-workflow, ml-adoption-playbook и pytorch-patterns. На их основе создан ml-engineering; дополнительно исследованы официальные скиллы Hugging Face и первичная документация scikit-learn, PyTorch и Google. Исправлены упрощения в выборе устройства, воспроизводимости, усреднении loss, checkpointing и promotion gates. Подробности: [ML sources](../skills/ml-engineering/references/sources.md). Сам upstream сохранён без изменений.

## Отдельный backend-скилл

backend-engineering опирается на четыре полностью прочитанных entrypoint и выбранные разделы security-review/deployment-patterns. Ключевые решения сверены с 15 первичными страницами документации. Исправлены опасные упрощения в миграциях, retries, очередях, health checks и авторизации. [Источники и детали](../skills/backend-engineering/references/sources.md). Универсального статического сканера, обещающего доказать корректность любого backend, в сборке нет: проверки выполняются средствами целевого проекта.

## Границы проверки

Статическая инвентаризация, целевой разбор и тесты наших локальных helpers повышают проверяемость комплекта. Они не доказывают качество всех 311 workflows, безопасность всех upstream scripts или то, что любой агент обязательно выдаст хороший дизайн. Финальную UI-работу всё равно нужно реально отрендерить и проверить.
