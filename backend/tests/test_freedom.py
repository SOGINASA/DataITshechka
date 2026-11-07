import io
import json
from copy import deepcopy
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest
from sqlalchemy import select, func

from models import Conversation, db
from services import freedom

URL = 'https://unit.environment.api.powerplatform.com/invoke?group_id=DEV'


@pytest.fixture
def payload():
    return {'error': '', 'isSuccess': True, 'data': {'dataset_group_id': 'DEV', 'total_records': 2, 'records': [
        {'conversation_id': 'test-ru-1', 'channel': 'agent chat', 'language': 'RU', 'audio_url': None,
         'transcript': [{'timestamp': '00:02', 'speaker': 'client', 'text': '  Тестовый вопрос  '},
                        {'timestamp': '01:03', 'speaker': 'operator', 'text': 'Тестовый ответ'}]},
        {'conversation_id': 'test-kz-1', 'channel': 'voice call', 'language': 'KZ', 'audio_url': 'https://example.org/audio.wav',
         'transcript': [{'timestamp': '2026-11-03T15:49:13.1900670+00:00', 'speaker': 'operator', 'text': 'Сәлеметсіз бе!'},
                        {'timestamp': '2026-11-03T15:49:22.4171535+00:00', 'speaker': 'client', 'text': 'Сұрақ'}]}
    ]}}


def test_normalization_preserves_timing_and_text(payload):
    chat, call = freedom.normalize_dataset(payload)
    assert chat['external_id'] == 'freedom:DEV:test-ru-1'
    assert chat['messages'][0]['text'] == '  Тестовый вопрос  '
    assert chat['messages'][1]['start_ms'] == 63000
    assert chat['source_metadata']['timestamp_reference'] == 'conversation_start'
    assert call['language'] == 'kk' and call['channel'] == 'call'
    assert call['messages'][0]['start_ms'] == 0 and call['messages'][1]['start_ms'] == 9227
    assert call['source_metadata']['timestamp_reference'] == 'first_message'
    assert call['source_metadata']['audio_alignment_verified'] is False
    assert call['source_metadata']['source_timestamps']['2'] == '2026-11-03T15:49:22.4171535+00:00'


def test_repeatable_import_and_no_overwrite(app, client, payload):
    with app.app_context():
        dry = freedom.import_dataset(payload, dry_run=True)
        assert dry['pending'] == 2 and dry['imported'] == 0
        assert db.session.scalar(select(func.count()).select_from(Conversation)) == 0
        assert freedom.import_dataset(payload)['imported'] == 2
        repeated = freedom.import_dataset(payload)
        assert repeated['imported'] == 0 and repeated['skipped'] == 2
        modified = deepcopy(payload)
        modified['data']['records'][0]['transcript'][0]['text'] = 'Changed source'
        with pytest.raises(freedom.ImportConflict):
            freedom.import_dataset(modified)
        stored = db.session.scalar(select(Conversation).where(Conversation.external_id == 'freedom:DEV:test-ru-1'))
        assert stored.messages[0]['text'] == '  Тестовый вопрос  '
        assert db.session.scalar(select(func.count()).select_from(Conversation)) == 2
        identifier = stored.id
    response = client.get('/api/conversations/' + identifier)
    assert response.json['source_metadata']['provider'] == 'freedom'


@pytest.mark.parametrize('case', ['failure', 'group', 'count', 'duplicate', 'channel', 'language', 'speaker',
                                  'reverse_time', 'invalid_time', 'mixed_time', 'no_timezone', 'empty', 'unknown_key'])
def test_invalid_batch_is_atomic(app, payload, case):
    data = payload['data']
    record = data['records'][1]
    if case == 'failure':
        payload['isSuccess'] = False
        payload['error'] = 'upstream confidential text'
    elif case == 'group':
        data['dataset_group_id'] = 'PRIVATE'
    elif case == 'count':
        data['total_records'] = 99
    elif case == 'duplicate':
        record['conversation_id'] = data['records'][0]['conversation_id']
    elif case in ('channel', 'language'):
        record[case] = 'unknown'
    elif case == 'speaker':
        record['transcript'][0]['speaker'] = 'unknown'
    elif case == 'reverse_time':
        record['transcript'].reverse()
    elif case == 'invalid_time':
        record['transcript'][0]['timestamp'] = '00:99'
    elif case == 'mixed_time':
        record['transcript'][0]['timestamp'] = '00:01'
    elif case == 'no_timezone':
        record['transcript'][0]['timestamp'] = '2026-11-03T15:49:13'
    elif case == 'empty':
        record['transcript'] = []
    elif case == 'unknown_key':
        record['unexpected'] = True
    with app.app_context():
        with pytest.raises(freedom.IntegrationError) as caught:
            freedom.import_dataset(payload)
        assert 'confidential' not in str(caught.value)
        assert db.session.scalar(select(func.count()).select_from(Conversation)) == 0


