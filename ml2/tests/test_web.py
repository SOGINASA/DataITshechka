import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from ml2.contracts import read_json, write_json
from ml2.web import Jobs, BusyError, handler_for, parse_input


class WebTests(unittest.TestCase):
    def test_text_roles_multiline_and_json_ids(self):
        d = parse_input({'format': 'text', 'source': 'Клиент: Привет\nОператор: Здравствуйте\nВторая строка\nБот: Событие'})
        self.assertEqual([m['speaker'] for m in d['messages']], ['client', 'operator', 'bot'])
        self.assertEqual(d['messages'][1]['text'], 'Здравствуйте\nВторая строка')
        raw = {'external_id': 'keep-this-id', 'channel': 'agent chat', 'language': 'KZ', 'transcript': [{'speaker': 'operator', 'text': 'Сәлем'}]}
        result = parse_input({'format': 'json', 'source': json.dumps(raw)})
        self.assertEqual((result['conversation_id'], result['language']), ('keep-this-id', 'kk'))
        for source in ('нет роли', 'Клиент: Только клиент', 'Оператор:'):
            with self.assertRaises(ValueError): parse_input({'format': 'text', 'source': source})

    def test_acceptance_is_persisted_busy_and_restart_recovery(self):
        entered, release = threading.Event(), threading.Event()
        def runner(args):
            entered.set(); release.wait(3); return 2
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs(tmp, runner)
            job = jobs.start(parse_input({'format': 'text', 'source': 'Оператор: Тест'}))
            try:
                self.assertTrue((Path(tmp) / job['id'] / 'input.json').exists())
                self.assertTrue(entered.wait(1))
                with self.assertRaises(BusyError): jobs.start({'unused': True})
            finally: release.set()
            for _ in range(100):
                if jobs.active is None: break
                time.sleep(.01)
            self.assertEqual(jobs.get(job['id'])['status'], 'error')
            unfinished = jobs.get(job['id']); unfinished['status'] = 'running'
            write_json(Path(tmp) / job['id'] / 'job.json', unfinished)
            restarted = Jobs(tmp, runner)
            self.assertEqual(restarted.get(job['id'])['status'], 'error')
            self.assertIsNone(restarted.active)

    def test_http_origin_validation_static_allowlist_and_input_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Jobs(tmp)))
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            port = server.server_address[1]
            def request(method, path, data=None, headers=None):
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                try:
                    c.request(method, path, body=data, headers=headers or {})
                    r = c.getresponse(); return r.status, r.read(), dict(r.getheaders())
                finally: c.close()
            try:
                status, body, headers = request('GET', '/')
                self.assertEqual(status, 200)
                self.assertIn(b'/app.js', body)
                self.assertIn('Content-Security-Policy', headers)
                self.assertEqual(request('GET', '/../../case/api.txt')[0], 404)
                self.assertEqual(request('GET', '/', headers={'Host': 'evil.example'})[0], 403)
                self.assertEqual(request('POST', '/api/jobs', '{}', {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})[0], 403)
                self.assertEqual(request('POST', '/api/jobs', '{}', {'Content-Type': 'text/plain'})[0], 400)
                self.assertEqual(request('POST', '/api/jobs', '{}', {'Content-Type': 'application/json'})[0], 400)
                self.assertEqual(request('POST', '/api/jobs', '', {'Content-Type': 'application/json', 'Content-Length': '2000000'})[0], 413)
            finally: server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': unittest.main()
