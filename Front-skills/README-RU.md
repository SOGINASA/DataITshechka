# Frontend, Backend & ML Skills Kit

Личный комплект для **Codex и Claude Code**: качественный frontend по референсам Forte, отдельные backend- и ML-скиллы и полный локальный справочник ECC. Собран 30 октября 2026. При сборке шесть рабочих скиллов подключены к обоим агентам; на рабочем столе создан ярлык `Frontend-Skills-Kit`.

## Начать пользоваться

Шесть скиллов подключаются к обоим агентам из одной папки. Для новых сессий:

| Задача | Codex | Claude Code |
|---|---|---|
| Команда frontend-агентов: реализация и проверки | `$frontend-team` | `/frontend-team` |
| Нарисовать и реализовать интерфейс | `$frontend-craft` | `/frontend-craft` |
| Проверить готовый интерфейс | `$frontend-qa` | `/frontend-qa` |
| Найти и применить нужный скилл ECC | `$ecc-library` | `/ecc-library` |
| API, сервер, базы данных, очереди и интеграции | `$backend-engineering` | `/backend-engineering` |
| Построить, обучить или проверить ML-модель | `$ml-engineering` | `/ml-engineering` |

Примеры запросов:

> Используй frontend-craft. Переделай страницу аналитики в этом проекте: нужна чёткая иерархия, аккуратная типографика и нормальная мобильная версия. Сохрани действующие данные и функции. После реализации проверь экран и основной сценарий в браузере.

> Используй frontend-qa. Проверь этот интерфейс на телефоне и десктопе, пройди форму и ошибки. Укажи конкретные дефекты с доказательствами.

> Используй ecc-library. Подбери из локальной библиотеки скиллы для React, тестирования и производительности, затем примени нужные к текущей задаче.

> Используй ml-engineering. Изучи данные и текущий код, проверь разбиение на выборки, сделай baseline и сравни модель с ним. Сохрани команды, метрики, ограничения и следующий обоснованный эксперимент.

> Используй backend-engineering. Реализуй серверную часть этой функции в текущем стеке: проверь контракт, права доступа, изменения данных и поведение при повторных запросах. Выполни подходящие тесты и покажи результат.

Если скилл не виден в текущем чате, начни новую сессию или перезапусти приложение. Самый надёжный запасной способ — передать полный путь к `SKILL.md` и попросить прочитать его. Установка на диске сама по себе не доказывает, что уже открытая сессия обновила список скиллов.

## Что внутри

- [Frontend-команда из шести агентов](FRONTEND-AGENTS-GUIDE-RU.md): дизайн, реализация, ревью кода, browser QA, доступность и производительность; общий скилл [frontend-team](skills/frontend-team/SKILL.md).

- [frontend-craft](skills/frontend-craft/SKILL.md): направление дизайна, композиция, типографика, палитры, responsive, состояния и доводка.
- [frontend-qa](skills/frontend-qa/SKILL.md): реальные screenshots, клавиатура, контраст, сценарии, проверки проекта и честная фиксация непроверенного.
- [backend-engineering](skills/backend-engineering/SKILL.md): API, бизнес-логика, доступ к данным, миграции, безопасность, queues/webhooks, тестирование и эксплуатация; [русская инструкция](BACKEND-GUIDE-RU.md).
- [ml-engineering](skills/ml-engineering/SKILL.md): данные, baseline, эксперименты, оценка, PyTorch, прогнозирование, retrieval/LLM и внедрение; [русская инструкция](ML-GUIDE-RU.md).
- [ecc-library](skills/ecc-library/SKILL.md): выбор подходящих workflows без загрузки всей библиотеки в контекст.
- [Галерея 63 изображений Forte](skills/frontend-craft/references/gallery.html), [текстовый индекс](skills/frontend-craft/references/reference-index.md), [12 палитр с контрастом](skills/frontend-craft/references/palettes.md), [шрифтовые пары](skills/frontend-craft/references/typography.md).
- [Все 311 скиллов ECC](catalog/ecc-skills.md) и [машинный каталог](catalog/ecc-skills.json). Сохранён весь исходный репозиторий: supporting files, rules, agents, commands, docs, scripts и лицензия.
- [Разбор ECC и ограничения](catalog/ECC-REVIEW.md), [источники и commit](catalog/SOURCES.md), [проверки сборки](catalog/VALIDATION.md).
- [AGENTS.md](AGENTS.md) и [CLAUDE.md](CLAUDE.md): инструкции для агента, открывшего эту папку как проект.

