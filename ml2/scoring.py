"""Arithmetic is independent of the model; Decimal and HALF_UP at presentation only."""
from decimal import Decimal, ROUND_HALF_UP


def rounded(value):
    return float(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def summarize(results, checklist):
    by_id = {r['criterion_id']: r for r in results}
    points, weight, assessed = Decimal(0), Decimal(0), Decimal(0)
    contributions, flags = [], []
    for c in checklist['criteria']:
        r = by_id[c['id']]
        w = Decimal(str(c['weight']))
        if c['answer_type'] == 'flag':
            flags.append(None if r['status'] == 'needs_review' else r['value'])
        earned = Decimal(0) if c['answer_type'] == 'flag' else None
        if r['status'] == 'not_applicable':
            earned = Decimal(0)
        elif w:
            weight += w
            if r['status'] != 'needs_review':
                assessed += w
                earned = (w * Decimal(str(r['value'])) / Decimal(str(max(s['value'] for s in c['scale'])))) if c['answer_type'] == 'scale' else (w if r['value'] else Decimal(0))
                points += earned
        contributions.append({'criterion_id': c['id'], 'weight': c['weight'],
                              'points': rounded(earned) if earned is not None else None})
    partial = any(by_id[c['id']]['status'] == 'needs_review' and c['weight'] > 0 for c in checklist['criteria'])
    for row in contributions:
        r = by_id[row['criterion_id']]
        row['effective_weight'] = rounded(100 * Decimal(str(row['weight'])) / weight) if weight and r['status'] != 'not_applicable' else 0
    return {'final_score': rounded(100 * points / weight) if weight and not partial else None,
            'score_is_partial': partial, 'coverage': rounded(100 * assessed / weight) if weight else None,
            'applicable_weight': float(weight), 'points': rounded(points), 'contributions': contributions,
            'gross_error_detected': True if True in flags else (False if flags and all(f is False for f in flags) else None),
            'unresolved_criteria': [r['criterion_id'] for r in results if r['status'] == 'needs_review']}