@pytest.mark.parametrize('url', ['', 'http://unit.environment.api.powerplatform.com/?group_id=DEV',
                                 'https://example.org/?group_id=DEV',
                                 'https://unit.environment.api.powerplatform.com.evil.org/?group_id=DEV',
                                 'https://user:password@unit.environment.api.powerplatform.com/?group_id=DEV',
                                 'https://unit.environment.api.powerplatform.com/?group_id=OTHER',
                                 'https://unit.environment.api.powerplatform.com/?group_id=DEV&group_id=OTHER'])
def test_disallowed_source_urls(url):
    with pytest.raises(freedom.IntegrationError):
        freedom.validate_url(url)


class Response(io.BytesIO):
    status = 200

    def __init__(self, content, content_type='application/json'):
        super().__init__(content)
        self.headers = Message()
        self.headers['Content-Type'] = content_type


def mock_transport(monkeypatch, response=None, exception=None):
    class Opener:
        def open(self, req, timeout):
            assert req.method == 'GET' and timeout == 30
            if exception:
                raise exception
            return response
    monkeypatch.setattr(freedom.request, 'build_opener', lambda handler: Opener())


def test_network_success_and_errors(monkeypatch, payload):
    mock_transport(monkeypatch, Response(json.dumps(payload).encode()))
    assert freedom.fetch_dataset(URL) == payload
    mock_transport(monkeypatch, exception=HTTPError(URL + '&sig=secret-value', 403, 'secret-value', {}, None))
    with pytest.raises(freedom.IntegrationError) as caught:
        freedom.fetch_dataset(URL)
    assert '403' in str(caught.value) and 'secret-value' not in str(caught.value)
    mock_transport(monkeypatch, exception=URLError('secret-value'))
    with pytest.raises(freedom.IntegrationError) as caught:
        freedom.fetch_dataset(URL)
    assert 'secret-value' not in str(caught.value)
    mock_transport(monkeypatch, Response(b'{}', content_type='text/html'))
    with pytest.raises(freedom.IntegrationError):
        freedom.fetch_dataset(URL)
    mock_transport(monkeypatch, Response(b'not-json'))
    with pytest.raises(freedom.IntegrationError):
        freedom.fetch_dataset(URL)
    mock_transport(monkeypatch, Response(b' ' * (freedom.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(freedom.IntegrationError, match='8'):
        freedom.fetch_dataset(URL)
    assert freedom.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example') is None


def test_cli_file_import(app, tmp_path, payload):
    source = tmp_path / 'synthetic.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    runner = app.test_cli_runner()
    dry = runner.invoke(args=['import-dev', '--file', str(source), '--dry-run'])
    assert dry.exit_code == 0 and json.loads(dry.output)['pending'] == 2
    real = runner.invoke(args=['import-dev', '--file', str(source)])
    assert real.exit_code == 0 and json.loads(real.output)['imported'] == 2
    retry = runner.invoke(args=['import-dev', '--file', str(source)])
    assert retry.exit_code == 0 and json.loads(retry.output)['skipped'] == 2
    app.config['FREEDOM_API_URL'] = ''
    missing = runner.invoke(args=['import-dev'])
    assert missing.exit_code != 0 and 'FREEDOM_API_URL' in missing.output


def test_upgrade_preserves_pre_integration_dialogue(tmp_path):
    from pathlib import Path
    from app import create_app
    from config import TestingConfig
    from flask_migrate import upgrade
    from sqlalchemy import text
    class OldDatabase(TestingConfig):
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + (tmp_path / 'previous.db').as_posix()
    application = create_app(OldDatabase)
    directory = str(Path(__file__).resolve().parents[1] / 'migrations')
    with application.app_context():
        upgrade(directory=directory, revision='c2349e861e54')
        db.session.execute(text('INSERT INTO conversations (id,title,channel,language,messages,created_at) '
                                'VALUES (:id,:title,:channel,:language,:messages,:created_at)'),
                           {'id': 'existing', 'title': 'Existing dialogue', 'channel': 'chat', 'language': 'en',
                            'messages': '[{"id":"1","speaker":"client","text":"Original"}]',
                            'created_at': '2026-11-07 00:00:00'})
        db.session.commit()
        upgrade(directory=directory)
        stored = db.session.get(Conversation, 'existing')
        assert stored.source_metadata is None and stored.messages[0]['text'] == 'Original'
        db.session.remove()
        db.engine.dispose()
