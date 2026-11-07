"""Full frozen DEV evaluation through OpenAI Responses; root .env is read privately."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import dotenv_values
from ml.dataset import load_release, adapt_input, adapt_rubric, adapt_reference, sha256
from ml.metrics import measure
from ml.run import write_json
from services.ollama import SYSTEM, PROMPT_VERSION, response_schema
from services.evaluation import evaluate, apply_overrides, summarize
from services.validation import assessment_item, obj, ValidationError
from services.freedom import NoRedirect

ENDPOINT = 'https://api.openai.com/v1/responses'
DEFAULT_MODEL = 'gpt-5-mini-2025-08-07'


class APIError(ValueError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def api_schema(criteria, messages):
    # Reuse one ID enum: duplicating it in every union exceeds API enum limits on calls.
    schema = response_schema(criteria)
    def convert(node):
        if isinstance(node, list):
            return [convert(n) for n in node]
        if not isinstance(node, dict):
            return node
        result = {k: convert(v) for k, v in node.items() if k not in ('minLength', 'maxLength')}
        if 'const' in result:
            value = result.pop('const')
            result.update(type='boolean' if type(value) is bool else 'string', enum=[value])
        if 'properties' in result:
            for key in ('start_message_id', 'end_message_id'):
                if key in result['properties']:
                    result['properties'][key] = {'$ref': '#/$defs/message_id'}
            if 'evidence_message_ids' in result['properties']:
                result['properties']['evidence_message_ids']['items'] = {'$ref': '#/$defs/message_id'}
        return result
    schema = convert(schema)
    schema['$defs'] = {'message_id': {'type': 'string', 'enum': [m['id'] for m in messages]}}
    return schema


def payload(conversation, rubric, model, output_tokens):
    return {'model': model, 'store': False, 'stream': False,
            'max_output_tokens': output_tokens,
            'input': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps({
                'rubric_description': rubric.description, 'criteria': rubric.criteria,
                'language': conversation.language, 'channel': conversation.channel,
                'messages': conversation.messages}, ensure_ascii=False)}],
            'text': {'format': {'type': 'json_schema', 'name': 'cqa_assessment', 'strict': True,
                                'schema': api_schema(rubric.criteria, conversation.messages)}}}


def send(body, key):
    req = request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
    try:
        with request.build_opener(NoRedirect).open(req, timeout=300) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise APIError('Response exceeds 2 MiB')
            return json.loads(raw)
    except error.HTTPError as exc:
        status = exc.code
        # Never persist remote error text: it can echo request data or credentials.
        try:
            data = json.loads(exc.read(65536)).get('error', {})
            code = data.get('code')
            safe_code = code if code in ('insufficient_quota', 'credit_balance_exhausted', 'invalid_api_key', 'model_not_found',
                                          'rate_limit_exceeded', 'unsupported_country_region_territory') else 'request_failed'
        except (ValueError, TypeError, AttributeError):
            safe_code = 'request_failed'
        finally:
            if exc.fp is not None:
                exc.close()
        raise APIError(f'OpenAI HTTP {status}: {safe_code}', status) from None
    except (error.URLError, OSError, TimeoutError, HTTPException):
        raise APIError('OpenAI network failure or timeout; request may have been billed', 503) from None


def parse(envelope, conversation, rubric):
    if envelope.get('status') != 'completed':
        raise APIError('OpenAI response is incomplete or failed')
    content = [part for item in envelope.get('output', []) if item.get('type') == 'message'
               for part in item.get('content', [])]
    if any(part.get('type') == 'refusal' for part in content):
        raise APIError('Model refused assessment')
    texts = [part['text'] for part in content if part.get('type') == 'output_text']
    if len(texts) != 1:
        raise APIError('Expected exactly one final JSON output')
    document = obj(json.loads(texts[0]), ('results',), ('results',))
    if not isinstance(document['results'], dict) or set(document['results']) != {c['id'] for c in rubric.criteria}:
        raise APIError('Incorrect criterion IDs')
    fields = ('status', 'value', 'explanation', 'evidence_message_ids', 'reviewed_range')
    overrides = [assessment_item({**obj(value, fields, fields), 'criterion_id': cid})
                 for cid, value in document['results'].items()]
    initial = evaluate(conversation, rubric)
    for item in initial:
        item['require_evidence'] = True
        item['evidence'] = []
        item.pop('reviewed_range', None)
    return apply_overrides(initial, overrides, conversation.messages, source='model')[0]


def assess_one(cid, conversation, rubric, model, output_tokens, key):
    started = time.monotonic()
    captured = {}
    metadata = {'calls': 1, 'model': model, 'prompt_version': PROMPT_VERSION}
    try:
        envelope = send(payload(conversation, rubric, model, output_tokens), key)
        usage = envelope.get('usage') or {}
        captured = {k: envelope[k] for k in ('id', 'model', 'status', 'usage', 'incomplete_details') if k in envelope}
        # Preserve final output only, never hidden reasoning or API keys.
        captured['output'] = [x for x in envelope.get('output', []) if x.get('type') == 'message']
        metadata.update(response_id=envelope.get('id'), actual_model=envelope.get('model'), usage=usage,
                        prompt_eval_count=usage.get('input_tokens', 0), eval_count=usage.get('output_tokens', 0))
        results = parse(envelope, conversation, rubric)
        prediction = {'state': 'ok', 'results': results, 'summary': summarize(results)}
    except (APIError, ValueError, KeyError, TypeError) as exc:
        # Validation text could contain echoed transcript; keep detailed final output privately.
        message = str(exc) if isinstance(exc, APIError) else 'Invalid structured assessment: ' + type(exc).__name__
        prediction = {'state': 'error', 'error': message, 'http_status': getattr(exc, 'status', None)}
    prediction.update(conversation_id=cid, engine='openai:' + model, metadata=metadata,
                      elapsed_seconds=round(time.monotonic() - started, 3))
    return prediction, captured


def compare_baseline(folder, rows, references, prepared, predictions):
    """Compare only completed runs and verify that model-visible inputs really match."""
    baseline = ROOT / 'data/runs/full-compare-20261107/local-v1'
    if not (baseline / 'predictions.json').exists() or set(predictions) != set(prepared):
        return
    local = json.loads((baseline / 'predictions.json').read_text(encoding='utf-8'))
    exported = json.loads((baseline / 'inputs.json').read_text(encoding='utf-8'))
    by_id = {r['conversation_id']: r for r in exported}
    if set(local) != set(prepared) or set(by_id) != set(prepared):
        return
    for cid, (c, k) in prepared.items():
        if by_id[cid]['conversation'] != vars(c) or by_id[cid]['checklist'] != vars(k):
            raise ValueError('Baseline input/rubric mismatch; comparison refused')
    local_refs = json.loads((baseline / 'references.json').read_text(encoding='utf-8'))
    if local_refs != references:
        raise ValueError('Baseline reference mismatch; comparison refused')
    a, b = measure(rows, references, local), measure(rows, references, predictions)
    pairs = [(local[cid].get('summary', {}).get('final_score'),
              predictions[cid].get('summary', {}).get('final_score'), references[cid]['summary']['final_score'])
             for cid in prepared]
    pairs = [p for p in pairs if all(x is not None for x in p)]
    write_json(folder / 'comparison-with-qwen.json', {
        'complete': True, 'identical_inputs_rubrics_references': True, 'qwen': a, 'gpt': b,
        'accuracy_delta_gpt_minus_qwen': b['breakdown']['all']['accuracy'] - a['breakdown']['all']['accuracy'],
        'score_pairs_with_both_complete': len(pairs),
        'paired_score_mae_qwen': sum(abs(x - z) for x, y, z in pairs) / len(pairs) if pairs else None,
        'paired_score_mae_gpt': sum(abs(y - z) for x, y, z in pairs) / len(pairs) if pairs else None,
        'independent_test': False, 'model_audio_input': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--model')
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 5))
    parser.add_argument('--max-output-tokens', type=int, default=12000)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    env = dotenv_values(ROOT / '.env', encoding='utf-8-sig', interpolate=False)
    key = env.get('GPT_API_KEY') or env.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
    model = args.model or env.get('GPT_MODEL') or env.get('OPENAI_MODEL') or DEFAULT_MODEL
    if not args.prepare_only and not key:
        parser.error('Set GPT_API_KEY or OPENAI_API_KEY in root .env')
    release = ROOT / 'data/releases/dev-reviewed-v1'
    rows, original, rubrics, _ = load_release(release)
    prepared, references = {}, {}
    for row in rows:
        cid = row['conversation_id']
        c, k = adapt_input(row), adapt_rubric(rubrics[row['checklist_hash']])
        prepared[cid] = (c, k)
        results = adapt_reference(original[cid], c, k)
        references[cid] = {'results': results, 'summary': summarize(results),
                          'audio_reviewed': original[cid].get('assessment_context', {}).get('audio_reviewed', False)}
    bodies = {cid: payload(c, k, model, args.max_output_tokens) for cid, (c, k) in prepared.items()}
    fingerprints = {str(path.relative_to(ROOT)): sha256(path) for path in [Path(__file__),
        *[ROOT / 'backend' / name for name in ('ml/dataset.py', 'ml/metrics.py', 'services/ollama.py',
                                               'services/evaluation.py', 'services/validation.py')]]}
    config = {'model': model, 'endpoint': ENDPOINT, 'max_output_tokens': args.max_output_tokens,
              'workers': args.workers, 'store': False, 'reasoning_effort': 'API default', 'automatic_retries': 0,
              'release_manifest_sha256': sha256(release / 'manifest.json'), 'code_sha256': fingerprints,
              'requests_sha256': hashlib.sha256(json.dumps(bodies, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
              'conversation_ids': list(prepared), 'prompt_version': PROMPT_VERSION,
              'independent_test': False, 'audio_supplied': False, 'reference_policy': 'frozen v1'}
    folder = args.run_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'run.json'
    if manifest_path.exists():
        if not args.resume or json.loads(manifest_path.read_text(encoding='utf-8'))['configuration'] != config:
            raise ValueError('Existing run or changed configuration; use new directory or identical --resume')
    else:
        if any(folder.iterdir()):
            raise ValueError('New run directory must be empty')
        write_json(manifest_path, {'created_at': datetime.now(timezone.utc).isoformat(), 'configuration': config})
        write_json(folder / 'requests.json', bodies)
        write_json(folder / 'references.json', references)
        for relative in fingerprints:
            dest = folder / 'code' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, dest)
    print(f'Validated {len(rows)} dialogues / {sum(len(g["results"]) for g in references.values())} labels. Model: {model}', flush=True)
    if args.prepare_only:
        return
    path = folder / 'predictions.json'
    predictions = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if set(predictions) - set(prepared):
        raise ValueError('Unexpected saved IDs')
    remaining = iter(cid for cid in prepared if cid not in predictions)
    fatal = False
    def save(cid, result):
        nonlocal fatal
        prediction, captured = result
        if captured:
            response_dir = folder / 'responses'
            response_dir.mkdir(exist_ok=True)
            write_json(response_dir / (cid + '.json'), captured)
        predictions[cid] = prediction
        write_json(path, predictions)
        write_json(folder / 'metrics.json', measure(rows, references, predictions))
        print(f'[{len(predictions)}/{len(rows)}] {cid}: {prediction["state"]}, {prediction["elapsed_seconds"]}s'
              + ('; ' + prediction['error'] if prediction['state'] == 'error' else ''), flush=True)
        fatal |= prediction.get('http_status') is not None
    # One real pilot first; do not spend the full budget on a broken credential/schema.
    first = next(remaining, None)
    if first is not None:
        save(first, assess_one(first, *prepared[first], model, args.max_output_tokens, key))
        fatal |= predictions[first]['state'] != 'ok'
    if not fatal:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {}
            def submit():
                cid = next(remaining, None)
                if cid is not None:
                    future = pool.submit(assess_one, cid, *prepared[cid], model, args.max_output_tokens, key)
                    pending[future] = cid
            for _ in range(args.workers):
                submit()
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    cid = pending.pop(future)
                    save(cid, future.result())
                if not fatal:
                    for _ in done:
                        submit()
    metrics = measure(rows, references, predictions)
    write_json(folder / 'metrics.json', metrics)
    write_json(folder / 'status.json', {'complete': len(predictions) == len(rows), 'halted_on_api_error': fatal,
                                       'saved': len(predictions), 'expected': len(rows)})
    compare_baseline(folder, rows, references, prepared, predictions)
    print(json.dumps({k: metrics[k] for k in ('completed', 'errors', 'pending', 'score_mae')}), flush=True)


if __name__ == '__main__':
    main()
