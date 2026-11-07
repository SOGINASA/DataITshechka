"""Strict validation shared by HTTP and offline import; no implicit coercion."""
import math
import re
from urllib.parse import urlsplit


class ValidationError(ValueError):
    pass


def fail(message):
    raise ValidationError(message)


def obj(value, allowed, required=()):
    if not isinstance(value, dict):
        fail('Ожидается JSON-объект.')
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown:
        fail('Неизвестные поля: ' + ', '.join(sorted(unknown)))
    if missing:
        fail('Обязательные поля: ' + ', '.join(sorted(missing)))
    return value


def string(value, field, limit, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        fail(f'{field}: ожидается строка длиной от {0 if empty else 1} до {limit}.')
    return value.strip()


def choice(value, field, options):
    if not isinstance(value, str) or value not in options:
        fail(f'{field}: допустимы {", ".join(options)}.')
    return value


def number(value, field, minimum=0, maximum=86400000, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        fail(f'{field}: ожидается конечное число.')
    if integer and type(value) is not int:
        fail(f'{field}: ожидается целое число.')
    if not minimum <= value <= maximum:
        fail(f'{field}: значение вне диапазона [{minimum}, {maximum}].')
    return value


def sequence(value, field, limit, nonempty=True):
    if not isinstance(value, list) or len(value) > limit or (nonempty and not value):
        fail(f'{field}: ожидается массив из {1 if nonempty else 0}–{limit} элементов.')
    return value


def conversation(value):
    obj(value, ('external_id', 'title', 'channel', 'language', 'operator_name', 'recording_url', 'messages'),
        ('title', 'channel', 'language', 'messages'))
    result = {'title': string(value['title'], 'title', 200),
              'channel': choice(value['channel'], 'channel', ('chat', 'call')),
              'language': choice(value['language'], 'language', ('ru', 'kk', 'en'))}
    for field, limit in (('external_id', 160), ('operator_name', 120), ('recording_url', 2048)):
        result[field] = None if value.get(field) is None else string(value[field], field, limit)
    if result['recording_url']:
        try:
            url = urlsplit(result['recording_url'])
            valid = url.scheme in ('http', 'https') and url.hostname and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid:
            fail('recording_url: ожидается HTTP(S) URL без логина и пароля.')
    messages, ids = [], set()
    previous_start = -1
    for index, message in enumerate(sequence(value['messages'], 'messages', 2000)):
        obj(message, ('id', 'speaker', 'text', 'start_ms', 'end_ms'), ('speaker', 'text'))
        mid = string(message.get('id', str(index + 1)), 'message.id', 80)
        if mid in ids:
            fail('Идентификаторы реплик должны быть уникальны.')
        ids.add(mid)
        item = {'id': mid, 'speaker': choice(message['speaker'], 'speaker', ('client', 'operator', 'bot', 'system')),
                'text': string(message['text'], 'text', 10000)}
        start, end = message.get('start_ms'), message.get('end_ms')
        if start is not None:
            number(start, 'start_ms', integer=True)
            if start < previous_start:
                fail('Реплики должны идти по возрастанию start_ms.')
            previous_start = start
        if end is not None:
            number(end, 'end_ms', integer=True)
            if start is None or end < start:
                fail('end_ms требует start_ms и не может быть меньше него.')
        item.update(start_ms=start, end_ms=end)
        messages.append(item)
    result['messages'] = messages
    return result


def checklist(value):
    obj(value, ('name', 'version', 'description', 'is_demo', 'criteria'), ('name', 'version', 'criteria'))
    result = {'name': string(value['name'], 'name', 160), 'version': string(value['version'], 'version', 40),
              'description': string(value.get('description', ''), 'description', 4000, empty=True),
              'is_demo': value.get('is_demo', False)}
    if type(result['is_demo']) is not bool:
        fail('is_demo: ожидается boolean.')
    criteria, ids = [], set()
    for criterion in sequence(value['criteria'], 'criteria', 100):
        obj(criterion, ('id', 'title', 'description', 'weight', 'critical', 'rule'), ('id', 'title'))
        cid = string(criterion['id'], 'criterion.id', 80)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', cid) or cid in ids:
            fail('criterion.id: уникальный код из латинских букв, цифр, _ и -.')
        ids.add(cid)
        item = {'id': cid, 'title': string(criterion['title'], 'criterion.title', 200),
                'description': string(criterion.get('description', ''), 'criterion.description', 4000, empty=True),
                'weight': number(criterion.get('weight', 1), 'weight', 0.01, 100),
                'critical': criterion.get('critical', False)}
        if type(item['critical']) is not bool:
            fail('critical: ожидается boolean.')
        rule = criterion.get('rule', {'type': 'manual'})
        obj(rule, ('type', 'speaker', 'terms'), ('type',))
        kind = choice(rule['type'], 'rule.type', ('manual', 'contains_any', 'contains_none'))
        if kind == 'manual':
            if set(rule) != {'type'}:
                fail('Для manual допустимо только поле type.')
            item['rule'] = {'type': 'manual'}
        else:
            speaker = choice(rule.get('speaker', 'operator'), 'rule.speaker', ('client', 'operator', 'bot', 'system', 'any'))
            terms = obj(rule.get('terms'), ('ru', 'kk', 'en'))
            if not terms:
                fail('rule.terms: нужен хотя бы один язык.')
            item['rule'] = {'type': kind, 'speaker': speaker, 'terms': {
                language: [string(term, 'term', 200) for term in sequence(words, 'terms', 30)]
                for language, words in terms.items()}}
        criteria.append(item)
    result['criteria'] = criteria
    return result


def review(value):
    obj(value, ('expected_revision', 'reviewer', 'comment', 'overrides'),
        ('expected_revision', 'reviewer', 'comment', 'overrides'))
    result = {'expected_revision': number(value['expected_revision'], 'expected_revision', 1, 2147483647, integer=True),
              'reviewer': string(value['reviewer'], 'reviewer', 120),
              'comment': string(value['comment'], 'comment', 4000)}
    overrides, ids = [], set()
    for override in sequence(value['overrides'], 'overrides', 100):
        obj(override, ('criterion_id', 'status', 'explanation'), ('criterion_id', 'status', 'explanation'))
        cid = string(override['criterion_id'], 'criterion_id', 80)
        if cid in ids:
            fail('Повтор criterion_id в overrides.')
        ids.add(cid)
        overrides.append({'criterion_id': cid,
                          'status': choice(override['status'], 'status', ('pass', 'fail', 'not_applicable', 'needs_review')),
                          'explanation': string(override['explanation'], 'explanation', 4000)})
    result['overrides'] = overrides
    return result
