from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest
from flask_migrate import upgrade, check
from sqlalchemy import event, select, func
from sqlalchemy.exc import IntegrityError

from models import db, Conversation, Review


def review_payload(revision=1, status='pass'):
    return {'expected_revision': revision, 'reviewer': 'Проверяющий', 'comment': 'Просмотрены все реплики.',
            'overrides': [{'criterion_id': 'resolution', 'status': status, 'explanation': 'Клиент подтвердил решение.'}]}


def test_end_to_end_review_and_export(client, evaluation):
    assert evaluation['score'] == 100
    assert evaluation['coverage'] == 20
    assert evaluation['needs_review'] is True
    assert evaluation['results'][0]['evidence'][0]['message_id'] == 'm3'
    assert evaluation['results'][0]['evidence'][0]['start_ms'] == 3000
    assert evaluation['results'][1]['status'] == 'needs_review'
    endpoint = f'/api/evaluations/{evaluation["id"]}'
    payload = review_payload()
    payload['overrides'].extend([
        {'criterion_id': 'greeting', 'status': 'pass', 'explanation': 'Приветствие присутствует.'},
        {'criterion_id': 'handoff', 'status': 'pass', 'explanation': 'Контекст передан.'}])
    review = client.post(endpoint + '/reviews', json=payload)
    assert review.status_code == 201
    updated = review.json['evaluation']
    assert updated['revision'] == 2
    assert updated['coverage'] == 100
    assert updated['needs_review'] is False
    assert updated['original_results'] == evaluation['results']
    assert updated['results'][1]['source'] == 'human'
    assert client.post(endpoint + '/reviews', json=payload).status_code == 409
    export = client.get(endpoint + '/export')
    assert export.status_code == 200
    assert 'attachment' in export.headers['Content-Disposition']
    assert export.json['checklist']['is_demo'] is True
    assert len(export.json['reviews']) == 1
    assert export.json['reviews'][0]['changes'][0]['before']['status'] == 'needs_review'
    assert export.json['reviews'][0]['changes'][0]['after']['status'] == 'pass'
    detail = client.get('/api/conversations/' + evaluation['conversation_id']).json
    assert detail['latest_evaluation']['revision'] == 2
    assert client.get(endpoint + '/reviews').json['pagination']['total'] == 1
    stats = client.get('/api/stats').json
    assert stats['conversations'] == stats['evaluations'] == stats['reviews'] == 1


def test_critical_failure_and_na_score(client, evaluation):
    endpoint = f'/api/evaluations/{evaluation["id"]}/reviews'
    failed = client.post(endpoint, json=review_payload(status='fail')).json['evaluation']
    assert failed['score'] == 25
    assert failed['coverage'] == 80
    assert failed['critical_failures'] == ['resolution']
    payload = review_payload(2)
    payload['overrides'] = [{'criterion_id': r['criterion_id'], 'status': 'not_applicable', 'explanation': 'Не применимо.'}
                            for r in evaluation['results']]
    na = client.post(endpoint, json=payload).json['evaluation']
    assert na['score'] is None and na['coverage'] is None
    assert na['needs_review'] is False
    assert na['critical_failures'] == []


@pytest.mark.parametrize('language,greeting', [('ru', 'Здравствуйте!'), ('kk', 'Сәлеметсіз бе!'), ('en', 'HELLO!')])
def test_multilingual_evidence(client, dialog, checklist, language, greeting):
    dialog['language'] = language
    dialog['messages'] = [{'speaker': 'operator', 'text': greeting, 'start_ms': 0, 'end_ms': 1000}]
    cid = client.post('/api/conversations', json=dialog).json['id']
    rid = client.post('/api/checklists', json=checklist).json['id']
    result = client.post(f'/api/conversations/{cid}/evaluations', json={'checklist_id': rid}).json
    evidence = result['results'][0]['evidence'][0]
    assert evidence['quote'] == greeting and evidence['end_ms'] == 1000
    assert result['results'][0]['status'] == 'pass'


