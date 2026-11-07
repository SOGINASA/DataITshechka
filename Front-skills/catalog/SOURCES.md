# Происхождение

Собрано 30 октября 2026, Asia/Almaty.

## ECC

- Репозиторий: https://github.com/affaan-m/ECC
- Commit: `25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b`
- Дата commit: 2026-10-26T00:03:57-04:00
- Локально: [полный исходный снимок](../library/ecc/README.md), включая 311 канонических скиллов, 71 agent, 97 command-файлов и 122 Markdown-файла правил.
- Снимок создан `git archive HEAD`; `.git` и история не включены. Исходные файлы не редактировались.
- Лицензия: [MIT, Copyright 2026 Affaan Mustafa](../library/ecc/LICENSE). Внутренние атрибуции дополнительных источников сохранены.
- Runtime, hooks, зависимости и внешние сервисы ECC не установлены этой сборкой. Проверка содержимого описана в [ECC-REVIEW.md](ECC-REVIEW.md).

## Forte

- Источник: `/Users/artempinigin/Forte/frontend/design rules`.
- 63 оригинальных изображения скопированы побайтово. SHA-256, исходные имена, размеры и ID: [manifest](../skills/frontend-craft/references/reference-manifest.json).
- Визуальный разбор всех изображений использован для новых правил; галерея и контактные листы помогают просматривать коллекцию.
- На изображениях присутствует атрибуция Dr Studio / @drstudiooo. Это личная референсная коллекция пользователя; она не получает MIT-лицензию ECC. Файлы шрифтов не включены. Не переносить изображения/логотипы в публичный продукт без соответствующих прав.

## Документация для совместимости и точечных исправлений

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code: Skills](https://code.claude.com/docs/en/skills)
- [W3C: Contrast Minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- [W3C: Target Size Minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [Next.js: use server](https://nextjs.org/docs/app/api-reference/directives/use-server)
- [React: Activity](https://react.dev/reference/react/Activity)

Новые файлы `skills/frontend-craft`, `skills/frontend-qa`, `skills/ecc-library`, каталог, скрипты управления и руководство созданы для этого комплекта. Они не являются официальной сборкой ECC или OpenAI/Anthropic.

## ML extension — 2026-10-30

Добавлен самостоятельный ml-engineering. [Источники, версии и границы разбора](../skills/ml-engineering/references/sources.md): три полных entrypoint ECC, два официальных Hugging Face skill entrypoint (TRL и sentence-transformers, второй — выбранные разделы), девять первичных страниц документации. Новые внешние runtime-компоненты не установлены; ECC snapshot не изменён.

## Backend extension — 2026-10-30

Добавлен самостоятельный backend-engineering. [Источники и решения](../skills/backend-engineering/references/sources.md): четыре полностью изученных entrypoint ECC, выбранные разделы двух других, 15 первичных страниц RFC/OpenAPI/OWASP/PostgreSQL/Prisma/AWS/Stripe/Kubernetes. Upstream snapshot не изменён.

## Frontend agents extension — 2026-10-30

Добавлены шесть оригинальных frontend-ролей, общий скилл frontend-team, два native-адаптера на роль и безопасный установщик. [Источники и изменения](FRONTEND-AGENTS-SOURCES.md): три agent-файла ECC полностью, два — выбранные разделы, официальные форматы Codex/Claude. Upstream snapshot сохранён.
