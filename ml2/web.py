"""Loopback-only ML2 playground with one durable local evaluation at a time."""
import argparse
from datetime import datetime, timezone
from datetime import date as calendar_date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
import threading
import uuid

from .cli import main as run_cli
from .contracts import ContractError, conversation, loads, read_json, require, write_json
from .provider import Ollama, Settings, ModelError
from .knowledge import KnowledgeBase

ROOT = Path(__file__).parent
ROLES = {'клиент': 'client', 'оператор': 'operator', 'бот': 'bot', 'система': 'system',
         'client': 'client', 'operator': 'operator', 'bot': 'bot', 'system': 'system'}
ROLE_LINE = re.compile(r'^(клиент|оператор|бот|система|client|operator|bot|system)\s*:\s*(.*)$', re.I)


def parse_input(payload):
    require(isinstance(payload, dict), 'Ожидается объект запроса.')
    source = payload.get('source')
    require(isinstance(source, str) and bool(source.strip()), 'Вставьте текст диалога или JSON.')
    base = {'conversation_id': 'manual-' + uuid.uuid4().hex[:12],
            'language': payload.get('language', 'ru'), 'channel': payload.get('channel', 'chat'),
            'start_truncated': payload.get('start_truncated', False)}
    if payload.get('format') == 'json':
        raw = loads(source)
        if isinstance(raw, list):
            raw = {'messages': raw}
        require(isinstance(raw, dict), 'Вставьте один диалог или массив его реплик.')
        if 'data' in raw and isinstance(raw['data'], dict) and 'records' in raw['data']:
            require(raw.get('isSuccess') is True and len(raw['data']['records']) == 1,
                    'Для этой страницы выберите один диалог из набора.')
            raw = raw['data']['records'][0]
        # Preserve organizer IDs instead of shadowing external_id/id with a generated ID.
        if raw.get('external_id') or raw.get('id'):
            base.pop('conversation_id')
        raw = {**base, **raw}
    else:
        require(payload.get('format') == 'text', 'Неизвестный формат ввода.')
        messages = []
        for line in source.splitlines():
            found = ROLE_LINE.match(line.strip())
            if found:
                messages.append({'id': str(len(messages) + 1), 'speaker': ROLES[found[1].lower()], 'text': found[2]})
            elif line.strip():
                require(bool(messages), 'Начните реплику с «Клиент:» или «Оператор:».')
                messages[-1]['text'] += '\n' + line
        raw = {**base, 'messages': messages}
    result = conversation(raw)
    require(any(m['speaker'] == 'operator' for m in result['messages']), 'В диалоге нет реплик оператора.')
    return result


class BusyError(Exception):
    pass


