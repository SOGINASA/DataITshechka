"""Organizer JSON 1.0 adapter. Never invent a grade to make a submission complete."""
from pathlib import Path
from .contracts import (ContractError, digest, loads, read_json, require, rubric,
                        text, validate_results)
from .scoring import summarize

MAPPING = {'contact': 'contact', 'needs': 'discovery', 'identification': 'identification',
           'consultation': 'consultation', 'empathy': 'empathy',
           'dialogue_management': 'dialogue', 'closing': 'closure', 'gross_errors': 'critical'}
WEIGHTS = [10, 15, 20, 20, 15, 15, 5, 0]
NULLABLE = {'discovery', 'identification', 'consultation', 'closure'}
SCALES = {'consultation': [0, 5, 10, 15, 20], 'dialogue': [0, 4, 7, 10]}


def verify_rubric(checklist):
    criteria = {c['id']: c for c in checklist['criteria']}
    require(set(criteria) == set(MAPPING), 'Submission 1.0 requires the original eight criteria')
    for (internal, public), weight in zip(MAPPING.items(), WEIGHTS):
        c = criteria[internal]
        kind = 'scale' if public in SCALES else 'flag' if public == 'critical' else 'binary'
        require(c['weight'] == weight and c['answer_type'] == kind, 'Submission rubric weight/type mismatch')
        if kind == 'scale':
            require(sorted(s['value'] for s in c['scale']) == SCALES[public], 'Submission scale mismatch')


def error_row(cid, reason):
    return {'conversation_id': cid, 'status': 'error', 'criteria': [], 'score': None, 'error': reason}


def convert(prediction, dialog, checklist, knowledge):
    cid = dialog['conversation_id']
    if prediction is None:
        return error_row(cid, 'Нет результата оценки в выбранных запусках.')
    if prediction['status'] == 'error':
        return error_row(cid, text(prediction.get('error'), 'error', 4000))
    require(prediction['status'] == 'ok', 'Invalid native evaluation status')
    # Quotes are regenerated from the original input; stored totals are never trusted.
    rows = [{k: v for k, v in r.items() if k != 'evidence'} for r in prediction['results']]
    validated = validate_results({'results': rows}, checklist, dialog, knowledge)
    unresolved = [r['criterion_id'] for r in validated if r['status'] == 'needs_review']
    if unresolved:
        return error_row(cid, 'Недостаточно данных для полной оценки: ' + ', '.join(unresolved))
    positions = {m['id']: i + 1 for i, m in enumerate(dialog['messages'])}
    criteria = []
    for row in validated:
        key, value = MAPPING[row['criterion_id']], row['value']
        if value is None and key not in NULLABLE:
            return error_row(cid, f'{key}=N/A не разрешён форматом 1.0. Требуется уточнение организаторов; ответ не заменён на false.')
        turns = {positions[mid] for mid in row['evidence_message_ids']}
        span = row['reviewed_range']
        if span:
            turns.update(range(positions[span['start_message_id']], positions[span['end_message_id']] + 1))
        criteria.append({'criterion_id': key, 'value': value,
                         'rationale': row['explanation'], 'evidence_turns': sorted(turns)})
    score = summarize(validated, checklist)
    if score['final_score'] is None or type(score['gross_error_detected']) is not bool:
        return error_row(cid, 'Не удалось получить полный итог и флаг грубой ошибки.')
    return {'conversation_id': cid, 'status': 'ok', 'criteria': criteria,
            'score': {'final_score': score['final_score'], 'critical_flag': score['gross_error_detected']}}