Оригинальные 311 скиллов доступны через библиотеку; они не регистрируются как 311 отдельных глобальных команд. Это сохраняет короткий список рабочих скиллов и помогает выбирать материал по задаче. Собственные hooks, MCP-сервисы, правила автозапуска, память и runtime ECC здесь сохранены как исходники, но не активированы.

Имеющиеся у тебя скиллы `ui-ux-pro-max`, `design-system`, `brand`, `ui-styling` и другие не изменены. Основной новый web-скилл использует общие принципы подборки; палитра чёрный/лайм не навязывается каждому продукту.

## Подключение, проверка и удаление

Открой Terminal в этой папке. Все helpers работают на Python 3.11+ без сторонних пакетов.

```sh
# Посмотреть план, ничего не менять
python3 scripts/manage_skills.py install

# Подключить шесть скиллов к Codex и Claude Code
python3 scripts/manage_skills.py install --apply


# Подключить также шесть frontend-ролей к обоим инструментам
python3 scripts/manage_agents.py install --apply

# Проверить фактические ссылки
python3 scripts/manage_agents.py status
python3 scripts/manage_skills.py status

# Подключить только к одному агенту
python3 scripts/manage_skills.py install --target codex --apply
python3 scripts/manage_skills.py install --target claude --apply

# Удалить только ссылки, созданные этим комплектом; файлы и чужие скиллы остаются
python3 scripts/manage_agents.py remove --apply
python3 scripts/manage_skills.py remove --apply
```

Codex получает ссылки в `~/.agents/skills`, Claude Code — в `~/.claude/skills`. При совпадении имени с чужим скиллом установка останавливается до записи, ничего не перезаписывает. Актуальный результат подключения сохранён в [installation.json](catalog/installation.json).

Папка — источник скиллов и ролей. Перед её перемещением выполни `remove --apply` для manage_agents.py и manage_skills.py. После перемещения сначала `python3 scripts/render_agents.py --write`, затем `install --apply` для обоих установщиков. Иначе старые ссылки и абсолютные пути перестанут работать. Для переноса на другой компьютер копируй весь комплект и выполни эти три шага; [подробности](FRONTEND-AGENTS-GUIDE-RU.md). Локальное подключение не распространяется автоматически на облачные сессии.

## Найти материал

```sh
python3 scripts/find_skill.py "доступность"
python3 scripts/find_skill.py "react" --limit 8
python3 scripts/find_skill.py "бэкенд"
python3 scripts/find_skill.py "машинное обучение"
python3 scripts/find_skill.py --category machine-learning
python3 scripts/find_skill.py --category backend-data --limit 20
```

Поиск возвращает путь и описание; ничего не устанавливает и не запускает. Оригинальные workflows могут требовать дополнительных инструментов или разрешений. Замечания к конкретным примерам описаны в [совместимости](skills/ecc-library/references/compatibility.md).

## Проверить целостность и helpers

```sh
python3 scripts/validate_kit.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 skills/frontend-craft/scripts/contrast.py '#232329' '#B8A7F0'
```

Проверки целостности не заменяют практического применения скилла к интерфейсу. Для будущих итераций есть [набор сценариев оценки](tests/skill-scenarios.md). Проверяется наблюдаемое поведение агента и получившийся интерфейс, а не совпадение текста с шаблоном.

ML-скилл автономен: его папку можно перенести отдельно вместе с references, assets и scripts. Он использует ECC и официальные материалы scikit-learn, PyTorch, Google и Hugging Face; [источники и исправления примеров](skills/ml-engineering/references/sources.md).

Backend-скилл тоже автономен: для переноса достаточно всей папки `skills/backend-engineering`. [Источники и поправки к ECC](skills/backend-engineering/references/sources.md) описывают проверенные решения по API, транзакциям, миграциям и надёжной обработке задач.

## Обновление

ECC закреплён на commit из SOURCES.md. Автоматического обновления нет. Для обновления получи новую версию в отдельную папку, сравни нужные скиллы и зависимости, затем пересобери каталог/manifest и прогони проверки. Не заменяй всю работающую конфигурацию агента upstream-установщиком ради получения свежего текста одного скилла.
