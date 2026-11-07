# Локальная транскрибация MP3

На Mac аудиофайл загружается в локальный Flask backend (`POST /api/transcribe`),
обрабатывается `mlx-whisper` и удаляется вместе с временной директорией после ответа.
Аудио не отправляется стороннему API и не сохраняется в базе. В базу попадут только
подтверждённые пользователем текстовые реплики.

## Установка на Apple Silicon

```sh
brew install ffmpeg
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-mac.txt
```

Первый запуск может скачать ASR-модель из Hugging Face. По умолчанию используется
`mlx-community/whisper-large-v3-turbo`; переопределение — `ASR_MODEL` в `backend/.env`.
Включите `ASR_ENABLED=true` только в локальной конфигурации Mac.
Затем запустить backend через `backend/.venv/bin/python -m flask --app app:create_app
run --host 127.0.0.1 --port 6767` из каталога `backend`.

Поддерживаются MP3, WAV, M4A, MP4, MPEG и WebM до 25 МиБ и 30 минут. Язык можно
задать явно или определить автоматически (RU/KZ/EN).

## Ограничение ролей

Whisper даёт текстовые сегменты и таймкоды, но сам по себе не определяет, кто говорит.
Перед оценкой интерфейс показывает сегменты для исправления и просит назначить каждому
реплику клиента или оператора. Это нужно, потому что чек-лист оценивает действия именно
оператора. Автоматическая diarization пока не подключена.

После подтверждения диалог создаётся как `voice call`, затем автоматически запускается
текущий локальный evaluator. Экспериментальный MLX LoRA adapter находится в
`data/models/qwen3-1.7b-weak-cqa-v1`; он обучен на синтетических слабых метках и пока не
подключается как primary, поскольку smoke-run выявил ошибки evidence и формата JSON.
Подробности обучения и статус adapter — в `docs/ML_TRAINING_AND_CASCADE_RU.md`.
