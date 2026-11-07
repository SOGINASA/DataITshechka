"""Full DEV comparison. Run from the repository root; artifacts stay in data/runs/."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]

from ml.dataset import load_release, adapt_input, adapt_rubric, adapt_reference, sha256
from ml.metrics import measure
from services.evaluation import summarize
from ml2.contracts import conversation, rubric, digest, read_json, write_json
from ml2.engine import Evaluator, EvaluationFailure, SYSTEM, PROMPT_VERSION
from ml2.provider import Ollama, Settings, ModelError
from ml2.cli import code_hash
from ml2.scoring import summarize as ml2_summary

DEFAULT = ROOT / 'data/runs/full-compare-20261107'
ARCHIVE = ROOT / 'runs/collected-tests-2026-11-07'
MODEL_DIGEST = '500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41'


def signature(messages):
    return [(m['speaker'], m['text']) for m in messages]


def prepare(output):
    release = ROOT / 'data/releases/dev-reviewed-v1'
    rows, original_refs, sources, manifest = load_release(release)
    inputs, golds, checklists = {}, {}, {}
    for row in rows:
        cid = row['conversation_id']
        c = adapt_input(row)
        k = adapt_rubric(sources[row['checklist_hash']])
        normalized = conversation({'conversation_id': cid, 'language': c.language,
                                   'channel': c.channel, 'messages': c.messages})
        checked = rubric(vars(k))
        results = adapt_reference(original_refs[cid], c, k)
        if ml2_summary(results, checked)['final_score'] != summarize(results)['final_score']:
            raise ValueError('Scoring implementations disagree on the reference')
        inputs[cid] = normalized
        checklists[row['checklist_hash']] = checked
        golds[cid] = {'results': results, 'summary': summarize(results),
                     'audio_reviewed': original_refs[cid].get('assessment_context', {}).get('audio_reviewed', False)}
    contract = {'release_manifest_sha256': sha256(release / 'manifest.json'),
                'source_fingerprint': manifest['source_fingerprint'],
                'inputs_sha256': digest(inputs), 'gold_sha256': digest(golds),
                'rubrics_sha256': digest(checklists), 'conversation_ids': list(inputs),
                'reference_decisions': sum(len(g['results']) for g in golds.values()),
                'reference_policy': 'Frozen v1; newer pending voice-v2 label is not silently substituted.',
                'comparison': 'Same full dialogue text/order/IDs and frozen rubric definitions; different engines/models/settings.',
                'independent_test': False, 'audio_supplied': False, 'knowledge_supplied': False}
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'comparison-contract.json'
    if path.exists() and read_json(path) != contract:
        raise ValueError('Comparison contract changed; choose a new output directory')
    for name, data in [('comparison-contract.json', contract), ('common-inputs.json', inputs),
                       ('common-gold.json', golds), ('common-rubrics.json', checklists)]:
        if not (output / name).exists():
            write_json(output / name, data)
    return rows, inputs, golds, checklists, contract


def audit_archive(output):
    rows, inputs, golds, _, _ = prepare(output)
    by_id = {r['conversation_id']: r for r in rows}
    records = []
    for path in sorted(ARCHIVE.glob('*/request.json')):
        request = read_json(path)
        response = read_json(path.with_name('response.json'))
        matches = [cid for cid, d in inputs.items() if
                   d['channel'] == request['channel'] and d['language'] == request['language'] and
                   signature(d['messages']) == signature(request['messages'])]
        cid = request['conversation_id']
        changes = None
        if cid in by_id:
            a, b = request['messages'], inputs[cid]['messages']
            changes = {'request_turns': len(a), 'reference_turns': len(b),
                       'changed_positions': [i + 1 for i in range(max(len(a), len(b))) if
                                             i >= len(a) or i >= len(b) or signature([a[i]]) != signature([b[i]])]}
        record = {'folder': path.parent.name, 'conversation_id': cid, 'state': response['status'],
                  'model_digest': response.get('provenance', {}).get('model_digest'),
                  'exact_dev_content_matches': matches, 'differences_from_same_id': changes,
                  'final_score': response.get('summary', {}).get('final_score'),
                  'error': response.get('error')}
        if len(matches) == 1 and response['status'] == 'ok':
            expected = golds[matches[0]]
            predicted = {r['criterion_id']: r for r in response['results']}
            record.update(reference_final_score=expected['summary']['final_score'],
                          exact_correct=sum(equal(r, predicted.get(r['criterion_id'])) for r in expected['results']),
                          expected_decisions=len(expected['results']))
        records.append(record)
    audit = {'runs': len(records), 'unique_ids': len({r['conversation_id'] for r in records}),
             'ok': sum(r['state'] == 'ok' for r in records),
             'errors': sum(r['state'] == 'error' for r in records), 'records': records,
             'limitation': 'Manual examples and edited same-ID dialogues are not interchangeable with frozen DEV. OK is structural success, not correctness.'}
    write_json(output / 'archive-audit.json', audit)
    print(f'Archive: {audit["runs"]} runs, {audit["ok"]} ok, {audit["errors"]} error; exact DEV matches: '
          f'{sum(bool(r["exact_dev_content_matches"]) for r in records)}', flush=True)


def equal(gold, actual):
    return bool(actual and actual['status'] != 'needs_review' and
                (gold['status'], gold['value']) == (actual['status'], actual['value']))


def report(output, require_complete=False):
    rows, _, gold, _, _ = prepare(output)
    a_path, b_path = output / 'local-v1/predictions.json', output / 'ml2-8b/predictions.json'
    a = read_json(a_path) if a_path.exists() else {}
    b = read_json(b_path) if b_path.exists() else {}
    if (set(a) | set(b)) - set(gold):
        raise ValueError('Unexpected conversation IDs in predictions')
    complete = len(a) == len(b) == len(rows)
    if require_complete and not complete:
        raise ValueError('Both full 65-dialogue runs are required for the final report')
    metrics_a, metrics_b = measure(rows, gold, a), measure(rows, gold, b)
    paired = Counter()
    changed = []
    paired_mae_a, paired_mae_b = [], []
    for row in rows:
        cid = row['conversation_id']
        pa = {r['criterion_id']: r for r in a.get(cid, {}).get('results', [])}
        pb = {r['criterion_id']: r for r in b.get(cid, {}).get('results', [])}
        for g in gold[cid]['results']:
            ca, cb = equal(g, pa.get(g['criterion_id'])), equal(g, pb.get(g['criterion_id']))
            paired['both_correct' if ca and cb else 'only_a_correct' if ca else 'only_b_correct' if cb else 'both_wrong_or_missing'] += 1
            if ca != cb:
                changed.append({'conversation_id': cid, 'criterion_id': g['criterion_id'],
                                'a_correct': ca, 'b_correct': cb})
        sa, sb = [p.get(cid, {}).get('summary', {}).get('final_score') for p in (a, b)]
        sg = gold[cid]['summary']['final_score']
        if sa is not None and sb is not None and sg is not None:
            paired_mae_a.append(abs(sa - sg))
            paired_mae_b.append(abs(sb - sg))
    result = {'complete': complete, 'a': metrics_a, 'b': metrics_b, 'paired_decisions': dict(paired),
              'changed_correctness': changed, 'score_pairs_with_both_complete': len(paired_mae_a),
              'paired_score_mae_a': sum(paired_mae_a) / len(paired_mae_a) if paired_mae_a else None,
              'paired_score_mae_b': sum(paired_mae_b) / len(paired_mae_b) if paired_mae_b else None,
              'accuracy_delta_b_minus_a': metrics_b['breakdown']['all']['accuracy'] - metrics_a['breakdown']['all']['accuracy'],
              'limitations': ['Development only; human-confirmed original AI labels, no independent holdout.',
                              'Different models and thinking modes: comparison of full candidates, not isolated code quality.',
                              'Same frozen v1 rubric; archive ML2 native rubrics differ and were not substituted into gold.',
                              'Audio-reviewed references and transcript-only inference reported separately.']}
    write_json(output / 'comparison-metrics.json', result)
    return result


def run_ml2(output, wait_local, resume):
    rows, inputs, _, checklists, contract = prepare(output)
    settings = {channel: Settings(model='qwen3:8b', context=ctx, output_tokens=4096,
                                  timeout=600, seed=7, think=True)
                for channel, ctx in [('chat', 28672), ('call', 45056)]}
    providers = {channel: Ollama(cfg) for channel, cfg in settings.items()}
    identity = providers['chat'].identity()
    if identity['digest'] != MODEL_DIGEST:
        raise ValueError('Installed qwen3:8b digest differs from the supplied archive; comparison refused')
    profile = ROOT / '.tools/ollama-runtime.json'
    runtime = read_json(profile) if profile.exists() else None
    if runtime:
        runtime = {k: runtime[k] for k in ('flash_attention', 'kv_cache_type')}
    cfg = {'contract': contract, 'model': identity, 'settings_by_channel': {k: vars(v) for k, v in settings.items()},
           'runtime': runtime, 'ml2_code_hash': code_hash(), 'prompt_version': PROMPT_VERSION,
           'prompt_hash': digest(SYSTEM), 'driver_sha256': sha256(Path(__file__)),
           'note': 'Original 8B digest, think=true, seed=7, output=4096, timeout=600, one ML2 repair. Context enlarged to fit identical full frozen rubrics and transcripts; no gold sent.'}
    folder = output / 'ml2-8b'
    path = folder / 'manifest.json'
    if path.exists():
        if not resume or read_json(path)['configuration'] != cfg:
            raise ValueError('ML2 run exists or configuration changed; choose a new directory')
    else:
        folder.mkdir(parents=True, exist_ok=False)
        write_json(path, {'created_at': datetime.now(timezone.utc).isoformat(), 'configuration': cfg})
        for source in [* (ROOT / 'ml2').glob('*.py'), * (ROOT / 'ml2/prompts').glob('*.txt')]:
            destination = folder / 'code/ml2' / source.relative_to(ROOT / 'ml2')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(__file__, folder / 'code/compare_ml_versions.py')
    if wait_local:
        while True:
            local = output / 'local-v1/predictions.json'
            saved = read_json(local) if local.exists() else {}
            if set(saved) == set(inputs):
                break
            print(f'Waiting for exclusive GPU: local saved {len(saved)}/{len(inputs)}', flush=True)
            time.sleep(45)
    predictions_path = folder / 'predictions.json'
    predictions = read_json(predictions_path) if predictions_path.exists() else {}
    if set(predictions) - set(inputs):
        raise ValueError('Unexpected saved IDs')
    evaluators = {(h, channel): Evaluator(providers[channel], checklists[h])
                  for h, channel in {(r['checklist_hash'], inputs[r['conversation_id']]['channel']) for r in rows}}
    for index, row in enumerate(rows, 1):
        cid = row['conversation_id']
        if cid in predictions:
            continue
        print(f'ML2 [{index}/{len(rows)}] {cid}', flush=True)
        started = time.monotonic()
        try:
            native = evaluators[(row['checklist_hash'], inputs[cid]['channel'])].evaluate(inputs[cid])
            prediction = {'state': 'ok', 'results': native['results'], 'summary': native['summary'],
                          'provenance': native['provenance']}
            attempts = native['provenance']['attempts']
        except EvaluationFailure as exc:
            attempts = exc.attempts
            prediction = {'state': 'error', 'error': str(exc), 'results': [], 'attempts': attempts}
        usage = Counter()
        for attempt in attempts:
            usage.update(attempt.get('usage', {}))
        prediction.update(conversation_id=cid, elapsed_seconds=round(time.monotonic() - started, 3),
                          engine='ml2:ollama:qwen3:8b', metadata={'calls': len(attempts), **dict(usage)})
        predictions[cid] = prediction
        write_json(predictions_path, predictions)
        report(output)
        print(f'  {prediction["state"]}, {prediction["elapsed_seconds"]}s, attempts={len(attempts)}', flush=True)
    final = report(output, require_complete=True)
    print('Complete: A', final['a']['breakdown']['all'], 'B', final['b']['breakdown']['all'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run-ml2', 'report'])
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--wait-local', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output)
        audit_archive(args.output)
    elif args.action == 'report':
        r = report(args.output, require_complete=True)
        print(json.dumps({'a': r['a']['breakdown']['all'], 'b': r['b']['breakdown']['all'], 'paired': r['paired_decisions']}))
    else:
        run_ml2(args.output, args.wait_local, args.resume)


if __name__ == '__main__':
    main()
