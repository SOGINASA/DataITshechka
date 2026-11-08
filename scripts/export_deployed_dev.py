"""Run the deployed HTTP evaluator within a wall budget; export honest JSON 1.0."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml2.contracts import dataset, write_json, require
from ml2.submission import MAPPING, error_row, validate_submission, verify_rubric
from ml2.scoring import summarize


def http(base, path, payload=None, timeout=20):
    req = request.Request(base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except error.HTTPError as exc:
        return exc.code, json.load(exc)


def convert(response, dialog, api_dialog, checklist):
    cid = dialog['conversation_id']
    rows = response.get('original_results', response.get('results', []))
    require(len(rows) == 8 and {r['criterion_id'] for r in rows} == set(MAPPING), 'Incomplete criteria')
    unknown = [r['criterion_id'] for r in rows if r['status'] == 'needs_review']
    if unknown:
        return error_row(cid, 'Система оставила критерии неоценёнными: ' + ', '.join(unknown))
    positions = {m['id']: i + 1 for i, m in enumerate(api_dialog['messages'])}
    require(len(positions) == len(dialog['messages']), 'Message IDs are not unique')
    criteria = []
    for row in rows:
        ids = [e['message_id'] for e in row.get('evidence', [])]
        turns = {positions[mid] for mid in ids}
        span = row.get('reviewed_range')
        if not turns and span:
            start, end = positions[span['start_message_id']], positions[span['end_message_id']]
            require(start <= end, 'Reversed evidence range')
            turns.update(range(start, end + 1))
        require(bool(turns), 'No supporting evidence or inspected range')
        require(row['status'] in ('pass', 'fail', 'scored', 'not_applicable'), 'Invalid status')
        require((row['value'] is None) == (row['status'] == 'not_applicable'), 'Unknown is not N/A')
        criteria.append({'criterion_id': MAPPING[row['criterion_id']], 'value': row['value'],
                         'rationale': row['explanation'], 'evidence_turns': sorted(turns)})
    summary = summarize(rows, checklist)
    require(response.get('final_score') == summary['final_score'], 'Backend total mismatch')
    require(type(summary['gross_error_detected']) is bool, 'Unknown critical flag')
    return {'conversation_id': cid, 'status': 'ok', 'criteria': criteria,
            'score': {'final_score': summary['final_score'], 'critical_flag': summary['gross_error_detected']}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=ROOT / 'data/raw/dev.json')
    p.add_argument('--base', default='http://127.0.0.1:6767')
    p.add_argument('--team', required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'results/dev/results.json')
    p.add_argument('--deadline-seconds', type=int, default=1200)
    args = p.parse_args()
    started = time.monotonic()
    dialogs = dataset(args.input)
    require(len(dialogs) == 65, 'Expected complete DEV')
    require(not args.run_dir.exists(), 'Use a new run directory')
    require(not args.output.exists(), 'Refusing to overwrite a submission')
    _, checks = http(args.base, '/api/checklists')
    require(len(checks['items']) == 1, 'Choose a checklist explicitly if more than one exists')
    checklist = checks['items'][0]
    verify_rubric(checklist)
    _, listing = http(args.base, '/api/conversations?dataset_group_id=DEV&per_page=100')
    by_external = {r['external_id']: r['id'] for r in listing['items']}
    snapshots = {}
    for dialog in dialogs:
        cid = dialog['conversation_id']
        status, current = http(args.base, '/api/conversations/' + by_external['freedom:DEV:' + cid])
        require(status == 200, 'Input not available')
        require([(m['speaker'], m['text']) for m in current['messages']] ==
                [(m['speaker'], m['text']) for m in dialog['messages']], 'Deployed transcript differs from DEV')
        snapshots[cid] = current
    # Interleave languages without looking at labels or prior outcomes; calls stay included.
    groups = [[d for d in dialogs if d['language'] == lang and d['channel'] == 'chat']
              for lang in ('ru', 'kk', 'en')]
    ordered = [g[i] for i in range(max(map(len, groups))) for g in groups if i < len(g)]
    calls = [d for d in dialogs if d['channel'] == 'call']
    ordered[3:3] = calls[:1]
    ordered.extend(calls[1:])
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'team_name': args.team,
        'model': 'qwen3:8b', 'base_url': args.base, 'wire_format': 'legacy',
        'checklist_id': checklist['id'], 'deadline_seconds': args.deadline_seconds,
        'source_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'conversation_order': [d['conversation_id'] for d in ordered],
        'configuration': {'num_ctx': 32768, 'num_predict': 2048, 'think': False, 'timeout': 300},
        'runtime': {'flash_attention': True, 'kv_cache_type': 'q8_0', 'concurrency': 1},
        'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                       for name in ('backend/services/ollama.py', 'backend/services/evaluation.py',
                                    'backend/routes/cqa.py', 'scripts/export_deployed_dev.py')}}
    args.run_dir.mkdir(parents=True)
    write_json(args.run_dir / 'manifest.json', manifest)
    write_json(args.run_dir / 'inputs.json', snapshots)
    write_json(args.run_dir / 'checklist.json', checklist)
    records, responses = {}, []

    def save(finished=False):
        reason = ('Не запускался: исчерпан согласованный лимит времени пакетного прогона.' if finished
                  else 'Ожидает запуска: пакетный прогон ещё выполняется.')
        payload = {'schema_version': '1.0', 'team_name': args.team,
                   'model': {'mode': 'local', 'name': 'qwen3:8b'},
                   'results': [records.get(d['conversation_id'], error_row(d['conversation_id'], reason)) for d in dialogs]}
        validate_submission(payload, dialogs, 'dev')
        write_json(args.output, payload)
        summary = {'state': 'finished' if finished else 'running', 'attempted': len(records),
                   'ok': sum(r['status'] == 'ok' for r in records.values()),
                   'failed': sum(r['status'] == 'error' for r in records.values()),
                   'not_run': len(dialogs)-len(records), 'elapsed_seconds': round(time.monotonic()-started, 2)}
        write_json(args.run_dir / 'progress.json', summary)
        return summary

    save()
    for index, dialog in enumerate(ordered, 1):
        if args.deadline_seconds - (time.monotonic()-started) < 315:
            break  # Do not start work that cannot finish within the declared budget.
        cid = dialog['conversation_id']; current = snapshots[cid]
        payload = {'checklist_id': checklist['id'], 'engine': 'ollama'}
        write_json(args.run_dir / 'active.json', {'conversation_id': cid, 'started_at': datetime.now(timezone.utc).isoformat()})
        print(f'[{index}/65] {cid}', flush=True)
        begin = time.monotonic()
        try:
            status, response = http(args.base, '/api/conversations/'+current['id']+'/evaluations', payload, timeout=310)
        except (OSError, ValueError) as exc:
            status, response = None, {'error': {'message': str(exc)}}
        snapshot = {'conversation_id': cid, 'http_status': status, 'request': payload,
                    'elapsed_seconds': round(time.monotonic()-begin, 2), 'response': response}
        write_json(args.run_dir / 'responses' / (cid+'.json'), snapshot)
        if status == 201:
            try:
                require(response['engine'] == 'ollama:qwen3:8b', 'Unexpected model')
                meta = response['run_metadata']
                require(all(meta[k] == v for k,v in [('num_ctx',32768),('num_predict',2048),('think',False),('wire_format','legacy')]), 'Configuration changed')
                row = convert(response, dialog, current, checklist)
                # Validate in the full original set, never replacing failed decisions with guessed values.
                candidate = {**records, cid: row}
                validate_submission({'schema_version':'1.0','team_name':args.team,
                    'model':{'mode':'local','name':'qwen3:8b'},
                    'results':[candidate.get(d['conversation_id'],error_row(d['conversation_id'],'Pending')) for d in dialogs]}, dialogs, 'dev')
                records[cid] = row
            except (ValueError, KeyError, TypeError) as exc:
                records[cid] = error_row(cid, 'Результат системы нельзя экспортировать без подмены: '+str(exc))
        else:
            records[cid] = error_row(cid, 'HTTP '+str(status)+': '+str(response.get('error',{}).get('message','Ошибка API')))
        summary = save()
        print(json.dumps({**summary, 'last_id':cid,'last_status':records[cid]['status'],
                          'last_seconds':snapshot['elapsed_seconds']}, ensure_ascii=False), flush=True)
    (args.run_dir / 'active.json').unlink(missing_ok=True)
    print(json.dumps(save(True),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
