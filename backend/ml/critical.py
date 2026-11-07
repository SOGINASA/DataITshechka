"""Rare-violation diagnostics. Binary decisions are not calibrated probabilities."""


def audit(references, predictions, criterion_id='gross_errors'):
    counts = {'positive': 0, 'negative': 0, 'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0,
              'unresolved_positive': 0, 'unresolved_negative': 0}
    queue = []
    for cid, gold in references.items():
        labels = [r for r in gold['results'] if r['criterion_id'] == criterion_id]
        if len(labels) != 1 or labels[0]['status'] not in ('pass', 'fail'):
            raise ValueError('Expected one judged binary violation reference per dialogue')
        label = labels[0]
        if label.get('answer_type') != 'flag' or type(label['value']) is not bool:
            raise ValueError('Expected a flag reference with boolean value')
        positive = label['value']
        if (label['status'] == 'fail') != positive:
            raise ValueError('Reference flag polarity mismatch')
        counts['positive' if positive else 'negative'] += 1
        record = predictions.get(cid, {})
        actual = next((r for r in record.get('results', []) if r['criterion_id'] == criterion_id), None)
        judged = bool(record.get('state') == 'ok' and actual and actual['status'] in ('pass', 'fail')
                      and type(actual.get('value')) is bool)
        if judged and (actual['status'] == 'fail') != actual['value']:
            raise ValueError('Prediction flag polarity mismatch')
        if not judged:
            outcome = 'unresolved_positive' if positive else 'unresolved_negative'
        else:
            outcome = ('tp' if actual['value'] else 'fn') if positive else ('fp' if actual['value'] else 'tn')
        counts[outcome] += 1
        # Confirmed flags stay intact; unknown subtype decisions must be reviewed before training.
        if outcome != 'tn':
            queue.append({'conversation_id': cid, 'outcome': outcome, 'reference_violation': positive,
                          'model_violation': actual['value'] if judged else None,
                          'reference_explanation': label['explanation'],
                          'reference_evidence_ids': [e['message_id'] for e in label.get('evidence', [])],
                          'subtype_annotation_status': 'not_annotated',
                          'subtypes': {k: {'verdict': None, 'evidence_message_ids': []} for k in
                                       ('insult', 'private_paid_service', 'confidential_disclosure')}})
    total = counts['positive'] + counts['negative']
    tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
    missed = fn + counts['unresolved_positive']
    priority = {'fn': 0, 'unresolved_positive': 1, 'fp': 2, 'unresolved_negative': 3, 'tp': 4}
    queue.sort(key=lambda r: (priority[r['outcome']], r['conversation_id']))
    return {'counts': counts, 'dialogues': total,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall_including_unresolved': tp / counts['positive'] if counts['positive'] else None,
            'f1_including_unresolved': 2 * tp / (2 * tp + fp + missed) if 2 * tp + fp + missed else None,
            'f2_including_unresolved': 5 * tp / (5 * tp + fp + 4 * missed) if 5 * tp + fp + 4 * missed else None,
            'always_no_violation_accuracy': counts['negative'] / total if total else None,
            'one_positive_changes_recall_by': 1 / counts['positive'] if counts['positive'] else None,
            'calibrated_probabilities_available': False, 'review_queue': queue,
            'limitations': ['Development data; no independent generalization estimate.',
                            'Subtype fields are unlabelled proposals, not confirmed annotations.',
                            'No probability may be inferred by subtracting accuracy or anomaly score from one.']}
