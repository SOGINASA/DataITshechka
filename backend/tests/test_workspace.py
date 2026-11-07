from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import event

from models import db, Conversation, Evaluation, Appeal


def validate_response(client, template, response):
    assert response.status_code == 200, response.json
    spec = client.get('/api/openapi.json').json
    schema = spec['paths'][template]['get']['responses']['200']['content']['application/json']['schema']
    Draft202012Validator({**schema, 'components': spec['components']}).validate(response.json)


def test_overview_is_bounded_and_list_filters_cover_all_pages(app, client):
    with app.app_context():
        for i in range(65):
            db.session.add(Conversation(id=f'conversation-{i:03}', title=f'Conversation {i}',
                                       language='kk' if i == 0 else 'ru', channel='chat', operator_name='Operator',
                                       messages=[{'text': 'TRANSCRIPT_MUST_NOT_BE_SENT', 'id': '1'}],
                                       created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)))
        db.session.commit()
        queries = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            response = client.get('/api/workspace/overview')
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
    validate_response(client, '/api/workspace/overview', response)
    assert response.json['total'] == 65
    assert response.json['assessed'] == 0 and response.json['average'] is None
    assert len(response.json['recent']) == 6
    assert len(queries) == 2  # Latest summaries and a bounded appeal queue, independent of N.
    assert all('conversations.messages' not in sql for sql in queries)
    assert 'TRANSCRIPT_MUST_NOT_BE_SENT' not in response.text
    assert len(response.json['trend']) == 7
    seen = []
    for page, expected in [(1, 20), (2, 20), (3, 20), (4, 5)]:
        response = client.get(f'/api/workspace/conversations?page={page}')
        validate_response(client, '/api/workspace/conversations', response)
        assert len(response.json['items']) == expected
        assert response.json['pagination']['total'] == 65
        seen.extend(c['id'] for c in response.json['items'])
        assert 'TRANSCRIPT_MUST_NOT_BE_SENT' not in response.text
    assert len(set(seen)) == 65
    for query in ('search=Conversation%200', 'language=kk', 'search=conversation-000&channel=chat&status=pending'):
        data = client.get('/api/workspace/conversations?' + query).json
        assert data['pagination']['total'] == 1
        assert data['items'][0]['id'] == 'conversation-000'
    assert client.get('/api/workspace/conversations?status=assessed').json['items'] == []


def test_latest_evaluation_score_and_appeal_context(app, client, evaluation):
    conversation_id = evaluation['conversation_id']
    with app.app_context():
        original = db.session.get(Evaluation, evaluation['id'])
        results = deepcopy(original.results)
        for r in results:
            r.update(status='fail', value=False, source='human')
        # Tie on created_at: ID must choose the same latest run on all screens.
        original.id = 'a-old'
        newest = Evaluation(id='z-latest', conversation_id=conversation_id, checklist_id=original.checklist_id,
                            engine='test', original_results=deepcopy(results), results=results,
                            created_at=original.created_at)
        db.session.add(newest)
        db.session.commit()
    data = client.get('/api/workspace/overview').json
    assert data['assessed'] == 1 and data['average'] == 0 and data['attention'] == 1
    assert data['recent'][0]['evaluation_id'] == 'z-latest'
    assert client.get('/api/workspace/conversations?status=pending').json['pagination']['total'] == 0
    assert client.get('/api/workspace/conversations?status=attention').json['pagination']['total'] == 1
    appeal = client.post('/api/evaluations/z-latest/appeals', json={
        'criterion_id': 'greeting', 'expected_revision': 1, 'author': 'QA', 'comment': 'Please check'})
    assert appeal.status_code == 201, appeal.json
    assert client.get('/api/workspace/conversations?status=appeal').json['pagination']['total'] == 1
    response = client.get('/api/workspace/appeals')
    validate_response(client, '/api/workspace/appeals', response)
    assert response.json['selected_id'] == appeal.json['id']
    assert response.json['detail']['conversation']['id'] == conversation_id
    assert len(response.json['detail']['evaluations']) == 2
    assert response.json['open_appeals'] == 1
    response = client.get(f'/api/workspace/conversations/{conversation_id}')
    validate_response(client, '/api/workspace/conversations/{conversation_id}', response)
    assert [e['id'] for e in response.json['evaluations']] == ['a-old', 'z-latest']
    assert response.json['conversation']['messages']
    assert len(response.json['appeals']) == 1
    decision = client.post(f'/api/appeals/{appeal.json["id"]}/decision', json={
        'expected_revision': 1, 'decision': 'change', 'reviewer': 'QA', 'reason': 'Greeting found',
        'override': {'criterion_id': 'greeting', 'value': True, 'explanation': 'Found', 'evidence_message_ids': ['m2']}})
    assert decision.status_code == 200, decision.json
    overview = client.get('/api/workspace/overview').json
    assert overview['open_appeals'] == 0
    assert overview['average'] == decision.json['evaluation']['final_score']
    response = client.get(f'/api/workspace/appeals?selected={appeal.json["id"]}')
    assert response.json['status'] == 'resolved'
    assert response.json['detail']['reviews'][0]['id'] == decision.json['review']['id']


