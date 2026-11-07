import io
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, select, func

from models import db, Appeal, Review, Evaluation
from services import validation, freedom, ollama
from services.evaluation import summarize, evaluate, apply_overrides


@pytest.fixture
def official():
    return json.loads((Path(__file__).resolve().parents[1] / 'checklists/freedom_chat_v1.json').read_text(encoding='utf-8'))


@pytest.fixture
def official_evaluation(client, dialog, official):
    cid = client.post('/api/conversations', json=dialog).json['id']
    response = client.post('/api/checklists', json=official)
    assert response.status_code == 201, response.json
    rid = response.json['id']
    response = client.post(f'/api/conversations/{cid}/evaluations', json={'checklist_id': rid, 'engine': 'baseline'})
    assert response.status_code == 201
    return response.json


def decisions():
    values = {'contact': True, 'needs': None, 'identification': None, 'consultation': 15,
              'empathy': True, 'dialogue_management': 7, 'closing': True, 'gross_errors': True}
    return [{'criterion_id': key, 'value': value,
             **({'status': 'not_applicable'} if value is None else {}),
             'explanation': 'Проверен весь диалог; условие применимости и решение обоснованы.',
             'reviewed_range': {'start_message_id': 'm1', 'end_message_id': 'm4'}} for key, value in values.items()]


def submit(client, evaluation, overrides=None):
    return client.post(f'/api/evaluations/{evaluation["id"]}/reviews', json={
        'expected_revision': evaluation['revision'], 'reviewer': 'Reviewer', 'comment': 'Manual review',
        'overrides': decisions() if overrides is None else overrides})


def test_official_scoring_and_flag(client, official_evaluation):
    original = official_evaluation
    assert original['final_score'] is None and original['score_is_partial'] is True
    response = submit(client, original)
    assert response.status_code == 201, response.json
    result = response.json['evaluation']
    # (10 + 15 + 15 + 15*7/10 + 5) / (100 - 15 - 20) * 100
    assert result['score'] == result['final_score'] == 85.38
    assert result['coverage'] == 100 and result['score_is_partial'] is False
    assert result['gross_error_detected'] is True
    assert result['critical_failures'] == ['gross_errors']
    assert result['original_results'] == original['original_results']
    management = next(r for r in result['results'] if r['criterion_id'] == 'dialogue_management')
    assert management['points'] == 10.5 and management['effective_points'] == 16.15
    assert next(s for s in result['sections'] if s['name'] == 'Безопасность и решение')['score'] == 75
    no_flag = submit(client, result, [{'criterion_id': 'gross_errors', 'value': False, 'explanation': 'Нарушения не выявлены.'}])
    assert no_flag.json['evaluation']['score'] == 85.38
    assert no_flag.json['evaluation']['gross_error_detected'] is False


def test_model_status_is_derived_from_valid_configured_value(official):
    evidence = {'evidence_message_ids': ['m1']}
    response = [{'criterion_id': 'consultation', 'status': 'pass', 'value': 15, 'explanation': 'Ответ по существу.', **evidence},
                {'criterion_id': 'contact', 'status': 'fail', 'value': True, 'explanation': 'Контакт установлен.', **evidence},
                {'criterion_id': 'gross_errors', 'status': 'pass', 'value': True, 'explanation': 'Нарушение выявлено.', **evidence}]
    normalized = ollama.normalize_model_status(response, official['criteria'])
    assert normalized[0]['status'] == 'scored'
    assert normalized[1]['status'] == 'pass'
    assert normalized[2]['status'] == 'fail'


def test_model_decision_without_evidence_is_saved_for_manual_review(official):
    response = [{'criterion_id': 'contact', 'status': 'pass', 'value': True, 'explanation': 'Всё хорошо.'}]
    normalized = ollama.normalize_model_status(response, official['criteria'])
    assert normalized[0]['status'] == 'needs_review' and normalized[0]['value'] is None


@pytest.mark.parametrize('criterion', ['contact', 'empathy', 'dialogue_management', 'gross_errors'])
def test_official_na_restrictions(client, official_evaluation, criterion):
    response = submit(client, official_evaluation, [{'criterion_id': criterion, 'status': 'not_applicable',
                                                   'explanation': 'N/A', 'evidence_message_ids': ['m1']}])
    assert response.status_code == 422


