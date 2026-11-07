"""Run from backend: python -m ml.run --help. Never write model results into gold."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.request import urlopen

from dotenv import load_dotenv

from ml.dataset import load_release, adapt_input, adapt_rubric, adapt_reference, sha256
from ml.metrics import measure
from services.evaluation import summarize
from services.ollama import AssessmentError, assess, SYSTEM, PROMPT_VERSION, response_schema

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def choose(rows, limit, ids):
    if ids:
        requested = ids.split(',')
        by_id = {r['conversation_id']: r for r in rows}
        if len(set(requested)) != len(requested) or set(requested) - set(by_id):
            raise ValueError('Unknown or duplicate --ids')
        return [by_id[cid] for cid in requested]
    if limit is None:
        return rows
    if limit < 1:
        raise ValueError('--limit must be positive')
    # Spread the initial control sample across languages. No gold label access.
    chats = [r for r in rows if r['channel'] == 'agent chat']
    languages = sorted({r['language'] for r in chats})
    groups = [[r for r in chats if r['language'] == lang] for lang in languages]
    balanced = [group[i] for i in range(max(map(len, groups), default=0)) for group in groups if i < len(group)]
    return (balanced + [r for r in rows if r['channel'] != 'agent chat'])[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=ROOT / 'data/releases/dev-reviewed-v1')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--ids', help='Comma-separated exact conversation IDs')
    parser.add_argument('--prepare-only', action='store_true', help='Validate/export inputs; no model predictions')
    parser.add_argument('--resume', action='store_true', help='Continue same immutable configuration, including saved failures')
    args = parser.parse_args()
    load_dotenv(ROOT / 'backend/.env')
    from config import Config
    config = {key: getattr(Config, key) for key in dir(Config) if key.startswith('OLLAMA_')}
    inputs, raw_refs, rubrics, manifest = load_release(args.release)
    selected = choose(inputs, args.limit, args.ids)
    prepared, references = {}, {}
    for row in selected:
        cid = row['conversation_id']
        conversation = adapt_input(row)
        rubric = adapt_rubric(rubrics[row['checklist_hash']])
        gold = adapt_reference(raw_refs[cid], conversation, rubric)
        prepared[cid] = (conversation, rubric)
        references[cid] = {'results': gold, 'summary': summarize(gold),
                           'audio_reviewed': raw_refs[cid].get('assessment_context', {}).get('audio_reviewed', False)}
    print(f'Validated {len(selected)} dialogues, {sum(len(r["results"]) for r in references.values())} labels; score parity OK.', flush=True)
    if args.prepare_only and args.run_dir is None:
        return
    if args.run_dir is None:
        parser.error('--run-dir is required for model inference')
    target = args.run_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    prepared_rows = [{'conversation_id': cid, 'conversation': vars(c), 'checklist': vars(k)}
                     for cid, (c, k) in prepared.items()]
    if args.prepare_only:
        if any(target.iterdir()):
            raise ValueError('Prepare output directory must be empty')
        write_json(target / 'inputs.json', prepared_rows)
        write_json(target / 'references.json', references)
        return
    # Preflight: do not send all cases to a missing or differently configured model.
    base = config['OLLAMA_BASE_URL'].rstrip('/')
    with urlopen(base + '/api/tags', timeout=10) as response:
        tags = json.load(response)['models']
    model = next((m for m in tags if m['name'] == config['OLLAMA_MODEL']), None)
    if model is None:
        raise ValueError('Configured model is not installed; run scripts/local_model.ps1 -Action setup')
    with urlopen(base + '/api/version', timeout=10) as response:
        runtime_version = json.load(response)['version']
    runtime_profile = None
    profile_path = ROOT / '.tools/ollama-runtime.json'
    if base == 'http://127.0.0.1:11434' and profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding='utf-8-sig'))
        runtime_profile = {k: profile[k] for k in ('flash_attention', 'kv_cache_type')}
    contract_hash = hashlib.sha256(json.dumps(prepared_rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    run_config = {'schema_version': 1, 'release_manifest_sha256': sha256(args.release / 'manifest.json'),
                  'release_version': manifest['release_version'], 'config': config,
                  'model_digest': model['digest'], 'prompt_version': PROMPT_VERSION,
                  'ollama_version': runtime_version, 'declared_local_runtime': runtime_profile,
                  'prompt_sha256': hashlib.sha256(SYSTEM.encode()).hexdigest(),
                  'adapter_sha256': sha256(Path(__file__).with_name('dataset.py')),
                  'engine_sha256': sha256(ROOT / 'backend/services/ollama.py'),
                  'prepared_inputs_sha256': contract_hash, 'conversation_ids': list(prepared),
                  'schemas': {cid: response_schema(k.criteria, c.messages) for cid, (c, k) in prepared.items()},
                  'independent_test': False, 'model_audio_input': False}
    manifest_path = target / 'run.json'
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not args.resume or saved['configuration'] != run_config:
            raise ValueError('Run exists or configuration changed; use new run-dir (resume requires identical inputs/model/prompt).')
    else:
        if any(target.iterdir()):
            raise ValueError('New run directory must be empty')
        write_json(manifest_path, {'created_at': datetime.now(timezone.utc).isoformat(), 'configuration': run_config})
        write_json(target / 'inputs.json', prepared_rows)
        write_json(target / 'references.json', references)
        snapshot_dir = target / 'code'
        for relative in ('ml/run.py', 'ml/dataset.py', 'ml/metrics.py', 'services/ollama.py',
                         'services/evaluation.py', 'services/validation.py'):
            destination = snapshot_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'backend' / relative, destination)
    predictions_path = target / 'predictions.json'
    predictions = json.loads(predictions_path.read_text(encoding='utf-8')) if predictions_path.exists() else {}
    if set(predictions) - set(prepared):
        raise ValueError('Saved predictions contain IDs outside the run manifest')
    for index, row in enumerate(selected, 1):
        cid = row['conversation_id']
        if cid in predictions:
            continue
        print(f'[{index}/{len(selected)}] {cid}', flush=True)
        started = time.monotonic()
        conversation, rubric = prepared[cid]
        captured = {}
        try:
            results, engine, metadata = assess(conversation, rubric, config, response_capture=captured)
            prediction = {'state': 'ok', 'results': results, 'summary': summarize(results),
                          'engine': engine, 'metadata': metadata}
        except AssessmentError as exc:
            prediction = {'state': 'error', 'http_status': exc.status, 'error': str(exc),
                          'metadata': {'calls': int(captured.get('request_attempted', False)), **{
                              k: captured[k] for k in ('prompt_eval_count', 'eval_count', 'total_duration') if k in captured}}}
        if captured:
            response_dir = target / 'responses'
            response_dir.mkdir(exist_ok=True)
            response_file = response_dir / (hashlib.sha256(cid.encode()).hexdigest() + '.json')
            write_json(response_file, captured)
            prediction['response_file'] = str(response_file.relative_to(target))
        prediction.update(conversation_id=cid, elapsed_seconds=round(time.monotonic() - started, 3))
        predictions[cid] = prediction
        write_json(predictions_path, predictions)
        report = measure(selected, references, predictions)
        write_json(target / 'metrics.json', report)
        print(f'  {prediction["state"]}, {prediction["elapsed_seconds"]} seconds', flush=True)
        # A service failure is actionable; avoid 65 repeated long timeouts. Resume after repair.
        if prediction.get('http_status') == 503:
            break
    report = measure(selected, references, predictions)
    write_json(target / 'metrics.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('breakdown', 'mismatches', 'limitations')}), flush=True)


if __name__ == '__main__':
    main()
