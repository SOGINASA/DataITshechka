"""Bounded local diagnostics: schema ordering, single decisions, focused gross errors."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from ml.dataset import load_release, adapt_input, adapt_rubric, adapt_reference, sha256
from ml.run import choose, write_json
from ml.metrics import measure
from services.ollama import assess, AssessmentError, wire_configuration
from services.evaluation import summarize
from services.assessment_logic import refinement_criteria


def prepare():
    rows, refs, rubrics, _ = load_release(ROOT / 'data/releases/dev-reviewed-v1')
    prepared, gold = {}, {}
    for row in rows:
        cid = row['conversation_id']
        c, k = adapt_input(row), adapt_rubric(rubrics[row['checklist_hash']])
        results = adapt_reference(refs[cid], c, k)
        prepared[cid] = (c, k)
        gold[cid] = {'results': results, 'summary': summarize(results),
                     'audio_reviewed': refs[cid].get('assessment_context', {}).get('audio_reviewed', False)}
    control = choose(rows, 6, None) + [next(row for row in rows if row['channel'] == 'voice call')]
    positive = [row for row in rows if any(r['criterion_id'] == 'gross_errors' and r['value'] is True
                                         for r in gold[row['conversation_id']]['results'])]
    negative = choose([row for row in rows if row not in positive], 8, None)
    return rows, prepared, gold, {'decision': control, 'legacy-reversed': control[:3],
                                 'critical-focused': positive + negative}


def reports(folder, rows, gold, groups):
    baseline = json.loads((ROOT / 'data/runs/full-compare-20261107/local-v1/predictions.json').read_text(encoding='utf-8'))
    reports = {}
    for variant, selected in groups.items():
        path = folder / variant / 'predictions.json'
        predictions = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        reference = gold
        if variant == 'critical-focused':
            reference = {cid: {**g, 'results': [r for r in g['results'] if r['criterion_id'] == 'gross_errors'],
                                'summary': {'final_score': None}} for cid, g in gold.items()}
        pairs = []
        for source in selected:
            cid = source['conversation_id']
            scores = (baseline[cid].get('summary', {}).get('final_score'),
                      predictions.get(cid, {}).get('summary', {}).get('final_score'),
                      reference[cid]['summary']['final_score'])
            if all(value is not None for value in scores):
                pairs.append(scores)
        reports[variant] = {'complete': set(predictions) == {r['conversation_id'] for r in selected},
                            'candidate': measure(selected, reference, predictions),
                            'baseline_same_subset': measure(selected, reference,
                                {r['conversation_id']: baseline[r['conversation_id']] for r in selected}),
                            'score_pairs_with_both_complete': len(pairs),
                            'paired_score_mae_baseline': sum(abs(a - g) for a, b, g in pairs) / len(pairs) if pairs else None,
                            'paired_score_mae_candidate': sum(abs(b - g) for a, b, g in pairs) / len(pairs) if pairs else None,
                            'analysis_code_sha256': sha256(Path(__file__))}
    write_json(folder / 'report.json', reports)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/runs/local-improvements-20261107-v1')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--variants', nargs='+', choices=['decision', 'legacy-reversed', 'critical-focused', 'decision-guided', 'decision-reasoned', 'logic-targeted'])
    parser.add_argument('--extra-controls', type=int, choices=[0, 3], default=0,
                        help='Add three later language-balanced chats, selected without labels')
    args = parser.parse_args()
    rows, prepared, gold, groups = prepare()
    if args.variants:
        groups = {variant: list(groups['decision']) if variant in ('decision-guided', 'decision-reasoned', 'logic-targeted') else groups[variant]
                  for variant in args.variants}
    if args.extra_controls:
        for selected in groups.values():
            existing = {r['conversation_id'] for r in selected}
            extra = [r for r in choose(rows, 9, None) if r['conversation_id'] not in existing][:args.extra_controls]
            selected.extend(extra)
    with urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as response:
        model = next(m for m in json.load(response)['models'] if m['name'] == 'qwen3:4b')
    cached_base = None
    cached_path = ROOT / 'data/runs/local-improvements-20261107-guided-v1/decision-guided/predictions.json'
    if 'logic-targeted' in groups:
        cached_base = json.loads(cached_path.read_text(encoding='utf-8'))
        base_manifest = json.loads((cached_path.parent.parent / 'run.json').read_text(encoding='utf-8'))['configuration']
        if (base_manifest['model_digest'] != model['digest'] or base_manifest['release_manifest_sha256'] !=
                sha256(ROOT / 'data/releases/dev-reviewed-v1/manifest.json')):
            raise ValueError('Cached base uses different model/release')
        if any(cid not in cached_base or cached_base[cid]['state'] != 'ok' for cid in
               (r['conversation_id'] for r in groups['logic-targeted'])):
            raise ValueError('Targeted experiment requires saved guided-base answers for every selected ID')
    config = {'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_MODEL': 'qwen3:4b',
              'OLLAMA_TIMEOUT': 300, 'OLLAMA_NUM_CTX': 28672, 'OLLAMA_NUM_PREDICT': 4096,
              'OLLAMA_NUM_CTX_CALL': 45056, 'OLLAMA_NUM_PREDICT_CALL': 4096, 'OLLAMA_THINK': False}
    config_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in [Path(__file__), *[
        ROOT / 'backend' / name for name in ('services/ollama.py', 'services/decision_format.py', 'services/decision_guidance.py', 'services/decision_reasoning.py', 'services/assessment_logic.py',
                                            'services/evaluation.py', 'services/validation.py', 'ml/dataset.py', 'ml/metrics.py')]]}
    effective_formats = {variant: ('decision' if variant == 'critical-focused' else
                                   'decision-reasoned' if variant == 'logic-targeted' else variant) for variant in groups}
    first_c, first_k = prepared[next(iter(prepared))]
    formats = {v: wire_configuration(first_c, first_k, f) for v, f in effective_formats.items()}
    with urlopen('http://127.0.0.1:11434/api/version', timeout=5) as response:
        runtime_version = json.load(response)['version']
    configuration = {'model_digest': model['digest'], 'config': config, 'code_hashes': config_hashes,
                     'ollama_version': runtime_version,
                     'release_manifest_sha256': sha256(ROOT / 'data/releases/dev-reviewed-v1/manifest.json'),
                     'groups': {k: [r['conversation_id'] for r in v] for k, v in groups.items()},
                     'wire_versions': {v: f[2] for v, f in formats.items()},
                     'system_prompt_sha256': {v: hashlib.sha256(f[0].encode('utf-8')).hexdigest() for v, f in formats.items()},
                     'cached_guided_base_sha256': sha256(cached_path) if cached_base is not None else None,
                     'independent_test': False,
                     'limitations': ['DEV diagnostics, no training or independent holdout.',
                         'critical-focused deliberately includes all known positives and eight negatives; not natural prevalence.',
                         'Decision format changes serialization instructions only; reversed changes union order only.',
                         'Context expanded vs baseline; inputs never truncated. Different latency context budgets.',
                         'logic-targeted reuses saved guided-base answers and reassesses only recognized discovery/consultation definitions; pipeline latency/tokens include the cached first call.',
                         'No calibrated probabilities are produced.']}
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'run.json'
    if manifest.exists():
        if not args.resume or json.loads(manifest.read_text(encoding='utf-8'))['configuration'] != configuration:
            raise ValueError('Existing experiment or changed configuration')
    else:
        if any(folder.iterdir()):
            raise ValueError('Nonempty output directory')
        write_json(manifest, {'created_at': datetime.now(timezone.utc).isoformat(), 'configuration': configuration})
        for relative in config_hashes:
            target = folder / 'code' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
    try:
        for variant, selected in groups.items():
            target = folder / variant
            target.mkdir(exist_ok=True)
            path = target / 'predictions.json'
            predictions = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            for index, row in enumerate(selected, 1):
                cid = row['conversation_id']
                if cid in predictions:
                    continue
                c, k = prepared[cid]
                if variant == 'critical-focused':
                    k = SimpleNamespace(**{**vars(k), 'criteria': [r for r in k.criteria if r['id'] == 'gross_errors']})
                if variant == 'logic-targeted':
                    k = SimpleNamespace(**{**vars(k), 'criteria': refinement_criteria(k.criteria)})
                    if not k.criteria:
                        raise ValueError('No supported criterion definitions for targeted experiment')
                print(f'{variant} [{index}/{len(selected)}] {cid}', flush=True)
                captured = {}
                started = time.monotonic()
                try:
                    results, engine, metadata = assess(c, k, config, response_capture=captured,
                        wire_format=effective_formats[variant])
                    if variant == 'logic-targeted':
                        base = cached_base[cid]
                        replacements = {r['criterion_id']: r for r in results}
                        results = [replacements.get(r['criterion_id'], r) for r in base['results']]
                        metadata['refinement_calls'] = metadata['calls']
                        metadata['calls'] += base['metadata']['calls']
                        for name in ('prompt_eval_count', 'eval_count'):
                            metadata[name] = metadata.get(name, 0) + base['metadata'].get(name, 0)
                        metadata['cached_base_engine'] = base['engine']
                        metadata['cached_base_elapsed_seconds'] = base['elapsed_seconds']
                    prediction = {'state': 'ok', 'results': results, 'summary': summarize(results),
                                  'engine': engine, 'metadata': metadata}
                except AssessmentError as exc:
                    prediction = {'state': 'error', 'http_status': exc.status, 'error': str(exc)}
                elapsed = time.monotonic() - started
                if variant == 'logic-targeted':
                    elapsed += cached_base[cid]['elapsed_seconds']
                prediction.update(conversation_id=cid, elapsed_seconds=round(elapsed, 3))
                predictions[cid] = prediction
                write_json(path, predictions)
                write_json(target / (cid + '.response.json'), captured)
                reports(folder, rows, gold, groups)
                print(f'  {prediction["state"]}, {prediction["elapsed_seconds"]}s', flush=True)
                if prediction.get('http_status') == 503:
                    return
        result = reports(folder, rows, gold, groups)
        for variant, report in result.items():
            print(variant, report['candidate']['breakdown']['all'], flush=True)
    finally:
        # Release VRAM at the end or on interruption; leave the local server available.
        try:
            req = Request('http://127.0.0.1:11434/api/generate', method='POST',
                          data=json.dumps({'model': 'qwen3:4b', 'keep_alive': 0, 'stream': False}).encode(),
                          headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=15):
                pass
        except OSError:
            pass


if __name__ == '__main__':
    main()
