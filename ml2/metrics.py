"""Fixed denominators and paired comparisons; failures never vanish from accuracy."""
from collections import Counter, defaultdict
from .contracts import require, digest
from .scoring import summarize


def valid_answer(item, c):
    if not isinstance(item, dict):
        return False
    s, v = item.get('status'), item.get('value')
    if s == 'not_applicable':
        return c['allow_na'] and v is None
    if s == 'needs_review':
        return v is None
    if c['answer_type'] == 'scale':
        return s == 'scored' and type(v) in (int, float) and v in [step['value'] for step in c['scale']]
    expected = ('fail' if v else 'pass') if c['answer_type'] == 'flag' else ('pass' if v else 'fail')
    return type(v) is bool and s == expected


def same(gold, prediction):
    return (prediction is not None and prediction.get('status') == gold['status'] and
            type(prediction.get('value')) is type(gold['value']) and prediction['value'] == gold['value']) or (
        prediction is not None and gold['status'] == prediction.get('status') == 'scored' and
        type(prediction.get('value')) in (int, float) and prediction['value'] == gold['value'])


def index_records(rows):
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('conversation_id'), str), 'Invalid evaluation record')
        cid = row['conversation_id']
        require(cid not in result, 'Duplicate evaluation conversation_id')
        result[cid] = row
    return result


def report(golds, predictions, checklist):
    golds, predictions = index_records(golds), index_records(predictions)
    require(bool(golds), 'No reference labels')
    require(not (set(predictions) - set(golds)), 'Predictions include conversations outside reference set')
    criteria = {c['id']: c for c in checklist['criteria']}
    rhash = digest(checklist)
    total = correct = complete = 0
    counts = defaultdict(Counter)
    slices = defaultdict(Counter)
    confusion = defaultdict(Counter)
    misses, scores, comparisons = [], [], []
    durations, per_dialog = [], []
    for cid, gold in golds.items():
        require(gold.get('rubric_hash') == rhash, 'Reference rubric hash mismatch')
        require(isinstance(gold.get('conversation_hash'), str) and len(gold['conversation_hash']) == 64, 'Reference needs input hash')
        require(gold.get('label_source') in ('human_reviewed', 'organizer_ground_truth', 'synthetic_test'), 'Reference needs label provenance')
        require(isinstance(gold.get('results'), list) and bool(gold['results']), 'Reference results missing')
        gs = {r['criterion_id']: r for r in gold['results']}
        require(len(gs) == len(gold['results']) and set(gs) <= set(criteria), 'Invalid reference criterion IDs')
        require(all(valid_answer(r, criteria[k]) and r['status'] != 'needs_review' for k, r in gs.items()), 'Reference must contain resolved, valid labels only')
        pred = predictions.get(cid)
        ps = {}
        if pred:
            prov = pred.get('provenance', {})
            require(prov.get('rubric_hash') == rhash and prov.get('conversation_hash') == gold['conversation_hash'], 'Prediction input/rubric mismatch')
            if pred.get('status') == 'ok':
                rows = pred.get('results', [])
                require(isinstance(rows, list) and all(isinstance(r, dict) and isinstance(r.get('criterion_id'), str) for r in rows), 'Invalid prediction results')
                ps = {r['criterion_id']: r for r in rows}
                require(len(ps) == len(rows) and set(ps) <= set(criteria), 'Invalid prediction criterion IDs')
                ps = {k: r for k, r in ps.items() if valid_answer(r, criteria[k])}
            duration = prov.get('elapsed_seconds')
            if type(duration) in (int, float) and 0 <= duration < 1e9:
                durations.append(duration)
        resolved = set(ps) == set(criteria) and all(r['status'] != 'needs_review' for r in ps.values())
        complete += resolved
        dc = 0
        for k, g in gs.items():
            p = ps.get(k)
            ok = same(g, p)
            total += 1
            correct += ok
            dc += ok
            counts[k]['total'] += 1
            counts[k]['correct'] += ok
            if p is None:
                counts[k]['missing_or_invalid'] += 1
            elif p['status'] == 'needs_review':
                counts[k]['needs_review'] += 1
            label = lambda r: 'missing_or_invalid' if r is None else (r['status'] if r['value'] is None else str(r['value']))
            confusion[k][label(g) + ' -> ' + label(p)] += 1
            if not ok:
                misses.append({'conversation_id': cid, 'criterion_id': k, 'expected': label(g), 'actual': label(p)})
            comparisons.append({'conversation_id': cid, 'criterion_id': k, 'correct': bool(ok)})
            if criteria[k]['answer_type'] == 'flag' and g['status'] != 'not_applicable':
                actual = p is not None and p['status'] != 'needs_review' and p['value'] is True
                counts[k]['tp'] += g['value'] is True and actual
                counts[k]['fp'] += g['value'] is False and actual
                counts[k]['fn'] += g['value'] is True and not actual
        for key in ('language', 'channel'):
            sk = f'{key}:{gold.get(key, "unknown")}'
            slices[sk]['total'] += len(gs)
            slices[sk]['correct'] += dc
        per_dialog.append({'conversation_id': cid, 'correct': dc, 'total': len(gs)})
        if set(gs) == set(criteria) and set(ps) == set(criteria):
            gscore = summarize(list(gs.values()), checklist)['final_score']
            pscore = summarize(list(ps.values()), checklist)['final_score']
            if gscore is not None and pscore is not None:
                scores.append(abs(gscore - pscore))
    enrich = lambda c: {**dict(c), 'accuracy': c['correct'] / c['total'] if c['total'] else None}
    by_criterion = {k: enrich(v) for k, v in counts.items()}
    for k, v in by_criterion.items():
        if criteria[k]['answer_type'] == 'flag':
            tp, fp, fn = (v.get(x, 0) for x in ('tp', 'fp', 'fn'))
            v.update(precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None)
    return {'reference_hash': digest(list(golds.values())), 'rubric_hash': rhash,
            'label_sources': sorted({g['label_source'] for g in golds.values()}),
            'dialogues': len(golds), 'decisions': total, 'correct': correct, 'accuracy': correct / total,
            'macro_criterion_accuracy': sum(v['accuracy'] for v in by_criterion.values()) / len(by_criterion),
            'complete_dialogues': complete, 'complete_fraction': complete / len(golds),
            'score_mae': sum(scores) / len(scores) if scores else None, 'score_pairs': len(scores),
            'mean_seconds': sum(durations) / len(durations) if durations else None,
            'timed_dialogues': len(durations), 'by_criterion': by_criterion,
            'slices': {k: enrich(v) for k, v in slices.items()},
            'confusion': {k: dict(v) for k, v in confusion.items()}, 'errors': misses,
            'paired_decisions': comparisons, 'per_dialog': per_dialog}


def compare(golds, first, second, checklist):
    a, b = report(golds, first, checklist), report(golds, second, checklist)
    pairs = []
    for x, y in zip(a['paired_decisions'], b['paired_decisions']):
        if x['correct'] != y['correct']:
            pairs.append({'conversation_id': x['conversation_id'], 'criterion_id': x['criterion_id'],
                          'a_correct': x['correct'], 'b_correct': y['correct']})
    return {'a': a, 'b': b, 'accuracy_delta_b_minus_a': b['accuracy'] - a['accuracy'],
            'changed_correctness': pairs,
            'note': 'Same reference and denominators. No automatic winner: inspect C8, N/A, coverage, evidence and latency.'}
