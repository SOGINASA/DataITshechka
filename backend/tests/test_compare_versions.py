"""Comparable rubrics and fixed denominators for the real full-run harness."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compare_ml_versions', ROOT / 'scripts/compare_ml_versions.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def test_full_private_release_has_score_parity_and_no_gold_in_model_input(tmp_path):
    if not (ROOT / 'data/releases/dev-reviewed-v1/manifest.json').exists():
        pytest.skip('Private frozen release not available')
    rows, inputs, gold, rubrics, contract = comparison.prepare(tmp_path)
    assert len(rows) == len(inputs) == len(gold) == 65
    assert contract['reference_decisions'] == 520
    assert contract['independent_test'] is False
    for row in rows:
        d = inputs[row['conversation_id']]
        assert not ({'labels', 'results', 'reason', 'assessment_context', 'audio_url'} & set(d))
        assert [m['id'] for m in d['messages']] == [t['turn_id'] for t in row['transcript']]
        assert comparison.ml2_summary(gold[d['conversation_id']]['results'], rubrics[row['checklist_hash']])['final_score'] == gold[d['conversation_id']]['summary']['final_score']
    assert comparison.prepare(tmp_path)[-1] == contract


def test_comparison_keeps_errors_and_unknowns_and_pairs_mae(tmp_path):
    results = [{'criterion_id': 'contact', 'status': 'pass', 'value': True, 'answer_type': 'binary', 'weight': 100},
               {'criterion_id': 'gross_errors', 'status': 'pass', 'value': False, 'answer_type': 'flag', 'weight': 0}]
    rows = [{'conversation_id': cid, 'language': 'RU', 'channel': 'agent chat'} for cid in ['a', 'b']]
    gold = {cid: {'results': results, 'summary': {'final_score': 100}, 'audio_reviewed': False} for cid in ['a', 'b']}
    okay = {'state': 'ok', 'results': results, 'summary': {'final_score': 100}}
    unknown = deepcopy(okay)
    unknown['results'][0].update(status='needs_review', value=None)
    unknown['summary']['final_score'] = None
    for name, records in [('local-v1', {'a': okay, 'b': {'state': 'error'}}), ('ml2-8b', {'a': unknown, 'b': okay})]:
        comparison.write_json(tmp_path / name / 'predictions.json', records)
    with patch.object(comparison, 'prepare', return_value=(rows, {}, gold, {}, {})):
        measured = comparison.report(tmp_path, require_complete=True)
    assert measured['complete'] is True
    assert measured['a']['breakdown']['all']['accuracy'] == 0.5
    assert measured['b']['breakdown']['all']['accuracy'] == 0.75
    assert measured['paired_decisions']['only_a_correct'] == 1
    assert measured['paired_decisions']['only_b_correct'] == 2
    assert measured['score_pairs_with_both_complete'] == 0
    assert measured['paired_score_mae_a'] is None and measured['paired_score_mae_b'] is None


def test_final_report_refuses_unfinished_run(tmp_path):
    rows = [{'conversation_id': 'a', 'language': 'RU', 'channel': 'agent chat'}]
    with patch.object(comparison, 'prepare', return_value=(rows, {}, {'a': {}}, {}, {})):
        with pytest.raises(ValueError, match='Both full'):
            comparison.report(tmp_path, require_complete=True)
