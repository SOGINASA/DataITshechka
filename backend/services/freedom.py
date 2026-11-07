"""Adapter for the observed Freedom DEV dataset envelope; no guessed API methods."""
import json
import re
import time
from http.client import HTTPException
from datetime import datetime, timedelta
from urllib import error, request
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import Conversation, db
from services.validation import ValidationError, conversation, obj, sequence, string

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 30
GROUP = 'DEV'


class IntegrationError(ValueError):
    """Safe, user-facing error; never include signed URLs or upstream response text."""


class ImportConflict(IntegrationError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url):
    if not isinstance(url, str) or not url:
        raise IntegrationError('Задайте FREEDOM_API_URL в локальном .env.')
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == 'https' and parts.hostname
                 and parts.hostname.endswith('.environment.api.powerplatform.com')
                 and parts.port in (None, 443) and not parts.username and not parts.password
                 and not parts.fragment and parse_qs(parts.query).get('group_id') == [GROUP])
    except ValueError:
        valid = False
    if not valid:
        raise IntegrationError('FREEDOM_API_URL должен быть HTTPS URL Power Platform с group_id=DEV.')


def decode_payload(raw):
    if len(raw) > MAX_RESPONSE_BYTES:
        raise IntegrationError('Ответ DEV API превышает 8 МиБ.')
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise IntegrationError('DEV API вернул некорректный JSON.') from None


def fetch_dataset(url):
    validate_url(url)
    started = time.monotonic()
    req = request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'CQA-DEV-import/1.0'}, method='GET')
    try:
        # Do not forward the signature to another host, or retry a workflow invocation.
        with request.build_opener(NoRedirect).open(req, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise IntegrationError(f'DEV API вернул HTTP {response.status}.')
            if response.headers.get_content_type() != 'application/json':
                raise IntegrationError('DEV API вернул ответ не в формате application/json.')
            chunks, size = [], 0
            while True:
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise IntegrationError('Превышено время ожидания DEV API.')
                chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise IntegrationError('Ответ DEV API превышает 8 МиБ.')
            raw = b''.join(chunks)
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise IntegrationError(f'DEV API вернул HTTP {status}; проверьте доступность подписанной ссылки.') from None
    except (error.URLError, OSError, TimeoutError, HTTPException):
        raise IntegrationError('Не удалось получить DEV-данные: ошибка сети или таймаут.') from None
    return decode_payload(raw)


def transcript_times(transcript):
    """Keep input order; never silently reorder utterances or invent audio alignment."""
    values = [string(message.get('timestamp'), 'timestamp', 80) for message in transcript]
    relative = [bool(re.fullmatch(r'\d{1,4}:[0-5]\d', value)) for value in values]
    if all(relative):
        times = [(int(value.split(':')[0]) * 60 + int(value.split(':')[1])) * 1000 for value in values]
        return times, 'conversation_start', None, values
    if any(relative):
        raise ValidationError('В одном диалоге смешаны относительные и абсолютные timestamp.')
    try:
        dates = [datetime.fromisoformat(value.replace('Z', '+00:00')) for value in values]
        if any(date.tzinfo is None or date.utcoffset() is None for date in dates):
            raise ValueError('Timezone required')
        origin = dates[0]
        times = [(date - origin) // timedelta(milliseconds=1) for date in dates]
    except ValueError:
        raise ValidationError('timestamp должен быть MM:SS или ISO 8601 с часовым поясом.') from None
    return times, 'first_message', values[0], values


def normalize_dataset(payload):
    """Validate the entire batch before it can touch the database."""
    try:
        obj(payload, ('error', 'isSuccess', 'data'), ('isSuccess', 'data'))
        if payload['isSuccess'] is not True or payload.get('error') not in (None, ''):
            raise IntegrationError('DEV API сообщил об ошибке получения данных.')
        data = obj(payload['data'], ('dataset_group_id', 'total_records', 'records'),
                   ('dataset_group_id', 'total_records', 'records'))
        if data['dataset_group_id'] != GROUP:
            raise IntegrationError('Получен датасет другой группы; ожидается DEV.')
        records = sequence(data['records'], 'records', 100, nonempty=False)
        if type(data['total_records']) is not int or data['total_records'] != len(records):
            raise IntegrationError('total_records не совпадает с размером массива records.')
        normalized, identifiers = [], set()
        for index, record in enumerate(records, start=1):
            try:
                obj(record, ('conversation_id', 'channel', 'language', 'transcript', 'audio_url'),
                    ('conversation_id', 'channel', 'language', 'transcript'))
                source_id = string(record['conversation_id'], 'conversation_id', 120)
                if source_id in identifiers:
                    raise ValidationError('conversation_id повторяется внутри датасета.')
                identifiers.add(source_id)
                channel = {'agent chat': 'chat', 'voice call': 'call'}.get(record['channel']) if isinstance(record['channel'], str) else None
                language = {'RU': 'ru', 'KZ': 'kk', 'EN': 'en'}.get(record['language']) if isinstance(record['language'], str) else None
                if channel is None or language is None:
                    raise ValidationError('Неизвестный channel или language в DEV-данных.')
                transcript = sequence(record['transcript'], 'transcript', 2000)
                for message in transcript:
                    obj(message, ('timestamp', 'speaker', 'text'), ('timestamp', 'speaker', 'text'))
                times, reference, origin, original_times = transcript_times(transcript)
                messages = [{'id': str(i + 1), 'speaker': message['speaker'], 'text': message['text'], 'start_ms': times[i]}
                            for i, message in enumerate(transcript)]
                item = conversation({'external_id': f'freedom:{GROUP}:{source_id}',
                                     'title': f'{GROUP} · {source_id}', 'channel': channel, 'language': language,
                                     'recording_url': record.get('audio_url'), 'messages': messages})
                for message, source in zip(item['messages'], transcript):
                    message['text'] = source['text']
                item['source_metadata'] = {'provider': 'freedom', 'dataset_group_id': GROUP,
                                           'conversation_id': source_id, 'timestamp_reference': reference,
                                           'time_origin': origin, 'audio_alignment_verified': False,
                                           'source_timestamps': {str(i + 1): value for i, value in enumerate(original_times)}}
                normalized.append(item)
            except ValidationError as exc:
                raise IntegrationError(f'Некорректная DEV-запись №{index}: {exc}') from None
        return normalized
    except ValidationError as exc:
        raise IntegrationError(f'Некорректный формат DEV-ответа: {exc}') from None


def import_dataset(payload, dry_run=False):
    items = normalize_dataset(payload)
    external_ids = [item['external_id'] for item in items]
    existing = {row.external_id: row for row in db.session.scalars(
        select(Conversation).where(Conversation.external_id.in_(external_ids)))}
    pending, skipped = [], 0
    for item in items:
        row = existing.get(item['external_id'])
        if row is not None:
            if any(getattr(row, field) != value for field, value in item.items()):
                raise ImportConflict('Источник изменил ранее импортированный диалог. Импорт отменён; существующие данные сохранены.')
            skipped += 1
        else:
            pending.append(item)
    if not dry_run:
        try:
            db.session.add_all(Conversation(**item) for item in pending)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ImportConflict('Конфликт параллельного импорта. Данные не перезаписаны; повторите команду.') from None
    return {'dataset_group_id': GROUP, 'received': len(items), 'imported': 0 if dry_run else len(pending),
            'pending': len(pending) if dry_run else 0, 'skipped': skipped, 'dry_run': dry_run}