class Jobs:
    def __init__(self, directory, runner=run_cli):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.runner = runner
        self.lock = threading.Lock()
        self.active = None
        # A server restart must never leave the browser waiting for a vanished worker.
        for path in self.directory.glob('*/job.json'):
            job = read_json(path)
            if job['status'] == 'running':
                job.update(status='error', error='Сервер был перезапущен. Запустите оценку заново.')
                write_json(path, job)

    def get(self, identifier):
        require(re.fullmatch('[0-9a-f]{32}', identifier) is not None, 'Неизвестный запуск.')
        return read_json(self.directory / identifier / 'job.json')

    def recent(self):
        files = sorted(self.directory.glob('*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        return [read_json(p) for p in files]

    def start(self, dialog, knowledge=None, as_of=None):
        with self.lock:
            if self.active:
                raise BusyError(self.active)
            identifier = uuid.uuid4().hex
            folder = self.directory / identifier
            folder.mkdir()
            write_json(folder / 'input.json', dialog)
            if knowledge is not None:
                write_json(folder / 'knowledge.json', knowledge)
            job = {'id': identifier, 'status': 'running', 'conversation_id': dialog['conversation_id'],
                   'created_at': datetime.now(timezone.utc).isoformat(), 'messages': len(dialog['messages']),
                   'knowledge_version': knowledge['version'] if knowledge is not None else None,
                   'knowledge_documents': len(knowledge['documents']) if knowledge is not None else 0,
                   'knowledge_as_of': as_of}
            write_json(folder / 'job.json', job)
            self.active = identifier
            threading.Thread(target=self._work, args=(job, dialog), daemon=True).start()
            return dict(job)

    def _work(self, job, dialog):
        folder = self.directory / job['id']
        checklist = ROOT / 'configs' / ('voice.json' if dialog['channel'] == 'call' else 'chat.json')
        try:
            args = ['run', '--input', str(folder / 'input.json'), '--output', str(folder / 'run'),
                    '--rubric', str(checklist), '--deadline-seconds', '600']
            if (folder / 'knowledge.json').exists():
                args.extend(['--knowledge', str(folder / 'knowledge.json')])
            if job.get('knowledge_as_of'):
                args.extend(['--as-of', job['knowledge_as_of']])
            code = self.runner(args)
            prediction_file = folder / 'run/predictions.jsonl'
            if not prediction_file.exists():
                raise ModelError('Модель недоступна. Проверьте Ollama и повторите запуск.')
            prediction = loads(prediction_file.read_text().splitlines()[0])
            if code or prediction['status'] != 'ok':
                raise ModelError(prediction.get('error', 'Не удалось завершить оценку.'), code=prediction.get('error_code', 'model_error'))
            job['status'] = 'done'
        except (OSError, ValueError, TypeError, KeyError, ModelError) as exc:
            job.update(status='error', error=str(exc))
            if isinstance(exc, ModelError):
                job['error_code'] = exc.code
        except Exception:
            job.update(status='error', error='Внутренняя ошибка. Исходный диалог сохранён; можно повторить запуск.')
        finally:
            job['finished_at'] = datetime.now(timezone.utc).isoformat()
            with self.lock:
                write_json(folder / 'job.json', job)
                self.active = None


def handler_for(jobs):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def local_request(self):
            port = self.server.server_address[1]
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            require(self.headers.get('Host') in hosts, 'Откройте страницу через localhost.')
            origin = self.headers.get('Origin')
            require(origin is None or origin in {'http://' + h for h in hosts}, 'Недопустимый источник запроса.')

        def respond(self, status, body, mime='application/json; charset=utf-8'):
            import json
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            try:
                self.local_request()
            except ContractError as exc:
                self.respond(403, {'error': str(exc)})
                return
            try:
                if self.path in ('/', '/app.js', '/style.css'):
                    filename = 'index.html' if self.path == '/' else self.path[1:]
                    self.respond(200, (ROOT / 'web_ui' / filename).read_bytes(), mimetypes.guess_type(filename)[0] + '; charset=utf-8')
                elif self.path == '/api/status':
                    try:
                        model = Ollama(Settings.environment()).identity()
                        self.respond(200, {'ready': True, 'model': model['model'], 'active': jobs.active})
                    except ModelError:
                        self.respond(200, {'ready': False, 'model': Settings.environment().model, 'active': jobs.active})
                elif self.path == '/api/jobs':
                    self.respond(200, jobs.recent())
                elif match := re.fullmatch(r'/api/jobs/([0-9a-f]{32})', self.path):
                    job = jobs.get(match[1])
                    folder = jobs.directory / match[1]
                    job['input'] = read_json(folder / 'input.json')
                    if job['status'] == 'done':
                        job['result'] = loads((folder / 'run/predictions.jsonl').read_text().splitlines()[0])
                        job['rubric'] = read_json(folder / 'run/manifest.json')['rubric']
                    self.respond(200, job)
                else:
                    self.respond(404, {'error': 'Не найдено.'})
            except (OSError, ValueError, KeyError):
                self.respond(404, {'error': 'Запуск не найден или недоступен.'})

        def do_POST(self):
            try:
                self.local_request()
            except ContractError as exc:
                self.respond(403, {'error': str(exc)})
                return
            try:
                if self.path != '/api/jobs':
                    self.respond(404, {'error': 'Не найдено.'})
                    return
                require(self.headers.get('Content-Type', '').split(';')[0] == 'application/json', 'Ожидается JSON-запрос.')
                length = int(self.headers.get('Content-Length', '0'))
                maximum = 5 * 1024 * 1024 if self.headers.get('X-ML2-Knowledge') == '1' else 1024 * 1024
                if not 0 < length <= maximum:
                    self.respond(413, {'error': 'Размер запроса превышает лимит 1 МБ (5 МБ с базой знаний).'})
                    return
                self.connection.settimeout(10)
                payload = loads(self.rfile.read(length))
                dialog = parse_input(payload)
                knowledge = payload.get('knowledge')
                if knowledge is not None:
                    KnowledgeBase(knowledge)
                as_of = payload.get('knowledge_as_of') or None
                if as_of:
                    calendar_date.fromisoformat(as_of)
                require(as_of is None or knowledge is not None,
                        'Чтобы указать дату источников, сначала подключите базу знаний.')
                self.respond(202, jobs.start(dialog, knowledge, as_of))
            except BusyError as exc:
                self.respond(409, {'error': 'Уже идёт оценка. Дождитесь её завершения.', 'active': str(exc)})
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.respond(400, {'error': str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Local ML2 playground')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), BaseHTTPRequestHandler)
    server.RequestHandlerClass = handler_for(Jobs(ROOT / 'runs/web'))
    print(f'ML2: http://localhost:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
