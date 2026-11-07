# ML-скилл для Codex и Claude Code

Отдельный [ml-engineering](skills/ml-engineering/SKILL.md) добавлен к этому комплекту. Его задача — доводить ML-работу от данных и baseline до проверенной оценки и, когда нужно, внедрения модели.

## Как вызвать

В Codex: **`$ml-engineering`**. В Claude Code: **`/ml-engineering`**. Можно написать обычным текстом «Используй ml-engineering». Если текущая сессия ещё не видит новый скилл, открой новую. Запасной вариант — попросить прочитать файл SKILL.md по его полному пути.

Примеры:

> Используй ml-engineering. В этом проекте нужно прогнозировать спрос. Изучи данные и текущий стек, выбери корректный backtest, сделай простой baseline и сравни с кандидатом. Сохрани воспроизводимый запуск и отчёт с метриками.

> Используй ml-engineering. Проверь обучение PyTorch на Mac: сначала найди причину сбоя на маленьком примере, затем исправь и измерь результат.

> Используй ml-engineering. Проверь эту модель на утечки данных, корректность выборок, метрик и preprocessing. Дай конкретные замечания с доказательствами.

> Используй ml-engineering. Оцени поиск по нашим документам: отдельно retrieval, reranking и итоговый ответ. Предложи следующий эксперимент по найденным ошибкам.

## Что внутри

| Материал | Для чего |
|---|---|
| [Данные и разбиение](skills/ml-engineering/references/data-and-splits.md) | Время, группы, дубликаты, доступность признаков и labels |
| [Оценка и эксперименты](skills/ml-engineering/references/evaluation.md) | Baseline, метрики, thresholds, uncertainty и защищённый final test |
| [Обучение и ресурсы](skills/ml-engineering/references/training-and-compute.md) | PyTorch, CPU/MPS/CUDA, smoke run, checkpoints и измерение производительности |
| [LLM и retrieval](skills/ml-engineering/references/llms-and-retrieval.md) | Embeddings, ранжирование, fine-tuning и отдельные проверки качества |
| [Внедрение и мониторинг](skills/ml-engineering/references/serving-and-operations.md) | Артефакты, train/serve parity, promotion, rollback и delayed labels |
| [Карточка эксперимента](skills/ml-engineering/assets/experiment-card.md) | Кратко зафиксировать гипотезу, данные, метрики и бюджет |
| [Шаблон отчёта](skills/ml-engineering/assets/evaluation-report.md) | Сравнить baseline и кандидата; отделить измеренное от непроверенного |
| [Split auditor](skills/ml-engineering/references/split-auditor.md) | Проверить CSV manifest без ML-библиотек и загрузки данных во внешние сервисы |

Скилл не навязывает нейросети, облако или тяжёлый MLOps простому эксперименту. Он учитывает временные ряды, табличные модели, классификацию/регрессию, рекомендации и anomaly detection; для глубоких специализированных задач обращается к подходящим первичным источникам.

## Быстрая проверка helper

Из корня комплекта:

```sh
python3 skills/ml-engineering/scripts/audit_splits.py \
  skills/ml-engineering/assets/split-manifest.example.csv \
  --group-column entity_id --fingerprint-column content_hash \
  --time-column prediction_at --gap-seconds 86400 --require-validation
```

Это синтетический пример. Для своих данных указывай собственный manifest и только подходящие проверки. Например, прогноз будущих покупок уже известных клиентов не всегда требует разделять клиентов между выборками. PASS означает успешность включённых проверок manifest, а не доказательство отсутствия всех утечек.

## Откуда собран

Из ECC взяты и переработаны mle-workflow, ml-adoption-playbook и pytorch-patterns. Дополнительно изучены официальные скиллы Hugging Face для TRL и sentence-transformers, документация scikit-learn, PyTorch, Hugging Face Evaluate и Google. [Все источники с ссылками и замечания к примерам](skills/ml-engineering/references/sources.md).

Обучение реальных моделей не запускалось при сборке скилла. Автотесты проверяют manifest auditor и инфраструктуру комплекта; поведение агента на реальной ML-задаче оценивается отдельно по [сценариям](tests/ml-scenarios.md).

## Перенос и подключение

Основная установка использует `scripts/manage_skills.py install --apply`: пять скиллов подключаются к обоим агентам из одной папки. Уже подключённые ссылки сохраняются, чужие скиллы не перезаписываются.

Для отдельного переноса скопируй всю папку `skills/ml-engineering` в каталог навыков целевого агента: `~/.agents/skills/ml-engineering` для Codex или `~/.claude/skills/ml-engineering` для Claude Code. Не заменяй существующий одноимённый скилл без проверки. References, assets и scripts должны оставаться вместе; полная библиотека ECC для основной работы этого скилла не обязательна.
