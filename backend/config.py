import os
from pathlib import Path
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parent


def database_url(value=None):
    """Явный URL имеет приоритет; локально SQLite, в Compose PostgreSQL."""
    if value:
        url = make_url(value)
        if url.drivername in ('postgres', 'postgresql'):
            url = url.set(drivername='postgresql+psycopg')
        if url.drivername in ('sqlite', 'sqlite+pysqlite'):
            if url.database and url.database != ':memory:':
                path = Path(url.database)
                if not path.is_absolute():
                    path = BACKEND_DIR / path
                url = url.set(database=str(path.resolve()))
        elif url.drivername != 'postgresql+psycopg':
            raise ValueError('DATABASE_URL must use SQLite or PostgreSQL with psycopg')
        return url

    engine = os.environ.get('DATABASE_ENGINE', 'sqlite').strip().lower()
    if engine == 'sqlite':
        return URL.create('sqlite', database=str(BACKEND_DIR / 'database' / 'database.db'))
    if engine != 'postgresql':
        raise ValueError('DATABASE_ENGINE must be sqlite or postgresql')
    return URL.create(
        'postgresql+psycopg',
        username=os.environ.get('POSTGRES_USER', 'cqa'),
        password=os.environ.get('POSTGRES_PASSWORD'),
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', '5432')),
        database=os.environ.get('POSTGRES_DB', 'cqa'),
    )


def _cors_origins():
    """CORS origins из env (через запятую) или дефолт для локальной разработки"""
    raw = os.environ.get('CORS_ORIGINS')
    if raw:
        return [o.strip() for o in raw.split(',') if o.strip()]
    return ['http://localhost:3000', 'http://localhost:5173', 'http://127.0.0.1:3000', 'http://127.0.0.1:5173']


class Config:
    SQLALCHEMY_DATABASE_URI = database_url(os.environ.get('DATABASE_URL'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

    # CORS
    CORS_ORIGINS = _cors_origins()

    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    FREEDOM_API_URL = os.environ.get('FREEDOM_API_URL', '')
    OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', '')
    OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '120'))
    OLLAMA_NUM_CTX = int(os.environ.get('OLLAMA_NUM_CTX', '32768'))
    OLLAMA_NUM_PREDICT = int(os.environ.get('OLLAMA_NUM_PREDICT', '4096'))
    OLLAMA_NUM_CTX_CALL = int(os.environ['OLLAMA_NUM_CTX_CALL']) if os.environ.get('OLLAMA_NUM_CTX_CALL') else None
    OLLAMA_NUM_PREDICT_CALL = int(os.environ['OLLAMA_NUM_PREDICT_CALL']) if os.environ.get('OLLAMA_NUM_PREDICT_CALL') else None
    # None preserves the model default. Qwen3 local baseline uses false.
    OLLAMA_THINK = {'true': True, 'false': False, '': None}[os.environ.get('OLLAMA_THINK', '').lower()]


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = False


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}


def get_config():
    """Получить текущую конфигурацию по FLASK_ENV"""
    return config.get(os.environ.get('FLASK_ENV') or 'default', DevelopmentConfig)


