# Источники frontend-агентов — 30 октября 2026

## Основа комплекта

- [frontend-craft](../skills/frontend-craft/SKILL.md): реальный проект, типографика, композиция, состояния, responsive и 63 изображения Forte.
- [frontend-qa](../skills/frontend-qa/SKILL.md): просмотр отрисованного UI, реальные действия, клавиатура, доказательства и границы проверки.
- [ecc-library](../skills/ecc-library/SKILL.md): ограниченный выбор нужных entrypoints, без неявной установки tools/hooks.

## ECC: просмотренные агенты

Зафиксированный commit: `25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b`. [Репозиторий](https://github.com/affaan-m/ECC), [лицензия MIT / Copyright 2026 Affaan Mustafa](../library/ecc/LICENSE). Оригинальные файлы сохранены без изменений.

| Источник | Глубина | Что использовано |
|---|---|---|
| [react-reviewer](../library/ecc/agents/react-reviewer.md) | Весь файл | Hook/state/identity review, server/client границы, review-only scope |
| [code-reviewer](../library/ecc/agents/code-reviewer.md) | Разделы Review Process, Confidence-Based Filtering, Pre-Report Gate, Common False Positives | Конкретный trigger, контекст вызовов, доказательства, отсутствие выдуманных замечаний |
| [e2e-runner](../library/ecc/agents/e2e-runner.md) | Весь файл | Пользовательские сценарии, локаторы, ожидания, screenshots/traces |
| [a11y-architect](../library/ecc/agents/a11y-architect.md) | Весь файл | Семантика, keyboard/focus, labels и отдельная проверка доступности |
| [performance-optimizer](../library/ecc/agents/performance-optimizer.md) | Analysis Commands, Indicators, Algorithmic Analysis, React Performance, начало Bundle Analysis | Профилирование, нагрузка, bundle/network/render; измерения до и после |

Это пять просмотренных agent-файлов, а не аудит всех 71 агентов ECC. Глубина изучения 311 скиллов по-прежнему указана отдельно в основном каталоге.

## Что переработано

Новые роли написаны для этого комплекта и текущих клиентов. Не скопированы upstream `model: sonnet`, обязательный вызов для каждой TSX-правки, blanket memoization, фиксированные file-length/bundle-size пороги, обязательная установка agent-browser и автоматическая отправка артефактов. Ревью не прекращается только из-за красного CI; ограничения указываются отдельно.

E2E использует доступные инструменты и существующие команды проекта. Первичны role/name/label, затем stable test IDs; ожидания основаны на конкретном состоянии. Flaky test не скрывается через skip, а диагностируется. Review-агент предлагает regression test, builder добавляет его при необходимости.

Для accessibility не перенесены неточные ссылки/смешение размеров target и focus из upstream. Применяется уже проверенный [review-guide](../skills/frontend-qa/references/review-guide.md), который различает WCAG AA 24 CSS px с исключениями и ориентир 44 px, а также не выдаёт axe за полный аудит.

Производительность требует сопоставимых условий, baseline и измерений; лабораторные данные не подменяют полевые. Не скопированы совет lazy-load для LCP-изображения, старые TTI-пороги или useCallback для каждого обработчика. При отсутствии инструмента вывод остаётся гипотезой.

## Первичные источники форматов

- [OpenAI: Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): personal standalone TOML в `.codex/agents`, обязательные поля и наследование возможностей.
- [Anthropic: Custom subagents](https://code.claude.com/docs/en/sub-agents): YAML/Markdown в `.claude/agents`, preload skills, inherit model, disallowedTools и обнаружение файлов.

Проверено 30.10.2026. Код клиента локально: `codex-cli 0.159.0`. Claude CLI не найден. Разрешения, модель и MCP основного клиента не переопределяются. Источники описывают формат; локальные испытания и их ограничения зафиксированы отдельно в validation.
