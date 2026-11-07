"""Revalidate saved model outputs with current logic, without any inference calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
from local_improvement_experiment import prepare
from ml.dataset import sha256
from ml.run import write_json
from ml.metrics import measure
from services import decision_reasoning
from services.assessment_logic import refinement_criteria
from services.evaluation import evaluate, apply_overrides, summarize
from services.validation import assessment_item
from types import SimpleNamespace


def paired(rows, gold, candidate, baseline):
    values = []
    for row in rows:
        cid = row['conversation_id']
        scores = (candidate[cid].get('summary', {}).get('final_score'),
                  baseline[cid].get('summary', {}).get('final_score'), gold[cid]['summary']['final_score'])
        if all(v is not None for v in scores):
            values.append(scores)
    return {'pairs': len(values), 'candidate_mae': sum(abs(a - g) for a, b, g in values) / len(values) if values else None,
            'baseline_mae': sum(abs(b - g) for a, b, g in values) / len(values) if values else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/runs/local-logic-targeted-20261107-v3')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/runs/local-logic-replay-20261107-v4')
    args = parser.parse_args()
    rows, prepared, gold, _ = prepare()
    source_manifest = json.loads((args.source / 'run.json').read_text(encoding='utf-8'))['configuration']
    ids = source_manifest['groups']['logic-targeted']
    if source_manifest['release_manifest_sha256'] != sha256(ROOT / 'data/releases/dev-reviewed-v1/manifest.json'):
        raise ValueError('Replay release mismatch')
    base_path = ROOT / 'data/runs/local-improvements-20261107-guided-v1/decision-guided/predictions.json'
    if source_manifest['cached_guided_base_sha256'] != sha256(base_path):
        raise ValueError('Cached base changed')
    guided = json.loads(base_path.read_text(encoding='utf-8'))
    legacy = json.loads((ROOT / 'data/runs/full-compare-20261107/local-v1/predictions.json').read_text(encoding='utf-8'))
    source_predictions = json.loads((args.source / 'logic-targeted/predictions.json').read_text(encoding='utf-8'))
    if set(ids) != set(source_predictions):
        raise ValueError('Replay requires every attempted source record')
    selected = [next(row for row in rows if row['conversation_id'] == cid) for cid in ids]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Replay output directory must be empty')
    sources = [Path(__file__), ROOT / 'backend/services/decision_reasoning.py', ROOT / 'backend/services/assessment_logic.py',
               ROOT / 'backend/services/decision_format.py', ROOT / 'backend/services/evaluation.py',
               ROOT / 'backend/services/validation.py', ROOT / 'backend/ml/dataset.py', ROOT / 'backend/ml/metrics.py']
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'inference_calls_this_run': 0,
                'source_run_manifest_sha256': sha256(args.source / 'run.json'),
                'cached_guided_base_sha256': sha256(base_path), 'logic_version': decision_reasoning.VERSION,
                'code_sha256': {str(p.relative_to(ROOT)): sha256(p) for p in sources},
                'response_sha256': {cid: sha256(args.source / 'logic-targeted' / (cid + '.response.json')) for cid in ids},
                'independent_test': False, 'conversation_ids': ids}
    write_json(output / 'run.json', manifest)
    for path in sources:
        target = output / 'code' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    predictions = {}
    for cid in ids:
        c, full_k = prepared[cid]
        criteria = refinement_criteria(full_k.criteria)
        k = SimpleNamespace(**{**vars(full_k), 'criteria': criteria})
        envelope = json.loads((args.source / 'logic-targeted' / (cid + '.response.json')).read_text(encoding='utf-8'))
        try:
            if envelope.get('done') is not True or envelope.get('done_reason') == 'length':
                raise ValueError('Incomplete saved model output')
            overrides, facts = decision_reasoning.decode(json.loads(envelope['content']), criteria, c.messages)
            initial = evaluate(c, k)
            for row in initial:
                row['require_evidence'] = True
            refined, _ = apply_overrides(initial, [assessment_item(r) for r in overrides], c.messages, source='model')
            by_id = {r['criterion_id']: r for r in refined}
            results = [by_id.get(r['criterion_id'], r) for r in guided[cid]['results']]
            predictions[cid] = {'state': 'ok', 'conversation_id': cid, 'results': results, 'summary': summarize(results),
                'engine': 'replayed:logic-targeted:qwen3:4b', 'metadata': {'assessment_facts': facts,
                'inference_calls_this_run': 0, 'postprocessor_version': decision_reasoning.VERSION}}
        except (ValueError, KeyError, TypeError) as exc:
            predictions[cid] = {'state': 'error', 'conversation_id': cid, 'error': str(exc)}
    references = {cid: gold[cid] for cid in ids}
    measured = measure(selected, references, predictions)
    report = {'complete': True, 'candidate': measured, 'original': measure(selected, references, legacy),
              'previous_guided': measure(selected, references, guided),
              'paired_vs_original': paired(selected, references, predictions, legacy),
              'paired_vs_previous_guided': paired(selected, references, predictions, guided),
              'inference_calls_this_run': 0,
              'limitations': ['Reprocessing saved model responses; no new model inference.',
                              'Development sample only; no independent test.',
                              'Incomplete scores remain incomplete; compare score coverage and paired MAE together.']}
    write_json(output / 'references.json', references)
    write_json(output / 'predictions.json', predictions)
    write_json(output / 'report.json', report)
    print(json.dumps({'completed': measured['completed'], 'errors': measured['errors'],
                      'correct': measured['breakdown']['all'], 'score_coverage': measured['score_comparable_dialogues'],
                      'paired_vs_original': report['paired_vs_original'], 'paired_vs_previous_guided': report['paired_vs_previous_guided']}))


if __name__ == '__main__':
    main()
