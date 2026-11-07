"""Explainable baseline, not a trained model or an official broker scoring rubric."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

ENGINE = 'keyword-baseline-v1'


def evaluate(conversation, checklist):
    results = []
    for criterion in checklist.criteria:
        rule = criterion['rule']
        item = {'criterion_id': criterion['id'], 'title': criterion['title'],
                'weight': criterion['weight'], 'critical': criterion['critical'],
                'status': 'needs_review', 'source': 'baseline', 'evidence': [],
                'explanation': 'Критерий требует ручной проверки.'}
        item.update({key: deepcopy(criterion.get(key, default)) for key, default in (
            ('answer_type', 'binary'), ('allow_na', True), ('na_condition', ''),
            ('scale', []), ('section', ''), ('require_evidence', False))})
        item['value'] = None
        if rule['type'] in ('contains_any', 'contains_none'):
            terms = rule['terms'].get(conversation.language)
            messages = [m for m in conversation.messages if rule['speaker'] in ('any', m['speaker'])]
            if not terms:
                item['explanation'] = 'Для языка диалога не настроены правила; нужна ручная проверка.'
            elif not messages:
                item['explanation'] = 'Нет реплик нужного участника; нужна ручная проверка.'
            else:
                for message in messages:
                    matches = [term for term in terms if term.casefold() in message['text'].casefold()]
                    if matches:
                        item['evidence'].append({'message_id': message['id'], 'quote': message['text'],
                                                 'start_ms': message['start_ms'], 'end_ms': message['end_ms'],
                                                 'matched_terms': matches})
                found = bool(item['evidence'])
                passed = found if rule['type'] == 'contains_any' else not found
                item['status'] = 'pass' if passed else 'fail'
                item['value'] = passed
                item['reviewed_range'] = {'start_message_id': messages[0]['id'], 'end_message_id': messages[-1]['id']}
                item['explanation'] = (
                    f'Правило {rule["type"]}: ' + ('найдены' if found else 'не найдены') +
                    ' настроенные фразы в репликах. Это поиск подстрок, без понимания контекста; подтвердите вручную.')
        results.append(item)
    return results


def decimal(value):
    return Decimal(str(value))


def rounded(value):
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def earned(item):
    if item['status'] not in ('pass', 'fail', 'scored'):
        return None
    weight = decimal(item['weight'])
    if item.get('answer_type') == 'scale':
        return weight * decimal(item['value']) / decimal(max(step['value'] for step in item['scale']))
    return weight if item['status'] == 'pass' else Decimal(0)


def score_summary(results):
    applicable = [r for r in results if r['status'] != 'not_applicable' and r['weight'] > 0]
    assessed = [r for r in applicable if earned(r) is not None]
    denominator = sum((decimal(r['weight']) for r in assessed), Decimal(0))
    applicable_weight = sum((decimal(r['weight']) for r in applicable), Decimal(0))
    points = sum((earned(r) for r in assessed), Decimal(0))
    score = rounded(100 * points / denominator) if denominator else None
    incomplete = any(r['status'] == 'needs_review' for r in applicable)
    return {'score': score, 'final_score': None if incomplete else score, 'score_is_partial': incomplete,
            'coverage': rounded(100 * denominator / applicable_weight) if applicable_weight else None,
            'applicable_weight': float(applicable_weight)}


def present_results(results):
    output = deepcopy(results)
    denominator = sum((decimal(r['weight']) for r in results if r['status'] != 'not_applicable'), Decimal(0))
    for item in output:
        points = earned(item)
        item['points'] = rounded(points) if points is not None else None
        item['effective_weight'] = rounded(100 * decimal(item['weight']) / denominator) if denominator and item['status'] != 'not_applicable' else 0
        item['effective_points'] = rounded(100 * points / denominator) if denominator and points is not None else None
    return output


def summarize(results):
    flags = [r for r in results if r.get('answer_type') == 'flag']
    detected = any(r['status'] == 'fail' for r in flags)
    sections = list(dict.fromkeys(r.get('section') for r in results if r.get('section')))
    return {**score_summary(results),
            'needs_review': any(r['source'] != 'human' or r['status'] == 'needs_review' for r in results),
            'critical_failures': [r['criterion_id'] for r in results if r['critical'] and r['status'] == 'fail'],
            'gross_error_detected': detected if detected or (flags and all(r['status'] != 'needs_review' for r in flags)) else None,
            'sections': [{'name': section, **score_summary([r for r in results if r.get('section') == section])} for section in sections],
            'counts': {status: sum(r['status'] == status for r in results)
                       for status in ('pass', 'fail', 'scored', 'not_applicable', 'needs_review')}}


def apply_overrides(results, overrides, messages=(), source='human'):
    from services.validation import fail, number
    updated, changes = deepcopy(results), []
    by_id = {r['criterion_id']: r for r in updated}
    for override in overrides:
        if override['criterion_id'] not in by_id:
            fail('Критерий отсутствует в этой оценке: ' + override['criterion_id'])
        item = by_id[override['criterion_id']]
        before = deepcopy(item)
        status, value = override.get('status'), override.get('value')
        kind = item.get('answer_type', 'binary')
        if status in ('not_applicable', 'needs_review'):
            if value is not None:
                fail('Для N/A и needs_review value должен отсутствовать или быть null.')
            if status == 'not_applicable' and not item.get('allow_na', True):
                fail('Для этого критерия N/A запрещён.')
        elif kind == 'scale':
            number(value, 'value', 0, 1000)
            if value not in [step['value'] for step in item['scale']] or status not in (None, 'scored'):
                fail('Выберите допустимую ступень шкалы; status должен быть scored.')
            status = 'scored'
        else:
            if 'value' not in override and status in ('pass', 'fail'):
                value = status == ('fail' if kind == 'flag' else 'pass')
            if type(value) is not bool:
                fail('Для binary/flag value должен быть boolean.')
            expected = ('fail' if value else 'pass') if kind == 'flag' else ('pass' if value else 'fail')
            if status is not None and status != expected:
                fail('status противоречит value.')
            status = expected
        item.update(status=status, value=value, explanation=override['explanation'], source=source)
        by_message = {m['id']: m for m in messages}
        if 'evidence_message_ids' in override:
            if any(mid not in by_message for mid in override['evidence_message_ids']):
                fail('Доказательство ссылается на отсутствующую реплику.')
            item['evidence'] = [{'message_id': mid, 'quote': by_message[mid]['text'],
                                 'start_ms': by_message[mid].get('start_ms'), 'end_ms': by_message[mid].get('end_ms'),
                                 'matched_terms': []} for mid in dict.fromkeys(override['evidence_message_ids'])]
        if 'reviewed_range' in override:
            span = override['reviewed_range']
            positions = {m['id']: i for i, m in enumerate(messages)}
            if any(mid not in positions for mid in span.values()) or positions[span['start_message_id']] > positions[span['end_message_id']]:
                fail('Некорректный проверенный участок диалога.')
            item['reviewed_range'] = span
        if item.get('require_evidence') and status != 'needs_review' and not (item['evidence'] or item.get('reviewed_range')):
            fail('Укажите evidence_message_ids или reviewed_range для обоснования оценки.')
        changes.append({'criterion_id': item['criterion_id'], 'before': before, 'after': deepcopy(item)})
    return updated, changes