@pytest.mark.parametrize('override', [
    {'criterion_id': 'consultation', 'value': 12, 'evidence_message_ids': ['m1']},
    {'criterion_id': 'dialogue_management', 'value': True, 'evidence_message_ids': ['m1']},
    {'criterion_id': 'contact', 'value': 1, 'evidence_message_ids': ['m1']},
    {'criterion_id': 'contact', 'value': True},
    {'criterion_id': 'contact', 'value': True, 'evidence_message_ids': ['invented']},
    {'criterion_id': 'contact', 'value': True, 'reviewed_range': {'start_message_id': 'm4', 'end_message_id': 'm1'}},
    {'criterion_id': 'consultation', 'value': 20, 'status': 'pass', 'evidence_message_ids': ['m1']},
    {'criterion_id': 'gross_errors', 'value': True, 'status': 'pass', 'evidence_message_ids': ['m1']},
])
def test_invalid_decisions_do_not_save(client, official_evaluation, override):
    response = submit(client, official_evaluation, [{**override, 'explanation': 'Test'}])
    assert response.status_code == 422
    assert client.get(f'/api/evaluations/{official_evaluation["id"]}').json['revision'] == 1


def test_official_seed_and_versioned_custom_scale(app, client, official, official_evaluation):
    runner = app.test_cli_runner()
    assert runner.invoke(args=['seed-checklist']).exit_code == 0
    assert runner.invoke(args=['seed-checklist']).exit_code == 0
    assert client.get('/api/checklists').json['pagination']['total'] == 1
    criteria = deepcopy(official['criteria'])
    criteria[0] = {'id': 'new_custom', 'title': 'Новый критерий жюри', 'answer_type': 'scale', 'weight': 10,
                   'allow_na': False, 'scale': [{'value': 0, 'label': 'Нет'}, {'value': 2, 'label': 'Частично'},
                                               {'value': 5, 'label': 'Полностью'}], 'rule': {'type': 'semantic'}}
    new = client.post(f'/api/checklists/{official_evaluation["checklist_id"]}/versions',
                      json={'version': 'jury-2', 'criteria': criteria})
    assert new.status_code == 201
    assert new.json['criteria'][0]['id'] == 'new_custom'
    old = client.get(f'/api/checklists/{official_evaluation["checklist_id"]}').json
    assert old['criteria'][0]['id'] == 'contact'
    assert client.get(f'/api/evaluations/{official_evaluation["id"]}').json['checklist_id'] == old['id']


def test_all_na_has_no_score_and_half_up_rounding():
    result = {'criterion_id': 'a', 'status': 'not_applicable', 'weight': 10, 'source': 'human', 'critical': False}
    assert summarize([result])['final_score'] is None
    # 1/32 * 100 = 3.125 -> 3.13 (not banker's rounding)
    passed = {**result, 'status': 'pass', 'weight': 1}
    failed = {**result, 'status': 'fail', 'weight': 31}
    assert summarize([passed, failed])['score'] == 3.13


def open_appeal(client, evaluation, criterion='consultation'):
    response = client.post(f'/api/evaluations/{evaluation["id"]}/appeals', json={
        'criterion_id': criterion, 'expected_revision': evaluation['revision'], 'author': 'Operator',
        'comment': 'Прошу пересмотреть оценку.'})
    assert response.status_code == 201, response.json
    return response.json


def test_appeal_change_and_confirm_preserve_history(client, official_evaluation):
    evaluation = submit(client, official_evaluation).json['evaluation']
    appeal = open_appeal(client, evaluation)
    assert appeal['disputed_result']['value'] == 15 and appeal['status'] == 'open'
    decision = {'expected_revision': evaluation['revision'], 'decision': 'change', 'reviewer': 'Reviewer',
                'reason': 'Все вопросы закрыты.', 'override': {'criterion_id': 'consultation', 'value': 20,
                'explanation': 'Ответ полный.', 'evidence_message_ids': ['m3', 'm4']}}
    response = client.post(f'/api/appeals/{appeal["id"]}/decision', json=decision)
    assert response.status_code == 200, response.json
    result = response.json['evaluation']
    assert result['score'] == 93.08
    assert response.json['appeal']['disputed_result']['value'] == 15
    assert response.json['appeal']['review_id'] == response.json['review']['id']
    assert client.post(f'/api/appeals/{appeal["id"]}/decision', json=decision).status_code == 409
    second = open_appeal(client, result)
    confirmed = client.post(f'/api/appeals/{second["id"]}/decision', json={
        'expected_revision': result['revision'], 'decision': 'confirm', 'reviewer': 'Reviewer', 'reason': 'Оценка верна.'})
    assert confirmed.status_code == 200
    assert confirmed.json['evaluation']['score'] == result['score']
    assert confirmed.json['evaluation']['original_results'] == official_evaluation['original_results']
    export = client.get(f'/api/evaluations/{result["id"]}/export').json
    assert len(export['appeals']) == 2 and len(export['reviews']) == 3
    assert client.get(f'/api/evaluations/{result["id"]}/appeals').json['pagination']['total'] == 2