def test_pending_and_all_na_are_not_zero_scores(app, client, evaluation):
    overview = client.get('/api/workspace/overview').json
    assert overview['assessed'] == 0 and overview['average'] is None and overview['attention'] == 0
    with app.app_context():
        e = db.session.get(Evaluation, evaluation['id'])
        e.results = [{**r, 'status': 'not_applicable', 'value': None, 'source': 'human'} for r in e.results]
        db.session.commit()
    overview = client.get('/api/workspace/overview').json
    assert overview['assessed'] == 1 and overview['average'] is None and overview['attention'] == 0


def test_appeals_are_paginated_and_overview_counts_hidden_records(app, client, evaluation):
    with app.app_context():
        source = db.session.get(Evaluation, evaluation['id'])
        source_conversation = db.session.get(Conversation, source.conversation_id)
        results = [{**r, 'status': 'pass', 'value': True, 'source': 'human'} for r in source.results]
        source.results = results
        # Assessed conversation is deliberately older than the six recent rows.
        source_conversation.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for i in range(25):
            c = Conversation(id=f'other-{i}', title='Other', channel='chat', language='ru', messages=source_conversation.messages)
            db.session.add(c)
            db.session.flush()
            e = Evaluation(id=f'e-{i}', conversation_id=c.id, checklist_id=source.checklist_id,
                           engine='test', results=source.original_results, original_results=source.original_results)
            db.session.add(e)
            db.session.flush()
            db.session.add(Appeal(evaluation_id=e.id, criterion_id='greeting', evaluation_revision=1,
                                 author='QA', comment='Check', disputed_result=deepcopy(e.results[0])))
        db.session.commit()
    overview = client.get('/api/workspace/overview').json
    assert overview['total'] == 26 and overview['assessed'] == 1 and overview['average'] == 100
    assert overview['open_appeals'] == 25 and len(overview['appeals']) == 4
    assert evaluation['conversation_id'] not in [c['id'] for c in overview['recent']]
    first = client.get('/api/workspace/appeals').json
    second = client.get('/api/workspace/appeals?page=2').json
    assert len(first['items']) == 20 and len(second['items']) == 5
    assert second['pagination']['total'] == 25
    assert set(a['id'] for a in first['items']).isdisjoint(a['id'] for a in second['items'])
    assert second['detail']['conversation']['id'] == second['items'][0]['conversation_id']
    assert all('disputed_result' not in a for a in first['items'])
    selected = client.get(f'/api/workspace/appeals?status=all&page=2&selected={second["items"][0]["id"]}').json
    assert selected['status'] == 'all' and selected['pagination']['page'] == 2


@pytest.mark.parametrize('path', [
    '/conversations?page=0', '/conversations?per_page=101', '/conversations?page=1.5',
    '/conversations?status=bad', '/conversations?language=bad', '/conversations?channel=bad',
    '/conversations?search=' + 'x' * 201, '/appeals?status=bad', '/appeals?page=0',
])
def test_invalid_screen_filters(client, path):
    assert client.get('/api/workspace' + path).status_code == 422


def test_empty_and_missing_screens(client):
    for path in ('/overview', '/conversations', '/appeals'):
        response = client.get('/api/workspace' + path)
        validate_response(client, '/api/workspace' + path, response)
    assert client.get('/api/workspace/conversations/missing').status_code == 404
    assert client.get('/api/workspace/appeals?selected=missing').status_code == 404
