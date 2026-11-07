"""Incomplete scores must not silently change the comparison population."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('local_experiment_report', ROOT / 'scripts/local_improvement_experiment.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_paired_score_mae_excludes_missing_scores_from_both_sides(tmp_path, monkeypatch):
    rows = [{'conversation_id': cid, 'language': 'RU', 'channel': 'agent chat'} for cid in ('a', 'b')]
    results = [{'criterion_id': 'x', 'status': 'pass', 'value': True, 'answer_type': 'binary', 'weight': 100}]
    gold = {cid: {'results': results, 'summary': {'final_score': 100}, 'audio_reviewed': False} for cid in ('a', 'b')}
    baseline = {cid: {'state': 'ok', 'results': results, 'summary': {'final_score': score}}
                for cid, score in [('a', 80), ('b', 70)]}
    candidate = {'a': {'state': 'ok', 'results': results, 'summary': {'final_score': 90}},
                 'b': {'state': 'error'}}
    baseline_path = tmp_path / 'data/runs/full-compare-20261107/local-v1/predictions.json'
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps(baseline), encoding='utf-8')
    output = tmp_path / 'experiment'
    (output / 'decision').mkdir(parents=True)
    (output / 'decision/predictions.json').write_text(json.dumps(candidate), encoding='utf-8')
    monkeypatch.setattr(experiment, 'ROOT', tmp_path)
    report = experiment.reports(output, rows, gold, {'decision': rows})['decision']
    assert report['complete'] is True  # two attempted records, including an error
    assert report['candidate']['errors'] == 1
    assert report['candidate']['breakdown']['all']['expected'] == 2
    assert report['score_pairs_with_both_complete'] == 1
    assert report['paired_score_mae_baseline'] == 20
    assert report['paired_score_mae_candidate'] == 10
