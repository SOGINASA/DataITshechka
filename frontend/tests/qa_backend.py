from pathlib import Path
import sys
import tempfile
import os

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
from app import create_app
from config import TestingConfig
from flask_migrate import upgrade

with tempfile.TemporaryDirectory(prefix='bimbombam-api-qa-') as folder:
    class QAConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + (Path(folder) / 'qa.db').as_posix()
        CORS_ORIGINS = ['http://127.0.0.1:3001', 'http://localhost:3001']
        FREEDOM_API_URL = ''
        OLLAMA_MODEL = ''
    app = create_app(QAConfig)
    with app.app_context():
        upgrade(directory=str(root / 'backend/migrations'))
    result = app.test_cli_runner().invoke(args=['seed-checklist'])
    assert result.exit_code == 0, result.output
    print('Disposable QA database ready; no production data or external imports.', flush=True)
    app.run(host='127.0.0.1', port=int(os.environ.get('QA_API_PORT', '6769')), use_reloader=False)
