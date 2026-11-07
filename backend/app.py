import json
import os
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate, upgrade
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.exceptions import HTTPException

load_dotenv(Path(__file__).with_name('.env'))

from config import get_config
from models import db, Conversation, Checklist
from services.validation import ValidationError

migrate = Migrate()
ROOT = Path(__file__).resolve().parent


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())
    app.json.ensure_ascii = False
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=False)
    url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    if url.get_backend_name() == 'sqlite' and url.database not in (None, '', ':memory:'):
        path = Path(url.database)
        if not path.is_absolute():
            path = Path(app.instance_path) / path
        path.parent.mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db, directory=str(ROOT / 'migrations'))
    from routes import cqa_bp
    app.register_blueprint(cqa_bp, url_prefix='/api')

    @app.get('/api')
    def api_info():
        return jsonify({'name': 'CQA — анализ качества диалогов', 'version': '1.0.0',
                        'authentication': 'none', 'languages': ['ru', 'kk', 'en'],
                        'evaluation_engine': 'keyword-baseline-v1',
                        'openapi': '/api/openapi.json'})

    @app.get('/api/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.get('/api/ready')
    def readiness():
        try:
            db.session.execute(select(Conversation.id).limit(1))
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({'status': 'database_unavailable_or_uninitialized'}), 503
        return jsonify({'status': 'ready'})

    @app.get('/api/openapi.json')
    def openapi():
        from api_schema import specification
        return jsonify(specification())

    @app.errorhandler(ValidationError)
    def validation_error(error):
        return jsonify({'error': {'code': 'validation_error', 'message': str(error)}}), 422

    @app.errorhandler(StaleDataError)
    def stale_revision(_):
        db.session.rollback()
        return jsonify({'error': {'code': 'revision_conflict', 'message': 'Оценка уже изменена. Загрузите актуальную версию.'}}), 409

    @app.errorhandler(IntegrityError)
    def integrity_error(_):
        db.session.rollback()
        return jsonify({'error': {'code': 'conflict', 'message': 'Конфликт данных: external_id или версия чек-листа уже существуют.'}}), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = app.json.dumps({'error': {'code': error.name.lower().replace(' ', '_'), 'message': error.description}})
        response.content_type = 'application/json'
        return response

    @app.errorhandler(SQLAlchemyError)
    def database_error(_):
        db.session.rollback()
        # SQLAlchemy exceptions may embed transcript text and SQL parameters.
        app.logger.error('Database operation failed; request data omitted.')
        return jsonify({'error': {'code': 'database_unavailable', 'message': 'База данных недоступна.'}}), 503

    @app.errorhandler(500)
    def internal_error(_):
        return jsonify({'error': {'code': 'internal_error', 'message': 'Внутренняя ошибка сервера.'}}), 500

    @app.after_request
    def response_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.cli.command('init-db')
    def init_db():
        """Apply committed migrations (same as flask db upgrade)."""
        upgrade(directory=str(ROOT / 'migrations'))
        click.echo('Миграции применены.')

    @app.cli.command('seed-demo')
    def seed_demo():
        """Explicitly load synthetic examples. Never called on server startup."""
        from services.validation import checklist, conversation
        data = json.loads((ROOT / 'examples' / 'checklist.json').read_text(encoding='utf-8'))
        existing = db.session.scalar(select(Checklist).where(Checklist.name == data['name'], Checklist.version == data['version']))
        if not existing:
            db.session.add(Checklist(**checklist(data)))
        dialogs = json.loads((ROOT / 'examples' / 'conversations.json').read_text(encoding='utf-8'))
        for value in dialogs['conversations']:
            if not db.session.scalar(select(Conversation.id).where(Conversation.external_id == value['external_id'])):
                db.session.add(Conversation(**conversation(value)))
        db.session.commit()
        click.echo('Демонстрационные данные загружены. Это не данные и не чек-лист организаторов.')

    @app.cli.command('import-dev')
    @click.option('--dry-run', is_flag=True, help='Validate and compare without saving records.')
    @click.option('--file', 'source_file', type=click.Path(exists=True, dir_okay=False, path_type=Path),
                  help='Read a saved DEV response instead of calling the API.')
    def import_dev(dry_run, source_file):
        """Import Freedom DEV data. Repeated identical imports skip existing dialogues."""
        from services.freedom import (IntegrationError, MAX_RESPONSE_BYTES, decode_payload,
                                     fetch_dataset, import_dataset)
        try:
            if source_file:
                with source_file.open('rb') as stream:
                    payload = decode_payload(stream.read(MAX_RESPONSE_BYTES + 1))
            else:
                payload = fetch_dataset(app.config['FREEDOM_API_URL'])
            result = import_dataset(payload, dry_run=dry_run)
        except IntegrationError as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from None
        except OSError:
            db.session.rollback()
            raise click.ClickException('Не удалось прочитать файл DEV-данных.') from None
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException('База данных недоступна. Проверьте настройки и выполните flask db upgrade.') from None
        click.echo(json.dumps(result, ensure_ascii=False))

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.environ.get('PORT', 5000)))
