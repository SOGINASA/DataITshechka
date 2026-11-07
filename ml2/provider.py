"""Bounded local Ollama client. Never downloads models, follows redirects or silently retries."""
from dataclasses import asdict, dataclass
import json
import math
import os
import time
from urllib import request, error
from urllib.parse import urlsplit
from .contracts import loads


class ModelError(RuntimeError):
    def __init__(self, message, *, code='model_error', details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class Settings:
    base_url: str = 'http://127.0.0.1:11434'
    model: str = 'qwen3:8b'
    context: int = 20480
    output_tokens: int = 2048
    timeout: int = 600
    seed: int = 7
    think: bool = True
    temperature: float = 0.6
    top_p: float = 0.95
    top_k: int = 20
    min_p: float = 0.0

    @classmethod
    def environment(cls):
        return cls(os.getenv('ML2_OLLAMA_URL', cls.base_url), os.getenv('ML2_MODEL', cls.model),
                   int(os.getenv('ML2_CONTEXT', cls.context)), int(os.getenv('ML2_OUTPUT_TOKENS', cls.output_tokens)),
                   int(os.getenv('ML2_TIMEOUT', cls.timeout)), int(os.getenv('ML2_SEED', cls.seed)),
                   cls.parse_think(os.getenv('ML2_THINK', 'true')),
                   float(os.getenv('ML2_TEMPERATURE', cls.temperature)),
                   float(os.getenv('ML2_TOP_P', cls.top_p)),
                   int(os.getenv('ML2_TOP_K', cls.top_k)),
                   float(os.getenv('ML2_MIN_P', cls.min_p)))

    @staticmethod
    def parse_think(value):
        if value not in ('true', 'false'):
            raise ModelError('ML2_THINK must be true or false')
        return value == 'true'

    def validate(self):
        parts = urlsplit(self.base_url)
        if (parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1') or
                parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ModelError('ML2_OLLAMA_URL must point to local HTTP Ollama; no cloud upload configured')
        if not self.model or not 4096 <= self.context <= 131072 or not 256 <= self.output_tokens < self.context - 2048:
            raise ModelError('Invalid model/context/output settings')
        if not 1 <= self.timeout <= 600:
            raise ModelError('Timeout must be 1..600 seconds')
        if type(self.think) is not bool:
            raise ModelError('think must be boolean')
        for value, low, high in ((self.temperature, 0, 2), (self.top_p, .0001, 1), (self.min_p, 0, 1)):
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ModelError('Invalid sampling settings')
        if type(self.top_k) is not int or not 1 <= self.top_k <= 1000:
            raise ModelError('Invalid top_k')


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def grammar_schema(value):
    """Ollama 0.32.14 rejects bounded repetitions in this schema's grammar.

    Keep object fields/types/enums on the wire; enforce lengths/counts in our validator.
    Never mutate the canonical schema or relax semantic validation.
    """
    if isinstance(value, dict):
        return {k: grammar_schema(v) for k, v in value.items()
                if k not in ('minItems', 'maxItems', 'minLength', 'maxLength')}
    if isinstance(value, list):
        return [grammar_schema(v) for v in value]
    return value


class Ollama:
    def __init__(self, settings):
        settings.validate()
        self.settings = settings
        self.deadline = None
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect)

    def _request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        req = request.Request(self.settings.base_url.rstrip('/') + path, data=data,
                              headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            timeout = self.settings.timeout if payload is not None else min(10, self.settings.timeout)
            if self.deadline is not None:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise ModelError('Run deadline exceeded')
                timeout = min(timeout, remaining)
            with self.opener.open(req, timeout=timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ModelError('Model response exceeds 2 MiB')
            return loads(raw)
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ModelError(f'Ollama HTTP {code}') from None
        except (OSError, error.URLError, ValueError) as exc:
            raise ModelError('Ollama unavailable, timeout or malformed response') from None

    def identity(self):
        tags = self._request('/api/tags')
        for model in tags.get('models', []):
            if model.get('name') in (self.settings.model, self.settings.model + ':latest'):
                return {'model': model['name'], 'digest': model['digest'],
                        'settings': asdict(self.settings), 'provider': 'ollama',
                        'server_version': self._request('/api/version').get('version'),
                        'runtime_notes': os.getenv('ML2_RUNTIME_NOTES', '')}
        raise ModelError('Requested model is not installed; no model was downloaded')

    def complete(self, messages, schema):
        cfg = self.settings
        wire_schema = grammar_schema(schema)
        # Conservative UTF-8 budget (including schema) before sending; never truncate a dialogue.
        size = len(json.dumps({'messages': messages, 'format': wire_schema}, ensure_ascii=False,
                              separators=(',', ':')).encode())
        if size + cfg.output_tokens + 1024 > cfg.context:
            input_limit = cfg.context - cfg.output_tokens - 1024
            raise ModelError(f'Контекст не вмещает запрос: примерно {size} байт при лимите входа '
                             f'{input_limit} байт (контекст {cfg.context}, запас на ответ {cfg.output_tokens}). '
                             'Увеличьте ML2_CONTEXT или сократите промпт/вход; диалог не обрезан.',
                             code='context_budget_exceeded',
                             details={'request_bytes': size, 'input_budget_bytes': input_limit,
                                      'context': cfg.context, 'output_reserve': cfg.output_tokens,
                                      'safety_margin_bytes': 1024})
        result = self._request('/api/chat', {'model': cfg.model, 'stream': False, 'think': cfg.think,
            'keep_alive': '5m', 'format': wire_schema, 'messages': messages,
            'options': {'temperature': cfg.temperature, 'top_p': cfg.top_p, 'top_k': cfg.top_k,
                        'min_p': cfg.min_p, 'seed': cfg.seed, 'num_ctx': cfg.context, 'num_predict': cfg.output_tokens}})
        usage = {k: result[k] for k in ('prompt_eval_count', 'eval_count', 'total_duration', 'load_duration')
                 if type(result.get(k)) is int and result[k] >= 0}
        if result.get('done') is not True or result.get('done_reason') == 'length':
            limit = result.get('done_reason') == 'length'
            message = f'Model reached output limit ({cfg.output_tokens} tokens); no partial assessment saved' if limit else 'Model generation did not finish; no partial assessment saved'
            raise ModelError(message, code='generation_limit' if limit else 'generation_incomplete',
                             details={'done_reason': result.get('done_reason'), 'output_token_limit': cfg.output_tokens,
                                      'usage': usage})
        content = result.get('message', {}).get('content')
        if not isinstance(content, str):
            raise ModelError('No model content')
        return content, usage
