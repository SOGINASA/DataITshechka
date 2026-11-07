# Как выбирать материалы ECC

| Запрос | Главный материал | Поддержка по необходимости |
|---|---|---|
| Создать качественный web UI | `frontend-craft` этого комплекта | ECC `frontend-design-direction`, `make-interfaces-feel-better` |
| Проверить готовый интерфейс | `frontend-qa` этого комплекта | ECC `browser-qa`, `click-path-audit`, `e2e-testing` |
| Выделить/аудировать дизайн-токены | `design-system` | Сохранять текущий формат токенов |
| Компоненты и state React | `react-patterns` | `react-testing`; текущая документация проекта |
| Медленный React/Next.js | `react-performance` | `benchmark`, `benchmark-optimization-loop` после базового замера |
| Формы, диалоги, клавиатура | `frontend-a11y` | `accessibility` и реальные APG-паттерны |
| Анимация в Motion | `motion-foundations` → `motion-patterns` | `motion-advanced` только для сложных жестов/последовательностей |
| Vue/Nuxt/Angular | `vue-patterns` / `nuxt4-patterns` / `angular-developer` | `vite-patterns` по конфигурации |
| Локализация | `i18n-sync` | Проверка длинного текста и форматов |
| API, сервер, очереди, интеграции | `backend-engineering` этого комплекта | ECC `api-design`, `backend-patterns`, `contract-first`; framework-specific skill по стеку |
| Данные и миграции | Раздел data-and-migrations в `backend-engineering` | ECC `postgres-patterns`, `prisma-patterns`, `database-migrations` с проверкой engine/version |
| ML, обучение, оценка моделей, прогнозы | `ml-engineering` этого комплекта | ECC `mle-workflow`, `ml-adoption-playbook`, `pytorch-patterns`; замечания к примерам в ML-скилле |
| Безопасность фичи | `security-review` | Узкий framework-specific security skill |
| Проверка перед сдачей | `verification-loop` | Только команды и проверки, применимые к проекту |
| Разобраться в репозитории | `codebase-onboarding` | `change-impact`, `architecture-decision-records` |
| Поиск существующего решения | `search-first` | Начать с локального кода; внешние источники по задаче |
| Исследование/сравнение | `research-ops` / `market-research` | `competitive-platform-analysis` |
| Тексты и брендовый голос | `article-writing` / `brand-voice` | `content-engine` |
| Native mobile | `swiftui-patterns` / `react-native-patterns` / `dart-flutter-patterns` | Не навязывать web-паттерны |
| Видео | `video-editing` / `remotion-video-creation` | `taste*` относится прежде всего к видео, не к frontend |
| Автоматизация/команда агентов | Найти точный skill в каталоге | Сначала проверить полномочия и runtime, не включать фоновую работу автоматически |

Названия здесь относятся к локальной библиотеке. Открой файл `library/ecc/skills/ИМЯ/SKILL.md` из корня комплекта; не считай название доступной командой хоста.

У пользователя уже есть отдельные `ui-ux-pro-max`, `ui-styling`, `brand`, `design`, `design-system`, `banner-design`, `slides`. В этой сборке они не перезаписываются. Для web-качества стартуй с `frontend-craft`. Если существующий скилл полезен конкретной задачей, прочитай его текущую версию: установленный `ui-ux-pro-max` содержит участки, ориентированные на native mobile, а локальный `ckm:design-system` — в том числе на презентации. Нельзя автоматически переносить их платформенные ограничения на web.