@pytest.mark.parametrize('case', ['missing_language', 'missing_speaker', 'no_match', 'prohibited_term'])
def test_rule_boundaries(client, dialog, checklist, case):
    criterion = checklist['criteria'][0]
    if case == 'missing_language':
        criterion['rule']['terms'] = {'en': ['hello']}
    elif case == 'missing_speaker':
        dialog['messages'] = [{'speaker': 'bot', 'text': 'Здравствуйте!'}]
    elif case == 'no_match':
        dialog['messages'] = [{'speaker': 'operator', 'text': 'Перейдите в раздел поддержки.'}]
    else:
        criterion['rule']['type'] = 'contains_none'
    cid = client.post('/api/conversations', json=dialog).json['id']
    rid = client.post('/api/checklists', json=checklist).json['id']
    result = client.post(f'/api/conversations/{cid}/evaluations', json={'checklist_id': rid}).json
    assert result['results'][0]['status'] == ('needs_review' if case.startswith('missing') else 'fail')
    if case.startswith('missing'):
        assert result['score'] is None


@pytest.mark.parametrize('field,value', [('title', ''), ('title', 1), ('channel', []), ('channel', 'email'),
                                        ('language', 'uz'), ('messages', []), ('messages', {}),
                                        ('recording_url', 'javascript:alert(1)'), ('recording_url', 'https://u:p@example.com'),
                                        ('external_id', False), ('unknown', 1)])
def test_invalid_conversation(client, dialog, field, value):
    dialog[field] = value
    response = client.post('/api/conversations', json=dialog)
    assert response.status_code == 422
    assert response.json['error']['code'] == 'validation_error'
    assert client.get('/api/conversations').json['pagination']['total'] == 0


@pytest.mark.parametrize('messages', [
    [{'speaker': 'operator', 'text': 'x', 'start_ms': True}],
    [{'speaker': 'operator', 'text': 'x', 'start_ms': -1}],
    [{'speaker': 'operator', 'text': 'x', 'start_ms': 1.5}],
    [{'speaker': 'operator', 'text': 'x', 'start_ms': 10, 'end_ms': 9}],
    [{'speaker': 'operator', 'text': 'x', 'end_ms': 9}],
    [{'speaker': 'operator', 'text': 'x', 'start_ms': 10}, {'speaker': 'client', 'text': 'x', 'start_ms': 1}],
    [{'id': '1', 'speaker': 'operator', 'text': 'x'}, {'id': '1', 'speaker': 'client', 'text': 'y'}],
])
def test_invalid_transcript(client, dialog, messages):
    dialog['messages'] = messages
    assert client.post('/api/conversations', json=dialog).status_code == 422


@pytest.mark.parametrize('patch', [{'weight': True}, {'weight': 0}, {'weight': float('nan')},
                                  {'critical': 'false'}, {'rule': {'type': 'unknown'}},
                                  {'rule': {'type': 'contains_any', 'terms': {}}},
                                  {'rule': {'type': 'manual', 'terms': {'ru': ['x']}}}])
def test_invalid_checklist(client, checklist, patch):
    checklist['criteria'][0].update(patch)
    assert client.post('/api/checklists', json=checklist).status_code == 422


def test_unique_checklist_version_and_immutable_resources(client, checklist, dialog):
    first = client.post('/api/checklists', json=checklist)
    assert client.post('/api/checklists', json=checklist).status_code == 409
    checklist['version'] = 'v2'
    assert client.post('/api/checklists', json=checklist).status_code == 201
    assert client.patch(first.headers['Location'], json={'criteria': []}).status_code == 405
    dialog_response = client.post('/api/conversations', json=dialog)
    assert client.delete(dialog_response.headers['Location']).status_code == 405
    assert client.get(first.headers['Location']).json['version'] == 'demo-1'


def test_atomic_import_and_retry_conflict(client, dialog):
    copy = deepcopy(dialog)
    copy['external_id'] = 'second'
    imported = client.post('/api/conversations/import', json={'conversations': [dialog, copy]})
    assert imported.status_code == 201 and imported.json['imported'] == 2
    copy['external_id'] = 'third'
    assert client.post('/api/conversations/import', json={'conversations': [copy, dialog]}).status_code == 409
    assert client.get('/api/conversations').json['pagination']['total'] == 2
    copy['messages'] = []
    assert client.post('/api/conversations/import', json={'conversations': [copy]}).status_code == 422
    assert client.get('/api/conversations?external_id=third').json['items'] == []


