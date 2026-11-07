"""Canonical inputs and strict assessment validation; no model-generated quotations."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def text(value, field, limit=4000):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, f'{field}: invalid string')
    return value


def number(value, field, low=0, high=10000):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            f'{field}: invalid number')
    return value


def array(value, field, maximum=2000, nonempty=True):
    require(isinstance(value, list) and int(nonempty) <= len(value) <= maximum, f'{field}: invalid array')
    return value


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError('Non-finite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError('Invalid JSON') from exc


def read_json(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 32 * 1024 * 1024, 'File exceeds 32 MiB')
    return loads(raw)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def rubric(raw):
    require(isinstance(raw, dict), 'rubric: expected object')
    result = {k: text(raw.get(k), f'rubric.{k}') for k in ('name', 'version')}
    result['description'] = raw.get('description', '')
    require(isinstance(result['description'], str), 'rubric.description: invalid')
    criteria, ids = [], set()
    for c in array(raw.get('criteria'), 'criteria', 100):
        require(isinstance(c, dict), 'criterion: expected object')
        item = {k: text(c.get(k), f'criterion.{k}') for k in ('id', 'title', 'description')}
        require(item['id'] not in ids, 'Duplicate criterion ID')
        ids.add(item['id'])
        kind = c.get('answer_type')
        require(kind in ('binary', 'scale', 'flag'), 'Unsupported answer_type')
        item.update(answer_type=kind, weight=number(c.get('weight'), 'weight', 0, 100),
                    section=c.get('section', ''), allow_na=c.get('allow_na', False),
                    na_condition=c.get('na_condition', ''), scale=deepcopy(c.get('scale', [])))
        require(type(item['allow_na']) is bool, 'allow_na: expected bool')
        require(isinstance(item['section'], str) and isinstance(item['na_condition'], str), 'Invalid criterion text')
        if item['allow_na']:
            text(item['na_condition'], 'na_condition')
        if kind == 'flag':
            require(item['weight'] == 0, 'Flags must have zero weight')
        if kind == 'scale':
            steps = array(item['scale'], 'scale', 100)
            values = []
            for step in steps:
                require(isinstance(step, dict), 'Invalid scale step')
                values.append(number(step.get('value'), 'scale.value'))
                text(step.get('label'), 'scale.label')
            require(len(values) == len(set(values)) and min(values) == 0 and max(values) > 0, 'Invalid scale values')
        else:
            require(not item['scale'], 'Only scale criteria can have steps')
        criteria.append(item)
    require(sum(Decimal(str(c['weight'])) for c in criteria) == 100, 'Weighted criteria must sum to 100')
    result['criteria'] = criteria
    return result


def conversation(raw):
    require(isinstance(raw, dict), 'conversation: expected object')
    cid = raw.get('conversation_id') or raw.get('external_id') or raw.get('id')
    channel = {'agent chat': 'chat', 'voice call': 'call'}.get(raw.get('channel'), raw.get('channel'))
    language = {'RU': 'ru', 'KZ': 'kk', 'EN': 'en', 'kz': 'kk'}.get(raw.get('language'), raw.get('language'))
    require(channel in ('chat', 'call') and language in ('ru', 'kk', 'en'), 'Unsupported channel/language')
    truncated = raw.get('start_truncated', False)
    require(type(truncated) is bool, 'start_truncated: expected bool')
    result = {'conversation_id': text(cid, 'conversation_id', 160), 'channel': channel,
              'language': language, 'start_truncated': truncated, 'messages': []}
    messages = raw.get('messages', raw.get('transcript'))
    ids = set()
    for i, m in enumerate(array(messages, 'messages')):
        require(isinstance(m, dict), 'message: expected object')
        mid = text(m.get('id', str(i + 1)), 'message.id', 160)
        require(mid not in ids, 'Duplicate message ID')
        ids.add(mid)
        require(m.get('speaker') in ('client', 'operator', 'bot', 'system'), 'Unsupported speaker')
        item = {'id': mid, 'speaker': m['speaker'], 'text': text(m.get('text'), 'message.text', 20000)}
        for field in ('start_ms', 'end_ms'):
            if m.get(field) is not None:
                require(type(m[field]) is int and m[field] >= 0, f'{field}: expected nonnegative integer')
                item[field] = m[field]
        if 'end_ms' in item:
            require('start_ms' in item and item['end_ms'] >= item['start_ms'], 'Invalid message interval')
        if m.get('timestamp') is not None:
            item['timestamp'] = text(m['timestamp'], 'timestamp', 80)
        result['messages'].append(item)
    starts = [m['start_ms'] for m in result['messages'] if 'start_ms' in m]
    require(starts == sorted(starts), 'Out of order message times')
    # Original timestamps stay intact. No invented audio alignment or signed URLs in prompts.
    return result


def dataset(path):
    path = Path(path)
    if path.suffix == '.jsonl':
        rows = [loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        raw = read_json(path)
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and 'isSuccess' in raw:
            require(raw['isSuccess'] is True and raw.get('error') in (None, ''), 'Organizer reported failure')
            rows = raw.get('data', {}).get('records')
            require(isinstance(rows, list) and raw['data'].get('total_records') == len(rows), 'Organizer count mismatch')
        elif isinstance(raw, dict) and 'conversations' in raw:
            rows = raw['conversations']
        else:
            rows = [raw]
    result = [conversation(row) for row in array(rows, 'dataset', 10000)]
    require(len({r['conversation_id'] for r in result}) == len(result), 'Duplicate conversation ID')
    return result


def response_schema(checklist):
    properties = {
        'criterion_id': {'type': 'string', 'enum': [c['id'] for c in checklist['criteria']]},
        'status': {'type': 'string', 'enum': ['pass', 'fail', 'scored', 'not_applicable', 'needs_review']},
        'value': {'type': ['boolean', 'number', 'null']},
        'explanation': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
        'evidence_message_ids': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 50},
        'reviewed_range': {'anyOf': [{'type': 'null'}, {'type': 'object', 'additionalProperties': False,
            'required': ['start_message_id', 'end_message_id'],
            'properties': {k: {'type': 'string'} for k in ('start_message_id', 'end_message_id')}}]},
        'knowledge_status': {'type': 'string', 'enum': ['not_needed', 'supported', 'missing', 'conflict']},
        'knowledge_refs': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 10},
    }
    return {'type': 'object', 'additionalProperties': False, 'required': ['results'], 'properties': {
        'results': {'type': 'array', 'minItems': len(checklist['criteria']), 'maxItems': len(checklist['criteria']),
                    'items': {'type': 'object', 'additionalProperties': False,
                              'required': list(properties), 'properties': properties}}}}


def validate_results(raw, checklist, dialog, knowledge):
    require(isinstance(raw, dict) and set(raw) == {'results'}, 'Expected only results')
    criteria = {c['id']: c for c in checklist['criteria']}
    messages = {m['id']: m for m in dialog['messages']}
    positions = {mid: i for i, mid in enumerate(messages)}
    known = {k['id'] for k in knowledge}
    results, seen = [], set()
    required = set(response_schema(checklist)['properties']['results']['items']['required'])
    for item in array(raw['results'], 'results', 100):
        require(isinstance(item, dict) and set(item) == required, 'Wrong assessment fields')
        cid = item['criterion_id']
        require(isinstance(cid, str) and cid in criteria and cid not in seen, 'Unknown or duplicate criterion')
        seen.add(cid)
        c = criteria[cid]
        status, value = item['status'], item['value']
        require(status in ('pass', 'fail', 'scored', 'not_applicable', 'needs_review'), 'Invalid status')
        if status in ('not_applicable', 'needs_review'):
            require(value is None, 'Unknown/N/A value must be null')
            require(status != 'not_applicable' or c['allow_na'], 'N/A forbidden for criterion')
        elif c['answer_type'] == 'scale':
            number(value, 'scale response')
            require(status == 'scored' and value in [s['value'] for s in c['scale']], 'Invalid scale response')
        else:
            require(type(value) is bool, 'Binary/flag response must be boolean')
            expected = ('fail' if value else 'pass') if c['answer_type'] == 'flag' else ('pass' if value else 'fail')
            require(status == expected, 'Status/value polarity mismatch')
        text(item['explanation'], 'explanation', 2000)
        mids = array(item['evidence_message_ids'], 'evidence', 50, False)
        require(all(isinstance(mid, str) and mid in messages for mid in mids), 'Nonexistent evidence ID')
        require(len(set(mids)) == len(mids), 'Duplicate evidence')
        span = item['reviewed_range']
        if span is not None:
            require(isinstance(span, dict) and set(span) == {'start_message_id', 'end_message_id'}, 'Invalid range shape')
            a, b = span['start_message_id'], span['end_message_id']
            require(isinstance(a, str) and isinstance(b, str) and a in positions and b in positions, 'Nonexistent range ID')
            require(positions[a] <= positions[b], 'Reversed range')
        require(bool(mids) or span is not None, 'Every decision needs evidence or inspected range')
        # Negative claims need the inspected context, not an invented quotation of an absent action.
        absent = (c['answer_type'] == 'flag' and value is False) or (c['answer_type'] == 'binary' and value is False)
        require(not absent or span is not None, 'Missing action/violation requires reviewed_range')
        refs = array(item['knowledge_refs'], 'knowledge_refs', 10, False)
        require(all(isinstance(k, str) and k in known for k in refs) and len(set(refs)) == len(refs), 'Invalid knowledge reference')
        ks = item['knowledge_status']
        require(ks in ('not_needed', 'supported', 'missing', 'conflict'), 'Invalid knowledge_status')
        require(ks != 'supported' or bool(refs), 'Supported claim requires knowledge reference')
        require(ks != 'not_needed' or not refs, 'not_needed cannot cite knowledge')
        require(ks not in ('missing', 'conflict') or status == 'needs_review', 'Missing/conflicting knowledge requires review')
        out = deepcopy(item)
        out['evidence'] = [{'message_id': mid, 'quote': messages[mid]['text']} for mid in mids]
        results.append(out)
    require(seen == set(criteria), 'Missing criteria')
    return sorted(results, key=lambda r: list(criteria).index(r['criterion_id']))
