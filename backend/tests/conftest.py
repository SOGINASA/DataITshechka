import json
import sys
from pathlib import Path

import pytest
from flask_migrate import upgrade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from config import TestingConfig
from models import db


@pytest.fixture
def app(tmp_path):
    class IsolatedConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + (tmp_path / 'cqa-test.db').as_posix()
    application = create_app(IsolatedConfig)
    with application.app_context():
        upgrade(directory=str(ROOT / 'migrations'))
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def dialog():
    return json.loads((ROOT / 'examples' / 'conversations.json').read_text(encoding='utf-8'))['conversations'][0]


@pytest.fixture
def checklist():
    return json.loads((ROOT / 'examples' / 'checklist.json').read_text(encoding='utf-8'))


@pytest.fixture
def evaluation(client, dialog, checklist):
    conv = client.post('/api/conversations', json=dialog)
    rubric = client.post('/api/checklists', json=checklist)
    assert conv.status_code == rubric.status_code == 201
    response = client.post(f'/api/conversations/{conv.json["id"]}/evaluations', json={'checklist_id': rubric.json['id']})
    assert response.status_code == 201
    return response.json
