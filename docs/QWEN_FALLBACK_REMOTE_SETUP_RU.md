# Запустить приложение с Qwen на другом компьютере

Эта инструкция поднимает **основное BimBomBam-приложение** на компьютере B: Ollama с Qwen, Flask API и фронтенд. Открыть интерфейс можно на B или на компьютере A через SSH-туннель.

## Что именно запускаем

- Подключённая к приложению модель — `qwen3:4b` через Ollama. Это рабочий локальный baseline, который мы запускали и проверяли на небольшой DEV-выборке.
- Обученный LoRA adapter `Qwen3-1.7B` не подключён к оценщику приложения.
- Автоматическое переключение «основная модель → fallback Qwen» пока не реализовано. Сейчас приложение вызывает настроенную Ollama-модель напрямую; ниже запускается именно этот рабочий Qwen-вариант.
- Результаты baseline были диагностическими: 55/80 решений совпали с эталонами на 10 DEV-диалогах, распознавание N/A осталось слабым. Проверяй выводы модели перед использованием.

## 1. Подготовить компьютер B

Нужны Git, Python 3.11+, Node.js/npm и Ollama. На Windows для этой конфигурации в проекте есть скрипт, который скачивает закреплённый portable Ollama и `qwen3:4b`. На macOS установи Ollama с [официальной страницы](https://ollama.com/download). Для Qwen нужен запас оперативной/видеопамяти: вес модели около 2,5 ГБ, а большой контекст требует дополнительную память.

Склонируй репозиторий или перейди в его рабочую копию:

```sh
git clone <URL-репозитория>
cd BimBomBam
```

Не копируй чужой `backend/.env` и `case/api.txt`: в них могут быть приватные значения. Создай собственный локальный `.env` из шаблона на шаге 3.

## 2. Установить и запустить Qwen через Ollama

### Windows PowerShell

Первый запуск установит portable runtime и загрузит Qwen:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local_model.ps1 -Action setup
```

Следующие запуски:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local_model.ps1 -Action start
```

Проверить модель и сервис:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local_model.ps1 -Action status
```

### macOS или Linux

Установи Ollama, затем открой терминал:

```sh
ollama pull qwen3:4b
```

На macOS Ollama обычно работает через установленное приложение. На Linux, если сервис ещё не запущен, оставь в отдельном терминале:

```sh
ollama serve
```

Проверка:

```sh
ollama list
ollama run qwen3:4b "Ответь одним словом: готово"
```

На машине B Ollama должна быть доступна Flask-бэкенду по `http://127.0.0.1:11434`.

## 3. Настроить Flask-бэкенд

Из корня репозитория:

Windows PowerShell:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

macOS/Linux:

```sh
[ -f backend/.env ] || cp backend/.env.example backend/.env
```

В `backend/.env` выставь локальные значения для Qwen:

```dotenv
DATABASE_ENGINE=sqlite
PORT=6767
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT=300
OLLAMA_NUM_CTX=24576
OLLAMA_NUM_PREDICT=4096
OLLAMA_NUM_CTX_CALL=40960
OLLAMA_NUM_PREDICT_CALL=3072
OLLAMA_THINK=false
```

Оставь остальные существующие настройки `.env` без изменений. Не добавляй сюда ключ модели: локальная Ollama не требует API-ключа.

## 4. Установить зависимости и подготовить базу

Windows PowerShell:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m flask --app backend/app.py init-db
.\backend\.venv\Scripts\python.exe -m flask --app backend/app.py seed-checklist
```

macOS/Linux:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m flask --app backend/app.py init-db
backend/.venv/bin/python -m flask --app backend/app.py seed-checklist
```

## 5. Запустить backend и frontend

Оставь Ollama запущенной. В отдельном терминале из корня проекта запусти Flask:

Windows:

```powershell
.\backend\.venv\Scripts\python.exe backend/app.py
```

macOS/Linux:

```sh
backend/.venv/bin/python backend/app.py
```

Проверь API: `http://127.0.0.1:6767/api/health` должен вернуть `{"status":"ok"}`, а `http://127.0.0.1:6767/api/ready` — `{"status":"ready"}`.

В ещё одном терминале запусти интерфейс. `PUBLIC_API_URL` должен быть задан **до** `npm start`, потому что dev-скрипт сначала собирает frontend.

Windows PowerShell:

```powershell
cd frontend
npm.cmd ci
$env:PUBLIC_API_URL = 'http://127.0.0.1:6767/api'
npm.cmd start
```

macOS/Linux:

```sh
cd frontend
npm ci
PUBLIC_API_URL=http://127.0.0.1:6767/api npm start
```

На компьютере B открой `http://localhost:3000`. Выбери диалог и запусти оценку. При выборе `auto` для семантического чек-листа backend использует настроенную Qwen через Ollama. В `backend/.env` нужно указать точное имя установленной модели.

## 6. Открыть интерфейс с компьютера A

Оба сервера привязаны к loopback на B. Не меняй их на `0.0.0.0` и не выставляй API в интернет: в текущем прототипе нет аутентификации.

С компьютера A открой SSH-туннель к B:

```sh
ssh -N -L 3000:127.0.0.1:3000 -L 6767:127.0.0.1:6767 <пользователь>@<адрес-компьютера-B>
```

Оставь SSH-команду работающей и на A открой `http://localhost:3000`. Браузер A попадёт в frontend и API на B через туннель; Qwen и Ollama остаются на B. Закрой туннель сочетанием `Ctrl+C`.

Если используется нестандартный SSH-порт, добавь `-p <порт>`. В Windows команда `ssh` доступна в PowerShell при установленном OpenSSH Client.

## Остановить процессы

На B нажми `Ctrl+C` в терминалах Flask и frontend. Ollama останови через приложение/системный сервис; на Windows можно выполнить:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\local_model.ps1 -Action stop
```

## Если что-то не запускается

- `503` при оценке: проверь, что Ollama запущена, `ollama list` показывает `qwen3:4b`, а `OLLAMA_MODEL` в `backend/.env` совпадает с именем из списка.
- Ошибка контекста (`422`): диалог не был обрезан. Для длинного чата увеличивай `OLLAMA_NUM_CTX` осторожно с учётом доступной памяти; для звонков заданы отдельные `OLLAMA_NUM_CTX_CALL` и `OLLAMA_NUM_PREDICT_CALL`.
- Frontend не соединяется с API: проверь `PUBLIC_API_URL`, `CORS_ORIGINS`, `/api/health` и то, что SSH-туннель прокидывает оба порта.
- Оценка долгая: скорость зависит от компьютера B и длины диалога. Не запускай несколько тяжёлых оценок параллельно.

Подробности о модели и измеренном baseline: [результаты baseline](ML_BASELINE_RESULTS_RU.md) и [описание обучаемой модели и fallback-плана](ML_TRAINING_AND_CASCADE_RU.md).


## Уже установленная Qwen3:8b на этом Mac

На Mac, где выполнялась проверка 8 ноября 2026 года, установлена `qwen3:8b`.
Для повторного запуска на этом Mac используй её; скачивание `qwen3:4b` из Windows-инструкции выше не требуется.
В `backend/.env` сохранён следующий профиль для полных чатов и транскриптов звонков:

```dotenv
OLLAMA_MODEL=qwen3:8b
OLLAMA_NUM_CTX=32768
OLLAMA_NUM_PREDICT=2048
OLLAMA_NUM_CTX_CALL=32768
OLLAMA_NUM_PREDICT_CALL=2048
OLLAMA_TIMEOUT=300
OLLAMA_THINK=false
```

Ollama запускается в отдельном терминале с ограничением на одну модель и одну генерацию:

```sh
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NO_CLOUD=1 ollama serve
```

Эти переменные относятся к процессу Ollama; запись их только в `backend/.env` не настраивает Ollama.
Если сервер уже работает, сначала останови именно его и запусти с указанными параметрами.
Бэкенд и frontend запускаются командами из шага 5.

Проверка размера через текущую функцию `assess` пропустила все 65 предоставленных
диалогов с неизменными сообщениями и официальным чек-листом приложения. Самый большой
запрос — 28 308 байт, доступный безопасный бюджет входа — 29 696 байт. Проверка сейчас
использует консервативную границу по UTF-8-байтам, а не точный подсчёт токенов; поэтому
16K ошибочно отклоняли часть русских входов. Новая или расширенная рубрика требует
повторной проверки размера. Эти результаты подтверждают вместимость, а не правильность оценок.

Реальная проверка самого длинного русского звонка `p4-ru-004` подтвердила приём
полного входа: Ollama обработала 7 994 токена без обрезки. Однако генерация не
завершилась за 300 секунд, и API вернул 503. Следовательно, ограничение размера
для набора устранено, но полная обработка самого длинного звонка пока не подтверждена:
остается проблема времени генерации. Модель в `ollama ps` занимала 7,6 ГБ при 32K/q8_0,
против 7,4 ГБ при прежних 16K/f16. Это измерение одного локального запуска.
