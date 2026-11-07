import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ml2.cli import initialize_run, export_csv, main
from ml2.contracts import canonical, digest, write_json, read_json
from ml2.provider import grammar_schema, Ollama, Settings, ModelError


class RunTests(unittest.TestCase):
    def test_thinking_setting_is_explicit_and_sent_to_transport(self):
        self.assertTrue(Settings.parse_think('true'))
        self.assertFalse(Settings.parse_think('false'))
        with self.assertRaises(ModelError):
            Settings.parse_think('maybe')
        provider = Ollama(Settings(think=True))
        with patch.object(provider, '_request', return_value={'done': True, 'message': {'content': '{}'}}) as request:
            provider.complete([], {})
        self.assertIs(request.call_args.args[1]['think'], True)

    def test_wire_decoding_preserves_decisions_and_flag_polarity(self):
        from ml2.decoding import decode, schema_for
        from ml2.contracts import rubric, validate_results
        from test_ml2 import answers, wire_answers, dialog
        checklist = rubric(read_json('ml2/configs/chat.json'))
        raw = answers()
        raw['results'][1].update(status='not_applicable', value=None)
        raw['results'][3].update(status='needs_review', value=None)
        raw['results'][-1].update(status='fail', value=True)
        decoded = decode(wire_answers(raw), checklist)
        self.assertEqual(decoded, raw)
        validate_results(decoded, checklist, dialog(), [])
        schema = schema_for(checklist, dialog(), [])
        self.assertEqual(set(schema['properties']['results']['required']), {c['id'] for c in checklist['criteria']})
        self.assertEqual(schema['$defs']['assessment']['properties']['reviewed_range']['properties']['start_message_id']['enum'], ['m1', 'm2', 'm3'])

    def test_wire_decoding_never_repairs_an_illegal_grade(self):
        from ml2.decoding import decode
        from ml2.contracts import rubric, validate_results
        from test_ml2 import wire_answers, dialog
        checklist = rubric(read_json('ml2/configs/chat.json'))
        for criterion, answer in [('contact', 1), ('consultation', 7), ('contact', 'N/A')]:
            raw = wire_answers()
            raw['results'][criterion]['answer'] = answer
            with self.assertRaises(ValueError):
                validate_results(decode(raw, checklist), checklist, dialog(), [])
        raw = wire_answers()
        raw['results'].pop('contact')
        with self.assertRaises(ValueError):
            decode(raw, checklist)

    def test_resume_requires_same_inputs_and_preserves_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            manifest = {'created_at': 'first', 'conversation_ids': ['one', 'two'], 'code_hash': 'c', 'rubric_hash': 'r'}
            initialize_run(out, manifest, False)
            previous = {'conversation_id': 'one', 'status': 'error', 'provenance': {'run_manifest_hash': digest(manifest)}}
            (out / 'predictions.jsonl').write_text(canonical(previous) + '\n')
            saved, rows = initialize_run(out, {**manifest, 'created_at': 'later'}, True)
            self.assertEqual(saved, manifest)
            self.assertEqual(rows, [previous])
            with self.assertRaises(ValueError):
                initialize_run(out, {**manifest, 'code_hash': 'different'}, True)
            with self.assertRaises(FileExistsError):
                initialize_run(out, manifest, False)
            (out / 'predictions.jsonl').write_text('{broken')
            with self.assertRaises(ValueError):
                initialize_run(out, manifest, True)

    def test_csv_keeps_error_and_neutralizes_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.csv'
            export_csv([{'conversation_id': '=FORMULA()', 'status': 'error', 'error': 'timeout'},
                        {'conversation_id': 'two', 'status': 'ok', 'results': [
                            {'criterion_id': 'x', 'status': 'pass', 'value': True, 'explanation': 'Обоснование'}]}], path)
            with path.open(encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['conversation_id'], "'=FORMULA()")
            self.assertEqual(rows[0]['error'], 'timeout')
            self.assertEqual(rows[1]['explanation'], 'Обоснование')

    def test_wire_grammar_keeps_types_and_leaves_validator_schema_unchanged(self):
        schema = {'type': 'array', 'minItems': 8, 'maxItems': 8,
                  'items': {'type': 'string', 'minLength': 1, 'maxLength': 2000, 'enum': ['a', 'b']}}
        wire = grammar_schema(schema)
        self.assertNotIn('minItems', wire)
        self.assertEqual(wire['items']['enum'], ['a', 'b'])
        self.assertEqual(schema['minItems'], 8)

    def test_empty_knowledge_cannot_claim_a_source_and_repair_fits(self):
        from ml2.engine import Evaluator
        from test_ml2 import wire_answers, dialog
        provider = Ollama(Settings())
        captured = []
        def complete(messages, schema):
            captured.append((list(messages), schema))
            if len(captured) == 1:
                return '{"results":[]}', {}
            return json.dumps(wire_answers()), {}
        with patch.object(provider, 'complete', side_effect=complete):
            Evaluator(provider, read_json('ml2/configs/chat.json')).evaluate(dialog())
        fields = captured[0][1]['$defs']['assessment']['properties']
        self.assertEqual(fields['knowledge_status']['enum'], ['not_needed', 'missing'])
        self.assertEqual(fields['reviewed_range']['type'], 'object')
        self.assertEqual(len(captured), 2)
        for messages, schema in captured:
            with patch.object(provider, '_request', return_value={
                'done': True, 'message': {'content': '{}'}}) as request:
                provider.complete(messages, schema)
                request.assert_called_once()

    def test_cli_real_pipeline_with_fake_transport_not_fake_metrics(self):
        # Only the transport is stubbed; CLI, validation, hashing, persistence and export are real.
        from test_ml2 import wire_answers
        identity = {'model': 'test-only', 'digest': 'test-only'}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            path = Path(tmp) / 'dialogue.json'
            from test_ml2 import dialog
            write_json(path, dialog())
            with patch.object(Ollama, 'identity', return_value=identity), patch.object(Ollama, 'complete', return_value=(json.dumps(wire_answers()), {})):
                self.assertEqual(main(['run', '--input', str(path), '--output', str(out), '--purpose', 'synthetic_smoke']), 0)
            self.assertEqual(read_json(out / 'run_summary.json')['quality_measured'], False)
            with patch.object(Ollama, 'identity', return_value=identity), patch.object(Ollama, 'complete') as call:
                self.assertEqual(main(['run', '--input', str(path), '--output', str(out), '--purpose', 'synthetic_smoke', '--resume']), 0)
                call.assert_not_called()
            with patch.object(Ollama, 'identity', return_value=identity), patch.object(Ollama, 'complete', side_effect=ModelError('offline')):
                self.assertEqual(main(['run', '--input', str(path), '--output', str(Path(tmp) / 'failure')]), 1)
            self.assertEqual(read_json(Path(tmp) / 'failure/run_summary.json')['failed'], 1)


if __name__ == '__main__':
    unittest.main()
