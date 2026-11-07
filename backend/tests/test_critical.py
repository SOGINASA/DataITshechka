from copy import deepcopy

import pytest

from ml.critical import audit


def label(positive):
    return {'criterion_id': 'gross_errors', 'answer_type': 'flag', 'status': 'fail' if positive else 'pass',
            'value': positive, 'explanation': 'Reference', 'evidence': []}


def test_rare_errors_and_unresolved_predictions_are_reported_separately():
    refs = {cid: {'results': [label(positive)]} for cid, positive in
            [('tp', True), ('fn', True), ('missing', True), ('fp', False), ('tn', False), ('error', False)]}
    predictions = {cid: {'state': 'ok', 'results': [label(positive)]} for cid, positive in
                   [('tp', True), ('fn', False), ('fp', True), ('tn', False)]}
    predictions['error'] = {'state': 'error'}
    report = audit(refs, predictions)
    assert report['counts'] == {'positive': 3, 'negative': 3, 'tp': 1, 'fn': 1, 'fp': 1, 'tn': 1,
                                'unresolved_positive': 1, 'unresolved_negative': 1}
    assert report['precision'] == .5
    assert report['recall_including_unresolved'] == 1 / 3
    assert report['f2_including_unresolved'] == 5 / 14
    assert report['always_no_violation_accuracy'] == .5
    assert report['calibrated_probabilities_available'] is False
    assert report['review_queue'][0]['conversation_id'] == 'fn'
    assert all(r['subtype_annotation_status'] == 'not_annotated' for r in report['review_queue'])
    assert all(s['verdict'] is None for r in report['review_queue'] for s in r['subtypes'].values())


def test_zero_positives_does_not_invent_recall_or_precision():
    report = audit({'a': {'results': [label(False)]}}, {'a': {'state': 'ok', 'results': [label(False)]}})
    assert report['precision'] is None and report['recall_including_unresolved'] is None
    assert report['one_positive_changes_recall_by'] is None
    assert report['always_no_violation_accuracy'] == 1


def test_polarity_mismatches_are_not_silently_scored():
    bad = label(True)
    bad['status'] = 'pass'
    with pytest.raises(ValueError, match='polarity'):
        audit({'a': {'results': [bad]}}, {})
    with pytest.raises(ValueError, match='polarity'):
        audit({'a': {'results': [label(True)]}}, {'a': {'state': 'ok', 'results': [bad]}})