def test_filters_pagination_and_errors(client, dialog):
    client.post('/api/conversations', json=dialog)
    assert client.get('/api/conversations?channel=call').json['items'] == []
    assert client.get('/api/conversations?language=ru&per_page=1').json['pagination']['total'] == 1
    for query in ('page=0', 'page=-1', 'page=abc', 'per_page=101', 'channel=no', 'page=999999999999999999'):
        assert client.get('/api/conversations?' + query).status_code == 422
    assert client.get('/api/conversations?page=99').json['items'] == []
    assert client.get('/api/unknown').status_code == 404
    assert client.get('/api/unknown').is_json
    assert client.post('/api/conversations', json=[]).status_code == 422
    assert client.post('/api/conversations', data='{', content_type='application/json').status_code == 400
    assert client.post('/api/conversations', data='{}').status_code == 415
    large = client.post('/api/conversations', data=b' ' * (4 * 1024 * 1024 + 1), content_type='application/json')
    assert large.status_code == 413 and large.is_json


def test_review_validation_rolls_back(client, evaluation):
    url = f'/api/evaluations/{evaluation["id"]}'
    payload = review_payload()
    payload['overrides'].append({'criterion_id': 'missing', 'status': 'pass', 'explanation': 'x'})
    assert client.post(url + '/reviews', json=payload).status_code == 422
    assert client.get(url).json['revision'] == 1
    assert client.get(url + '/reviews').json['items'] == []
    payload = review_payload()
    payload['expected_revision'] = True
    assert client.post(url + '/reviews', json=payload).status_code == 422


def test_concurrent_review_only_one_wins(app, client, evaluation):
    barrier = Barrier(2)
    with app.app_context():
        engine = db.engine

    def synchronize_updates(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE evaluations'):
            barrier.wait(timeout=10)

    def submit(status):
        with app.test_client() as isolated_client:
            return isolated_client.post(f'/api/evaluations/{evaluation["id"]}/reviews', json=review_payload(status=status)).status_code

    event.listen(engine, 'before_cursor_execute', synchronize_updates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit, status) for status in ('pass', 'fail')]
            statuses = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, 'before_cursor_execute', synchronize_updates)
    assert sorted(statuses) == [201, 409]
    assert client.get(f'/api/evaluations/{evaluation["id"]}').json['revision'] == 2
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(Review)) == 1


def test_migrations_preserve_data_and_match_models(app, client, dialog):
    from pathlib import Path
    item = client.post('/api/conversations', json=dialog).json
    with app.app_context():
        directory = str(Path(__file__).resolve().parents[1] / 'migrations')
        upgrade(directory=directory)
        check(directory=directory)
        assert db.session.get(Conversation, item['id']).title == dialog['title']
        db.session.add(Review(evaluation_id='absent', revision=2, reviewer='x', comment='x', changes=[]))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_cli_demo_is_explicit_and_repeatable(app, client):
    assert client.get('/api/stats').json['conversations'] == 0
    runner = app.test_cli_runner()
    first = runner.invoke(args=['seed-demo'])
    assert first.exit_code == 0, first.output
    assert runner.invoke(args=['seed-demo']).exit_code == 0
    assert client.get('/api/stats').json['conversations'] == 3
    assert client.get('/api/checklists').json['pagination']['total'] == 1
    assert client.get('/api/health').status_code == client.get('/api/ready').status_code == 200
    assert client.get('/api').json['authentication'] == 'none'
    assert client.get('/api/auth/login').status_code == 404


def test_readiness_detects_missing_schema(tmp_path):
    from app import create_app
    from config import TestingConfig
    class EmptyConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + (tmp_path / 'empty.db').as_posix()
    app = create_app(EmptyConfig)
    with app.test_client() as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/ready').status_code == 503
    with app.app_context():
        db.engine.dispose()


def test_cors_and_response_headers(client):
    allowed = client.get('/api', headers={'Origin': 'http://localhost:5173'})
    assert allowed.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'
    assert 'Access-Control-Allow-Origin' not in client.get('/api', headers={'Origin': 'https://unlisted.example'}).headers
    assert allowed.headers['Cache-Control'] == 'no-store'
    assert allowed.headers['X-Content-Type-Options'] == 'nosniff'