def test_cannot_confirm_changed_disputed_value(client, official_evaluation):
    evaluation = submit(client, official_evaluation).json['evaluation']
    appeal = open_appeal(client, evaluation)
    updated = submit(client, evaluation, [{'criterion_id': 'consultation', 'value': 20, 'explanation': 'Changed'}]).json['evaluation']
    response = client.post(f'/api/appeals/{appeal["id"]}/decision', json={
        'expected_revision': updated['revision'], 'decision': 'confirm', 'reviewer': 'Reviewer', 'reason': 'Confirm'})
    assert response.status_code == 409
    assert client.get(f'/api/appeals/{appeal["id"]}').json['status'] == 'open'


def test_concurrent_appeal_decisions_are_atomic(app, client, official_evaluation):
    evaluation = submit(client, official_evaluation).json['evaluation']
    appeal = open_appeal(client, evaluation)
    barrier = Barrier(2)
    with app.app_context():
        engine = db.engine
    def synchronize(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE evaluations'):
            barrier.wait(timeout=10)
    def decide():
        with app.test_client() as other:
            return other.post(f'/api/appeals/{appeal["id"]}/decision', json={
                'expected_revision': evaluation['revision'], 'decision': 'confirm', 'reviewer': 'Reviewer', 'reason': 'Confirmed'}).status_code
    event.listen(engine, 'before_cursor_execute', synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decide), pool.submit(decide)]
            statuses = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, 'before_cursor_execute', synchronize)
    assert sorted(statuses) == [200, 409]
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(Review)) == 2
        assert db.session.get(Appeal, appeal['id']).status == 'resolved'


def test_control_group_and_dataset_http_endpoint(app, client, monkeypatch):
    payload = {'isSuccess': True, 'error': '', 'data': {'dataset_group_id': 'CONTROL', 'total_records': 1, 'records': [{
        'conversation_id': 'same-id', 'channel': 'agent chat', 'language': 'EN', 'audio_url': None,
        'transcript': [{'timestamp': '00:00', 'speaker': 'client', 'text': 'Synthetic'}]}]}}
    def fetch(url, group_id='DEV'):
        assert group_id == 'CONTROL'
        return payload
    monkeypatch.setattr(freedom, 'fetch_dataset', fetch)
    response = client.post('/api/datasets/import', json={'group_id': 'CONTROL'})
    assert response.status_code == 200 and response.json['imported'] == 1
    assert client.post('/api/datasets/import', json={'group_id': 'CONTROL'}).json['skipped'] == 1
    assert client.get('/api/conversations?external_id=freedom:CONTROL:same-id').json['pagination']['total'] == 1
    assert client.get('/api/conversations?dataset_group_id=CONTROL').json['pagination']['total'] == 1
    assert client.get('/api/conversations?dataset_group_id=DEV').json['pagination']['total'] == 0
    with pytest.raises(freedom.IntegrationError):
        freedom.normalize_dataset(payload)
    url = freedom.dataset_url('https://unit.environment.api.powerplatform.com/invoke?sig=fake-token&group_id=DEV', 'CONTROL')
    assert 'group_id=CONTROL' in url and 'sig=fake-token' in url


class OllamaResponse(io.BytesIO):
    status = 200


def mock_ollama(monkeypatch, content, envelope_overrides=None, inspect=None):
    class Opener:
        def open(self, req, timeout):
            payload = json.loads(req.data)
            assert req.full_url.endswith('/api/chat') and payload['stream'] is False
            assert payload['format']['type'] == 'object'
            if inspect:
                inspect(payload)
            envelope = {'done': True, 'done_reason': 'stop', 'model': 'synthetic-test-model',
                        'message': {'content': json.dumps(content)}, 'eval_count': 40, 'prompt_eval_count': 100,
                        **(envelope_overrides or {})}
            return OllamaResponse(json.dumps(envelope).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda handler: Opener())


def model_results():
    results = decisions()
    for result in results:
        kind = result['criterion_id']
        if 'status' not in result:
            result['status'] = ('fail' if result['value'] else 'pass') if kind == 'gross_errors' else (
                'scored' if kind in ('consultation', 'dialogue_management') else 'pass' if result['value'] else 'fail')
        result['evidence_message_ids'] = []
    return {'results': results}


