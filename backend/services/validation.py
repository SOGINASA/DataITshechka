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
        obj(criterion, ('id', 'title', 'description', 'weight', 'critical', 'rule', 'answer_type',
                        'allow_na', 'na_condition', 'scale', 'section', 'require_evidence'), ('id', 'title'))
        cid = string(criterion['id'], 'criterion.id', 80)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', cid) or cid in ids:
            fail('criterion.id: уникальный код из латинских букв, цифр, _ и -.')
        ids.add(cid)
        answer_type = choice(criterion.get('answer_type', 'binary'), 'answer_type', ('binary', 'scale', 'flag'))
        item = {'id': cid, 'title': string(criterion['title'], 'criterion.title', 200),
                'description': string(criterion.get('description', ''), 'criterion.description', 4000, empty=True),
                'weight': number(criterion.get('weight', 0 if answer_type == 'flag' else 1), 'weight', 0 if answer_type == 'flag' else 0.01, 0 if answer_type == 'flag' else 100),
                'critical': criterion.get('critical', answer_type == 'flag'), 'answer_type': answer_type,
                'allow_na': criterion.get('allow_na', 'answer_type' not in criterion),
                'na_condition': string(criterion.get('na_condition', '' if 'answer_type' in criterion else 'По условиям пользовательского чек-листа.'), 'na_condition', 2000, empty=True),
                'section': string(criterion.get('section', ''), 'section', 200, empty=True),
                'require_evidence': criterion.get('require_evidence', False)}
        for field in ('critical', 'allow_na', 'require_evidence'):
            if type(item[field]) is not bool:
                fail(f'{field}: ожидается boolean.')
        if item['allow_na'] and 'answer_type' in criterion and not item['na_condition']:
            fail('Для N/A задайте na_condition.')
        item['scale'] = []
        if answer_type == 'scale':
            for step in sequence(criterion.get('scale'), 'scale', 30):
                obj(step, ('value', 'label'), ('value', 'label'))
                item['scale'].append({'value': number(step['value'], 'scale.value', 0, 1000),
                                      'label': string(step['label'], 'scale.label', 2000)})
            values = [step['value'] for step in item['scale']]
            if values != sorted(set(values)) or values[0] != 0 or values[-1] <= 0:
                fail('Шкала должна начинаться с 0, возрастать без повторов и иметь положительный максимум.')
        elif criterion.get('scale'):
            fail('scale допускается только для answer_type=scale.')
        rule = criterion.get('rule', {'type': 'manual'})
        obj(rule, ('type', 'speaker', 'terms'), ('type',))
        kind = choice(rule['type'], 'rule.type', ('manual', 'semantic', 'contains_any', 'contains_none'))
        if kind in ('manual', 'semantic'):
            if set(rule) != {'type'}:
                fail('Для manual/semantic допустимо только поле type.')
            item['rule'] = {'type': kind}
        else:
            if answer_type != 'binary':
                fail('Поиск фраз поддерживается только для binary. Для шкал и флагов используйте manual или semantic.')
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
        obj(override, ('criterion_id', 'status', 'value', 'explanation', 'evidence_message_ids', 'reviewed_range'),
            ('criterion_id', 'explanation'))
        cid = string(override['criterion_id'], 'criterion_id', 80)
        if cid in ids:
            fail('Повтор criterion_id в overrides.')
        ids.add(cid)
        overrides.append(assessment_item(override))
    result['overrides'] = overrides
    return result


def assessment_item(value):
    obj(value, ('criterion_id', 'status', 'value', 'explanation', 'evidence_message_ids', 'reviewed_range'),
        ('criterion_id', 'explanation'))
    result = {'criterion_id': string(value['criterion_id'], 'criterion_id', 80),
              'explanation': string(value['explanation'], 'explanation', 4000)}
    if 'status' not in value and 'value' not in value:
        fail('Укажите status или value.')
    if 'status' in value:
        result['status'] = choice(value['status'], 'status', ('pass', 'fail', 'scored', 'not_applicable', 'needs_review'))
    if 'value' in value:
        result['value'] = value['value']
    if 'evidence_message_ids' in value:
        result['evidence_message_ids'] = [string(mid, 'message_id', 80)
                                          for mid in sequence(value['evidence_message_ids'], 'evidence_message_ids', 50, nonempty=False)]
    if 'reviewed_range' in value:
        span = obj(value['reviewed_range'], ('start_message_id', 'end_message_id'), ('start_message_id', 'end_message_id'))
        result['reviewed_range'] = {k: string(v, k, 80) for k, v in span.items()}
    return result


def appeal(value):
    obj(value, ('criterion_id', 'expected_revision', 'comment', 'author'),
        ('criterion_id', 'expected_revision', 'comment', 'author'))
    return {'criterion_id': string(value['criterion_id'], 'criterion_id', 80),
            'expected_revision': number(value['expected_revision'], 'expected_revision', 1, 2147483647, integer=True),
            'comment': string(value['comment'], 'comment', 4000), 'author': string(value['author'], 'author', 120)}
