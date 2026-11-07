"""Private, on-device audio transcription for Apple Silicon development."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class TranscriptionError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


LANGUAGES = {'auto': None, 'ru': 'ru', 'kk': 'kk', 'en': 'en'}
EXTENSIONS = {'.mp3', '.wav', '.m4a', '.mp4', '.mpeg', '.mpga', '.webm'}


def _duration(path):
    executable = shutil.which('ffprobe')
    if not executable:
        raise TranscriptionError('Для проверки аудио установите ffmpeg (включает ffprobe).', 503)
    try:
        result = subprocess.run(
            [executable, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            check=True, capture_output=True, text=True, timeout=20,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        raise TranscriptionError('Не удалось прочитать аудио. Проверьте файл и его формат.') from None


def transcribe(upload: FileStorage, language: str, config: dict):
    language = language.lower().strip()
    if language not in LANGUAGES:
        raise TranscriptionError('Язык должен быть auto, ru, kk или en.')
    filename = secure_filename(upload.filename or '')
    if Path(filename).suffix.lower() not in EXTENSIONS:
        raise TranscriptionError('Поддерживаются MP3, WAV, M4A, MP4, MPEG и WebM.')
    maximum = config.get('ASR_MAX_UPLOAD_BYTES', 25 * 1024 * 1024)
    maximum_duration = config.get('ASR_MAX_DURATION_SECONDS', 1800)
    try:
        import mlx_whisper
    except ImportError:
        raise TranscriptionError('Локальный STT не установлен. Установите backend/requirements-mac.txt.', 503) from None
    try:
        with tempfile.TemporaryDirectory(prefix='cqa-asr-') as directory:
            path = Path(directory) / ('audio' + Path(filename).suffix.lower())
            size = 0
            with path.open('wb') as target:
                while True:
                    chunk = upload.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > maximum:
                        raise TranscriptionError(f'Аудиофайл превышает лимит {maximum // (1024 * 1024)} МиБ.')
                    target.write(chunk)
            if size == 0:
                raise TranscriptionError('Аудиофайл пустой.')
            duration = _duration(path)
            if duration <= 0 or duration > maximum_duration:
                raise TranscriptionError(f'Длительность записи должна быть не больше {maximum_duration // 60} минут.')
            try:
                result = mlx_whisper.transcribe(
                    str(path), path_or_hf_repo=config.get('ASR_MODEL', 'mlx-community/whisper-large-v3-turbo'),
                    language=LANGUAGES[language], task='transcribe', verbose=False,
                )
            except Exception:
                raise TranscriptionError('Локальная транскрибация не удалась. Проверьте модель и аудиофайл.', 503) from None
            segments = []
            for item in result.get('segments', []):
                text = re.sub(r'\s+', ' ', str(item.get('text', ''))).strip()
                if not text:
                    continue
                start = max(0.0, float(item.get('start', 0)))
                end = max(start, float(item.get('end', start)))
                segments.append({'start_seconds': round(start, 2), 'end_seconds': round(end, 2), 'text': text})
            if not segments:
                raise TranscriptionError('В аудиозаписи не распозналась речь.')
            return {'language': result.get('language') or (LANGUAGES[language] or 'ru'),
                    'duration_seconds': round(duration, 2), 'segments': segments,
                    'model': config.get('ASR_MODEL', 'mlx-community/whisper-large-v3-turbo')}
    except TranscriptionError:
        raise