def test_ollama_structured_output_and_dynamic_rubric(app, client, official_evaluation, monkeypatch):
    app.config['OLLAMA_MODEL'] = 'synthetic-test-model'
    app.config['OLLAMA_THINK'] = False
    captured = []
    mock_ollama(monkeypatch, model_results(), inspect=lambda payload: captured.append(payload))
    response = client.post(f'/api/conversations/{official_evaluation["conversation_id"]}/evaluations',
                           json={'checklist_id': official_evaluation['checklist_id']})
    assert response.status_code == 201, response.json
    result = response.json
    assert result['engine'] == 'ollama:synthetic-test-model' and result['score'] == 85.38
    assert result['results'][0]['source'] == 'model'
    assert result['run_metadata']['eval_count'] == 40 and result['run_metadata']['calls'] == 1
    assert captured[0]['think'] is False
    request_content = json.loads(captured[0]['messages'][1]['content'])
    assert len(request_content['criteria']) == 8
    assert 'recording_url' not in request_content and 'source_metadata' not in request_content
    custom = client.post(f'/api/checklists/{official_evaluation["checklist_id"]}/versions', json={
        'version': 'custom', 'criteria': [{'id': 'new', 'title': 'Новый критерий без правки кода', 'answer_type': 'binary',
                                         'weight': 10, 'allow_na': False, 'rule': {'type': 'semantic'}}]}).json
    mock_ollama(monkeypatch, {'results': [{'criterion_id': 'new', 'value': True, 'status': 'pass', 'explanation': 'Supported',
                                         'evidence_message_ids': ['m3'], 'reviewed_range': None}]})
    custom_result = client.post(f'/api/conversations/{official_evaluation["conversation_id"]}/evaluations', json={'checklist_id': custom['id']})
    assert custom_result.status_code == 201
    assert custom_result.json['results'][0]['evidence'][0]['message_id'] == 'm3'


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'bad_id', 'bad_score', 'forbidden_na', 'no_evidence', 'truncated'])
def test_bad_model_output_does_not_persist_unreviewed_values(app, client, official_evaluation, monkeypatch, case):
    app.config['OLLAMA_MODEL'] = 'synthetic-test-model'
    output = model_results()
    if case == 'missing':
        output['results'].pop()
    elif case == 'duplicate':
        output['results'][1] = deepcopy(output['results'][0])
    elif case == 'bad_id':
        output['results'][0]['evidence_message_ids'] = ['invented']
    elif case == 'bad_score':
        output['results'][3]['value'] = 13
    elif case == 'forbidden_na':
        output['results'][0].update(status='not_applicable', value=None)
    elif case == 'no_evidence':
        output['results'][0]['reviewed_range'] = None
    mock_ollama(monkeypatch, output, {'done_reason': 'length'} if case == 'truncated' else None)
    url = f'/api/conversations/{official_evaluation["conversation_id"]}/evaluations'
    response = client.post(url, json={'checklist_id': official_evaluation['checklist_id']})
    if case == 'no_evidence':
        assert response.status_code == 201, response.json
        result = next(item for item in response.json['results'] if item['criterion_id'] == 'contact')
        assert result['status'] == 'needs_review' and result['value'] is None
        assert client.get(url).json['pagination']['total'] == 2
        return
    assert response.status_code == 502
    assert client.get(url).json['pagination']['total'] == 1


def test_unconfigured_model_is_explicit_failure(app, client, official_evaluation):
    app.config['OLLAMA_MODEL'] = ''
    url = f'/api/conversations/{official_evaluation["conversation_id"]}/evaluations'
    assert client.post(url, json={'checklist_id': official_evaluation['checklist_id']}).status_code == 503
    assert client.get(url).json['pagination']['total'] == 1


def test_model_context_is_not_silently_truncated(app, client, official_evaluation):
    app.config.update(OLLAMA_MODEL='synthetic-test-model', OLLAMA_NUM_CTX=4096, OLLAMA_NUM_PREDICT=512)
    response = client.post(f'/api/conversations/{official_evaluation["conversation_id"]}/evaluations',
                           json={'checklist_id': official_evaluation['checklist_id']})
    assert response.status_code == 422


def test_official_and_appeal_response_schemas(client, official_evaluation):
    from jsonschema import Draft202012Validator
    specification = client.get('/api/openapi.json').json
    def validate_response(response, schema_name):
        Draft202012Validator({'$ref': '#/components/schemas/' + schema_name,
                              'components': specification['components']}).validate(response)
    validate_response(official_evaluation, 'Evaluation')
    evaluation = submit(client, official_evaluation).json['evaluation']
    validate_response(evaluation, 'Evaluation')
    appeal = open_appeal(client, evaluation)
    validate_response(appeal, 'Appeal')
    response = client.post(f'/api/appeals/{appeal["id"]}/decision', json={
        'expected_revision': evaluation['revision'], 'decision': 'confirm', 'reviewer': 'Reviewer', 'reason': 'Confirmed'})
    assert response.status_code == 200
    validate_response(response.json['appeal'], 'Appeal')
    validate_response(response.json['review'], 'Review')
    validate_response(response.json['evaluation'], 'Evaluation')