def load_runs(paths, dialogs):
    expected = {d['conversation_id']: d for d in dialogs}
    records, models = {}, set()
    for path in paths:
        path = Path(path)
        manifest = read_json(path / 'manifest.json')
        summary = read_json(path / 'run_summary.json')
        predictions = [loads(line) for line in (path / 'predictions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        require(summary.get('predictions_hash') == digest(predictions), 'Run contents changed or are incomplete')
        require(manifest['model']['provider'] == 'ollama', 'Only measured local Ollama runs are supported here')
        models.add(text(manifest['model']['model'], 'model.name'))
        checklist = rubric(manifest['rubric'])
        verify_rubric(checklist)
        knowledge = read_json(path / 'knowledge.snapshot.json')
        require(digest(knowledge) == manifest['knowledge_hash'], 'Knowledge snapshot changed')
        docs = {d['id']: d for d in knowledge['documents']}
        saved_ids = [p['conversation_id'] for p in predictions]
        require(len(saved_ids) == len(set(saved_ids)) and set(saved_ids) == set(manifest['conversation_ids']), 'Incomplete run ID set')
        for prediction in predictions:
            cid, provenance = prediction['conversation_id'], prediction['provenance']
            require(cid in expected and cid not in records, 'Unexpected or duplicate conversation across runs')
            require(provenance.get('conversation_hash') == digest(expected[cid]), 'Submission input hash mismatch')
            require(provenance.get('rubric_hash') == digest(checklist) == manifest['rubric_hash'], 'Submission rubric hash mismatch')
            require(provenance.get('run_manifest_hash') == digest(manifest), 'Run provenance mismatch')
            require(provenance.get('model_digest') == manifest['model']['digest'], 'Model provenance mismatch')
            refs = provenance.get('retrieved_ids', [])
            require(all(ref in docs for ref in refs), 'Missing knowledge snapshot document')
            records[cid] = convert(prediction, expected[cid], checklist, [docs[ref] for ref in refs])
    require(bool(models), 'At least one completed run is required')
    return records, sorted(models)


def build_submission(dialogs, paths, split, team):
    text(team, 'team_name', 200)
    require(split in ('dev', 'prod'), 'Invalid split')
    channels = [d['channel'] for d in dialogs]
    if split == 'dev':
        require(len(dialogs) == 65 and channels.count('chat') == 60 and channels.count('call') == 5,
                'DEV must contain all 60 chats and 5 calls from the original dataset')
    else:
        require(len(dialogs) == 10 and all(c == 'chat' for c in channels), 'PROD must contain exactly 10 chats')
    require(len({d['conversation_id'] for d in dialogs}) == len(dialogs), 'Duplicate source conversation ID')
    records, models = load_runs(paths, dialogs)
    payload = {'schema_version': '1.0', 'team_name': team,
               'model': {'mode': 'local', 'name': ', '.join(models)},
               'results': [records.get(d['conversation_id']) or convert(None, d, None, None) for d in dialogs]}
    validate_submission(payload, dialogs, split)
    return payload


def validate_submission(payload, dialogs, split):
    """Validate the public artifact independently of the internal evaluator or run files."""
    require(split in ('dev', 'prod'), 'Invalid split')
    channels = [d['channel'] for d in dialogs]
    require((split == 'dev' and len(dialogs) == 65 and channels.count('chat') == 60 and channels.count('call') == 5)
            or (split == 'prod' and len(dialogs) == 10 and all(c == 'chat' for c in channels)), 'Wrong source dataset composition')
    require(len({d['conversation_id'] for d in dialogs}) == len(dialogs), 'Duplicate source IDs')
    require(set(payload) == {'schema_version', 'team_name', 'model', 'results'}, 'Invalid submission fields')
    require(payload['schema_version'] == '1.0', 'Unknown submission schema')
    text(payload['team_name'], 'team_name', 200)
    require(set(payload['model']) == {'mode', 'name'} and payload['model']['mode'] in ('local', 'external_api', 'hybrid'), 'Invalid model metadata')
    text(payload['model']['name'], 'model.name', 1000)
    originals = {d['conversation_id']: d for d in dialogs}
    rows = payload['results']
    require(isinstance(rows, list) and len(rows) == (65 if split == 'dev' else 10), 'Wrong submission size')
    require(len({r['conversation_id'] for r in rows}) == len(rows) and {r['conversation_id'] for r in rows} == set(originals), 'Submission ID set mismatch')
    for row in rows:
        if row['status'] == 'error':
            require(set(row) == {'conversation_id', 'status', 'criteria', 'score', 'error'} and row['criteria'] == [] and row['score'] is None, 'Invalid error row')
            text(row['error'], 'error', 4000)
            continue
        require(row['status'] == 'ok' and set(row) == {'conversation_id', 'status', 'criteria', 'score'}, 'Invalid result row')
        criteria = row['criteria']
        require(isinstance(criteria, list) and len(criteria) == 8 and {r['criterion_id'] for r in criteria} == set(MAPPING.values()), 'Submission needs eight unique criteria')
        native, config = [], []
        weights = dict(zip(MAPPING.values(), WEIGHTS))
        for c in criteria:
            require(set(c) == {'criterion_id', 'value', 'rationale', 'evidence_turns'}, 'Invalid criterion fields')
            key, value = c['criterion_id'], c['value']
            if value is None:
                require(key in NULLABLE, 'Forbidden null in submission')
            elif key in SCALES:
                require(type(value) in (int, float) and value in SCALES[key], 'Invalid submission scale')
            else:
                require(type(value) is bool, 'Submission boolean expected')
            text(c['rationale'], 'rationale', 2000)
            turns = c['evidence_turns']
            require(isinstance(turns, list) and bool(turns) and all(type(t) is int and 1 <= t <= len(originals[row['conversation_id']]['messages']) for t in turns) and len(turns) == len(set(turns)), 'Invalid evidence_turns')
            native.append({'criterion_id': key, 'status': 'not_applicable' if value is None else 'scored' if key in SCALES else ('fail' if value else 'pass') if key == 'critical' else ('pass' if value else 'fail'), 'value': value})
            config.append({'id': key, 'weight': weights[key], 'answer_type': 'scale' if key in SCALES else 'flag' if key == 'critical' else 'binary', 'scale': [{'value': v} for v in SCALES.get(key, [])]})
        summary = summarize(native, {'criteria': config})
        score = row['score']
        require(isinstance(score, dict) and set(score) == {'final_score', 'critical_flag'}, 'Invalid score fields')
        require(type(score['final_score']) in (int, float) and score['final_score'] == summary['final_score'] and type(score['critical_flag']) is bool and score['critical_flag'] is summary['gross_error_detected'], 'Submission totals or critical_flag mismatch')
