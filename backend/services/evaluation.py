"""Explainable baseline, not a trained model or an official broker scoring rubric."""
from copy import deepcopy

ENGINE = 'keyword-baseline-v1'


def evaluate(conversation, checklist):
    results = []
    for criterion in checklist.criteria:
        rule = criterion['rule']
        item = {'criterion_id': criterion['id'], 'title': criterion['title'],
                'weight': criterion['weight'], 'critical': criterion['critical'],
                'status': 'needs_review', 'source': 'baseline', 'evidence': [],
                'explanation': 'Критерий требует ручной проверки.'}
        if rule['type'] != 'manual':
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
                item['explanation'] = (
                    f'Правило {rule["type"]}: ' + ('найдены' if found else 'не найдены') +
                    ' настроенные фразы в репликах. Это поиск подстрок, без понимания контекста; подтвердите вручную.')
        results.append(item)
    return results


def summarize(results):
    assessed = [r for r in results if r['status'] in ('pass', 'fail')]
    denominator = sum(r['weight'] for r in assessed)
    passed = sum(r['weight'] for r in assessed if r['status'] == 'pass')
    applicable = [r for r in results if r['status'] != 'not_applicable']
    applicable_weight = sum(r['weight'] for r in applicable)
    return {'score': round(100 * passed / denominator, 2) if denominator else None,
            'coverage': round(100 * denominator / applicable_weight, 2) if applicable_weight else None,
            'needs_review': any(r['source'] != 'human' or r['status'] == 'needs_review' for r in results),
            'critical_failures': [r['criterion_id'] for r in results if r['critical'] and r['status'] == 'fail'],
            'counts': {status: sum(r['status'] == status for r in results)
                       for status in ('pass', 'fail', 'not_applicable', 'needs_review')}}


def apply_overrides(results, overrides):
    from services.validation import fail
    updated, changes = deepcopy(results), []
    by_id = {r['criterion_id']: r for r in updated}
    for override in overrides:
        if override['criterion_id'] not in by_id:
            fail('Критерий отсутствует в этой оценке: ' + override['criterion_id'])
        item = by_id[override['criterion_id']]
        before = deepcopy(item)
        item.update(status=override['status'], explanation=override['explanation'], source='human')
        changes.append({'criterion_id': item['criterion_id'], 'before': before, 'after': deepcopy(item)})
    return updated, changes
