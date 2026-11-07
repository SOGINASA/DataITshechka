"""Keep errors and abstentions in the denominator; development metrics only."""
from collections import defaultdict
from math import ceil
from statistics import mean, median


def measure(inputs, references, predictions):
    buckets = defaultdict(lambda: {'expected': 0, 'correct': 0, 'abstained_or_missing': 0})
    mismatches, score_errors, durations = [], [], []
    violations = defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'unjudged': 0})
    scales = defaultdict(list)
    na_counts = {'reference_na': 0, 'predicted_na': 0, 'correct_na': 0}
    tokens = {'prompt_eval_count': 0, 'eval_count': 0, 'responses_with_token_counts': 0}
    for source in inputs:
        cid = source['conversation_id']
        prediction = predictions.get(cid, {})
        predicted = {x['criterion_id']: x for x in prediction.get('results', [])}
        gold = references[cid]
        for label in gold['results']:
            actual = predicted.get(label['criterion_id'])
            missing = actual is None or actual['status'] == 'needs_review'
            correct = bool(not missing and (actual['status'], actual['value']) == (label['status'], label['value']))
            na_counts['reference_na'] += label['status'] == 'not_applicable'
            na_counts['predicted_na'] += bool(actual and actual['status'] == 'not_applicable')
            na_counts['correct_na'] += correct and label['status'] == 'not_applicable'
            if label['answer_type'] in ('binary', 'flag') and label['status'] in ('pass', 'fail'):
                stats = violations[label['criterion_id']]
                positive = label['status'] == 'fail'
                predicted_positive = bool(actual and actual['status'] == 'fail')
                stats['tp'] += positive and predicted_positive
                stats['fp'] += not positive and predicted_positive
                stats['fn'] += positive and not predicted_positive
                stats['unjudged'] += missing or bool(actual and actual['status'] == 'not_applicable')
            if label['answer_type'] == 'scale' and actual and label['status'] == actual['status'] == 'scored':
                scales[label['criterion_id']].append(abs(actual['value'] - label['value']))
            for key in ('all', 'criterion:' + label['criterion_id'], 'language:' + source['language'],
                        'channel:' + source['channel'], 'reference_audio:' + str(gold['audio_reviewed'])):
                row = buckets[key]
                row['expected'] += 1
                row['correct'] += correct
                row['abstained_or_missing'] += missing
            if not correct:
                mismatches.append({'conversation_id': cid, 'criterion_id': label['criterion_id'],
                                   'expected': {'status': label['status'], 'value': label['value']},
                                   'actual': {'status': actual['status'], 'value': actual['value']} if actual else None})
        actual_score = prediction.get('summary', {}).get('final_score')
        expected_score = gold['summary']['final_score']
        if actual_score is not None and expected_score is not None:
            score_errors.append(abs(actual_score - expected_score))
        if prediction.get('elapsed_seconds') is not None:
            durations.append(prediction['elapsed_seconds'])
        metadata = prediction.get('metadata', {})
        if all(k in metadata for k in ('prompt_eval_count', 'eval_count')):
            tokens['responses_with_token_counts'] += 1
            for field in ('prompt_eval_count', 'eval_count'):
                tokens[field] += metadata[field]
    for row in buckets.values():
        row['accuracy'] = row['correct'] / row['expected'] if row['expected'] else None
    for row in violations.values():
        row['precision'] = row['tp'] / (row['tp'] + row['fp']) if row['tp'] + row['fp'] else None
        row['recall'] = row['tp'] / (row['tp'] + row['fn']) if row['tp'] + row['fn'] else None
    durations.sort()
    return {'independent_test': False, 'split': 'development', 'dialogues': len(inputs),
            'completed': sum(p.get('state') == 'ok' for p in predictions.values()),
            'errors': sum(p.get('state') == 'error' for p in predictions.values()),
            'pending': len(inputs) - len(predictions), 'breakdown': dict(buckets),
            'score_mae': mean(score_errors) if score_errors else None,
            'score_comparable_dialogues': len(score_errors),
            'latency_median_seconds': median(durations) if durations else None,
            'latency_p95_seconds': durations[ceil(0.95 * len(durations)) - 1] if durations else None,
            'violation_metrics': dict(violations), 'na_counts': na_counts,
            'scale_mae': {k: {'mae': mean(v), 'comparable': len(v)} for k, v in scales.items()},
            'token_usage': tokens,
            'mismatches': mismatches,
            'limitations': ['Human-confirmed AI preannotations; no independent holdout.',
                            'Audio was not supplied to model. Audio-reviewed references reported separately.',
                            'Evidence IDs are validated; semantic relevance needs human review.']}
