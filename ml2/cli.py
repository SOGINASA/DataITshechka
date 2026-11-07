"""CLI for local isolated inference and fair comparison of two candidates."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from .contracts import (ContractError, canonical, conversation, dataset, digest, loads,
                        read_json, require, rubric, write_json)
from .engine import Evaluator, EvaluationFailure, PROMPT_VERSION, SYSTEM
from .knowledge import KnowledgeBase
from .metrics import report, compare
from .provider import ModelError, Ollama, Settings
from .submission import build_submission, validate_submission

ROOT = Path(__file__).parent


def jsonl(path):
    return [loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def code_hash():
    paths = sorted([*ROOT.glob('*.py'), *ROOT.glob('prompts/*.txt')])
    return digest({str(p.relative_to(ROOT)): p.read_text() for p in paths})


def initialize_run(out, manifest, resume):
    if not resume:
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / 'manifest.json', manifest)
        return manifest, []
    saved = read_json(out / 'manifest.json')
    comparable = lambda m: {k: v for k, v in m.items() if k != 'created_at'}
    require(comparable(saved) == comparable(manifest), 'Resume refused: code/model/data/rules/settings changed')
    previous = jsonl(out / 'predictions.jsonl')
    ids = [p['conversation_id'] for p in previous]
    require(len(ids) == len(set(ids)) and set(ids) <= set(saved['conversation_ids']), 'Invalid saved run IDs')
    require(all(p.get('provenance', {}).get('run_manifest_hash') == digest(saved)
                for p in previous), 'Saved result provenance mismatch')
    return saved, previous


def export_csv(predictions, output):
    # Preserve errors as rows; neutralize spreadsheet formulas in model text and IDs.
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    with Path(output).open('x', newline='') as stream:
        columns = ['conversation_id', 'run_status', 'criterion_id', 'status', 'value', 'explanation',
                   'evidence_message_ids', 'reviewed_range', 'knowledge_refs', 'final_score', 'error']
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for prediction in predictions:
            for result in prediction.get('results') or [{}]:
                row = {k: result.get(k) for k in columns}
                row.update(conversation_id=prediction['conversation_id'], run_status=prediction['status'],
                           final_score=prediction.get('summary', {}).get('final_score'), error=prediction.get('error'))
                for field in ('evidence_message_ids', 'reviewed_range', 'knowledge_refs'):
                    row[field] = canonical(row[field])
                writer.writerow({k: safe(v) for k, v in row.items()})


def run(args):
    started_at = datetime.now(timezone.utc)
    budget = args.deadline_seconds if args.deadline_seconds is not None else (2700 if args.purpose == 'control' else None)
    require(budget is None or 1 <= budget <= 86400, 'deadline-seconds must be 1..86400')
    dialogs = dataset(args.input)
    if args.limit is not None:
        require(args.limit > 0, 'limit must be positive')
        dialogs = dialogs[:args.limit]
    checklist = rubric(read_json(args.rubric))
    kb = KnowledgeBase.load(args.knowledge)
    if any(d['channel'] == 'call' for d in dialogs) and Path(args.rubric).resolve() == (ROOT / 'configs/chat.json').resolve():
        raise ContractError('Calls require an explicitly selected rubric; use configs/voice.json for a call-only batch')
    provider = Ollama(Settings.environment())
    identity = provider.identity()
    evaluator = Evaluator(provider, checklist, kb, args.as_of)
    manifest = {'format_version': 1, 'created_at': started_at.isoformat(),
                'candidate': 'ml2', 'model': identity, 'code_hash': code_hash(),
                'rubric': checklist, 'rubric_hash': digest(checklist),
                'prompt_version': PROMPT_VERSION, 'prompt_hash': digest(SYSTEM),
                'knowledge_hash': digest(kb.raw), 'knowledge_version': kb.version, 'knowledge_as_of': args.as_of,
                'dataset_hash': digest(dialogs), 'conversation_ids': [d['conversation_id'] for d in dialogs],
                'purpose': args.purpose, 'deadline_seconds': budget, 'audio_analyzed': False}
    out = Path(args.output)
    manifest, previous = initialize_run(out, manifest, args.resume)
    if budget is not None:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest['created_at'])).total_seconds()
        provider.deadline = time.monotonic() + budget - elapsed
    if not args.resume:
        write_json(out / 'knowledge.snapshot.json', kb.raw)
        (out / 'prompt.txt').write_text(SYSTEM)
    completed = {p['conversation_id'] for p in previous}
    failures = sum(p['status'] == 'error' for p in previous)
    with (out / 'predictions.jsonl').open('a' if args.resume else 'x') as target:
        for i, dialog in enumerate(dialogs):
            if dialog['conversation_id'] in completed:
                continue
            start = time.monotonic()
            try:
                if provider.deadline is not None and time.monotonic() >= provider.deadline:
                    raise EvaluationFailure('Run deadline exceeded; no assessment was fabricated', [])
                result = evaluator.evaluate(dialog)
            except EvaluationFailure as exc:
                failures += 1
                result = {'conversation_id': dialog['conversation_id'], 'language': dialog['language'],
                          'channel': dialog['channel'], 'status': 'error', 'error': str(exc),
                          'error_code': exc.code, 'results': [],
                          'provenance': {'conversation_hash': digest(dialog), 'rubric_hash': digest(checklist),
                            'elapsed_seconds': round(time.monotonic() - start, 3), 'attempts': exc.attempts}}
            result['provenance'].update(model_digest=identity['digest'], run_manifest_hash=digest(manifest))
            target.write(canonical(result) + '\n')
            target.flush()
            os.fsync(target.fileno())
            print(f'{i+1}/{len(dialogs)} {result["status"]} {result["provenance"]["elapsed_seconds"]}s', flush=True)
    write_json(out / 'run_summary.json', {'requested': len(dialogs), 'saved': len(dialogs),
               'failed': failures, 'quality_measured': False, 'predictions_hash': digest(jsonl(out / 'predictions.jsonl'))})
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='ML2 — independent local CQA candidate')
    commands = parser.add_subparsers(dest='command', required=True)
    n = commands.add_parser('normalize', help='Read organizer response or backend export; preserve text/IDs')
    n.add_argument('--input', required=True)
    n.add_argument('--output', required=True)
    n.add_argument('--channel', choices=['chat', 'call'])
    r = commands.add_parser('run', help='Real local inference, new immutable run directory')
    r.add_argument('--input', required=True)
    r.add_argument('--output', required=True)
    r.add_argument('--rubric', default=str(ROOT / 'configs/chat.json'))
    r.add_argument('--knowledge')
    r.add_argument('--as-of', help='YYYY-MM-DD; required to retrieve dated knowledge excerpts')
    r.add_argument('--limit', type=int)
    r.add_argument('--resume', action='store_true', help='Continue untouched run; saved errors remain errors')
    r.add_argument('--deadline-seconds', type=int, help='Whole run time budget; control defaults to 2700 seconds, including resumed elapsed time')
    r.add_argument('--purpose', choices=['development', 'validation', 'control', 'synthetic_smoke'], default='development')
    for name in ('score', 'compare'):
        p = commands.add_parser(name)
        p.add_argument('--gold', required=True)
        p.add_argument('--predictions', required=True, help='Candidate A predictions.jsonl')
        if name == 'compare':
            p.add_argument('--other', required=True, help='Candidate B in the same exchange format')
        p.add_argument('--rubric', default=str(ROOT / 'configs/chat.json'))
        p.add_argument('--output', required=True)
    commands.add_parser('doctor', help='Check installed local model; no download or inference')
    e = commands.add_parser('export', help='Flat CSV including errors and evidence IDs')
    e.add_argument('--predictions', required=True)
    e.add_argument('--output', required=True)
    s = commands.add_parser('submission', help='Organizer JSON 1.0 from completed runs; missing/unresolved decisions remain errors')
    s.add_argument('--input', required=True, help='Complete original DEV/PROD dataset')
    s.add_argument('--runs', required=True, nargs='+')
    s.add_argument('--split', required=True, choices=['dev', 'prod'])
    s.add_argument('--team', required=True)
    s.add_argument('--output', required=True)
    v = commands.add_parser('validate-submission', help='Check public JSON against original IDs, turns, scales and totals')
    v.add_argument('--input', required=True, help='Complete original dataset')
    v.add_argument('--submission', required=True)
    v.add_argument('--split', required=True, choices=['dev', 'prod'])
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            print(json.dumps(Ollama(Settings.environment()).identity(), ensure_ascii=False, indent=2))
        elif args.command == 'normalize':
            dialogs = dataset(args.input)
            if args.channel:
                dialogs = [d for d in dialogs if d['channel'] == args.channel]
            require(bool(dialogs), 'No conversations selected')
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x') as stream:
                stream.write('\n'.join(canonical(d) for d in dialogs) + '\n')
            print(f'Saved {len(dialogs)} conversations; dataset hash {digest(dialogs)}')
        elif args.command == 'run':
            return run(args)
        elif args.command == 'export':
            export_csv(jsonl(args.predictions), args.output)
            print(f'CSV saved: {args.output}')
        elif args.command == 'submission':
            payload = build_submission(dataset(args.input), args.runs, args.split, args.team)
            require(not Path(args.output).exists(), 'Submission already exists; choose a new output')
            write_json(args.output, payload)
            failures = sum(r['status'] == 'error' for r in payload['results'])
            print(f'Saved {len(payload["results"])} records: {len(payload["results"])-failures} ok, {failures} error. No commit or push performed.')
        elif args.command == 'validate-submission':
            payload = read_json(args.submission)
            validate_submission(payload, dataset(args.input), args.split)
            failures = sum(r['status'] == 'error' for r in payload['results'])
            print(f'Valid format and IDs; {failures} error records. This is not an ML accuracy check.')
        else:
            gold = jsonl(args.gold)
            predictions = jsonl(args.predictions)
            checklist = rubric(read_json(args.rubric))
            result = compare(gold, predictions, jsonl(args.other), checklist) if args.command == 'compare' else report(gold, predictions, checklist)
            require(not Path(args.output).exists(), 'Report already exists; choose a new output')
            write_json(args.output, result)
            print(f'Report saved: {args.output}')
        return 0
    except (ContractError, ModelError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'ML2: {exc}', file=sys.stderr)
        return 2
