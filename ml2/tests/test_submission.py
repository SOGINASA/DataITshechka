import contextlib
import copy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from ml2.cli import main
from ml2.contracts import read_json, rubric, write_json
from ml2.provider import Ollama, Settings, ModelError
from ml2.submission import convert, build_submission, validate_submission
from test_ml2 import answers, wire_answers, dialog, checklist


class SubmissionTests(unittest.TestCase):
    def test_official_codes_raw_scale_and_na_formula(self):
        raw = answers()['results']
        raw[1].update(status='not_applicable', value=None)
        raw[2].update(status='not_applicable', value=None)
        raw[3]['value'] = 15
        raw[5]['value'] = 7
        raw[-1].update(status='fail', value=True)
        d = dialog()
        d['messages'].insert(0, {'id': 'bot', 'speaker': 'bot', 'text': 'Служебный контекст'})
        p = convert({'status': 'ok', 'results': raw}, d, checklist(), [])
        self.assertEqual(p['score'], {'final_score': 85.38, 'critical_flag': True})
        criteria = {c['criterion_id']: c for c in p['criteria']}
        self.assertEqual(set(criteria), {'contact', 'discovery', 'identification', 'consultation', 'empathy', 'dialogue', 'closure', 'critical'})
        self.assertEqual(criteria['dialogue']['value'], 7)
        self.assertEqual(criteria['contact']['evidence_turns'], [2, 3, 4])

    def test_unknown_and_contact_na_are_errors_never_false_or_na(self):
        raw = answers()['results']
        raw[3].update(status='needs_review', value=None)
        out = convert({'status': 'ok', 'results': raw}, dialog(), checklist(), [])
        self.assertEqual((out['status'], out['criteria'], out['score']), ('error', [], None))
        voice = rubric(read_json('ml2/configs/voice.json'))
        raw = answers(voice)['results']
        raw[0].update(status='not_applicable', value=None)
        d = {**dialog(), 'channel': 'call', 'start_truncated': True}
        out = convert({'status': 'ok', 'results': raw}, d, voice, [])
        self.assertEqual(out['status'], 'error')
        self.assertIn('contact=N/A', out['error'])

    def test_real_run_export_and_public_validation(self):
        identity = {'provider': 'ollama', 'model': 'synthetic-test-model', 'digest': 'test-only'}
        ds = [{**dialog(), 'conversation_id': f'test-{i}'} for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            source, run = Path(tmp) / 'input.json', Path(tmp) / 'run'
            write_json(source, ds)
            with patch.object(Ollama, 'identity', return_value=identity), patch.object(Ollama, 'complete', return_value=(json.dumps(wire_answers()), {})), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['run', '--input', str(source), '--output', str(run), '--limit', '1', '--purpose', 'synthetic_smoke']), 0)
            payload = build_submission(ds, [run], 'prod', 'TEST ONLY')
            self.assertEqual(len(payload['results']), 10)
            self.assertEqual(sum(r['status'] == 'error' for r in payload['results']), 9)
            validate_submission(payload, ds, 'prod')
            for mutation in ('score', 'id', 'boolean', 'turn'):
                bad = copy.deepcopy(payload)
                row = bad['results'][0]
                if mutation == 'score': row['score']['final_score'] = 42
                if mutation == 'id': row['conversation_id'] = 'wrong'
                if mutation == 'boolean': row['criteria'][0]['value'] = 1
                if mutation == 'turn': row['criteria'][0]['evidence_turns'] = [0]
                with self.assertRaises(ValueError): validate_submission(bad, ds, 'prod')
            # DEV requires the original 60 + 5 composition; missing predictions remain visible.
            dev = ds + [{**dialog(), 'conversation_id': f'test-{i}', 'channel': 'call' if i >= 60 else 'chat'} for i in range(10, 65)]
            self.assertEqual(len(build_submission(dev, [run], 'dev', 'TEST ONLY')['results']), 65)
            with self.assertRaises(ValueError): build_submission(ds, [run], 'dev', 'TEST ONLY')
            with self.assertRaises(ValueError): build_submission(ds, [run, run], 'prod', 'TEST ONLY')
            bad_input = copy.deepcopy(ds)
            bad_input[0]['messages'][0]['text'] = 'Changed source'
            with self.assertRaises(ValueError): build_submission(bad_input, [run], 'prod', 'TEST ONLY')
            (run / 'predictions.jsonl').write_text('{}\n')
            with self.assertRaises(ValueError): build_submission(ds, [run], 'prod', 'TEST ONLY')

    def test_expired_deadline_saves_all_ids_without_inference(self):
        identity = {'provider': 'ollama', 'model': 'synthetic-test-model', 'digest': 'test-only'}
        start = datetime(2026, 11, 7, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            source, run = Path(tmp) / 'input.json', Path(tmp) / 'run'
            write_json(source, [{**dialog(), 'conversation_id': f'test-{i}'} for i in range(10)])
            with patch.object(Ollama, 'identity', return_value=identity), patch.object(Ollama, 'complete') as complete, patch('ml2.cli.datetime') as clock, contextlib.redirect_stdout(io.StringIO()):
                clock.now.side_effect = [start, start + timedelta(seconds=2)]
                clock.fromisoformat.side_effect = datetime.fromisoformat
                code = main(['run', '--input', str(source), '--output', str(run), '--purpose', 'synthetic_smoke', '--deadline-seconds', '1'])
                self.assertEqual(code, 1)
                complete.assert_not_called()
            self.assertEqual(read_json(run / 'run_summary.json')['failed'], 10)
            provider = Ollama(Settings())
            provider.deadline = time.monotonic() - 1
            with patch.object(provider.opener, 'open') as request:
                with self.assertRaises(ModelError): provider.complete([], {})
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
