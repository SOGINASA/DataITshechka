import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ml2.contracts import (ContractError, conversation, dataset, digest, loads, read_json,
                           rubric, validate_results)
from ml2.engine import Evaluator, EvaluationFailure
from ml2.knowledge import KnowledgeBase
from ml2.metrics import report, compare
from ml2.provider import Ollama, Settings, ModelError
from ml2.scoring import summarize

ROOT = Path(__file__).parents[1]


def checklist():
    return rubric(read_json(ROOT / 'configs/chat.json'))


def dialog():
    return conversation({'conversation_id': 'synthetic-test', 'channel': 'chat', 'language': 'ru',
        'messages': [{'id': 'm1', 'speaker': 'client', 'text': 'Здравствуйте. Где поддержка?'},
                     {'id': 'm2', 'speaker': 'operator', 'text': 'Здравствуйте! Меня зовут Ирина.'},
                     {'id': 'm3', 'speaker': 'operator', 'text': 'Могу помочь ещё? До свидания.'}]})


def answers(c=None):
    c = c or checklist()
    rows = []
    for criterion in c['criteria']:
        kind = criterion['answer_type']
        value = max(s['value'] for s in criterion['scale']) if kind == 'scale' else kind != 'flag'
        rows.append({'criterion_id': criterion['id'], 'status': 'scored' if kind == 'scale' else 'pass',
                     'value': value, 'explanation': 'Синтетический ответ для теста контракта.',
                     'evidence_message_ids': ['m2'],
                     'reviewed_range': {'start_message_id': 'm1', 'end_message_id': 'm3'},
                     'knowledge_status': 'not_needed', 'knowledge_refs': []})
    return {'results': rows}


def wire_answers(raw=None):
    raw = raw if raw is not None else answers()
    return {'results': {r['criterion_id']: {
        **{k: v for k, v in r.items() if k not in ('criterion_id', 'status', 'value')},
        'answer': 'N/A' if r['status'] == 'not_applicable' else
                  'needs_review' if r['status'] == 'needs_review' else r['value']}
        for r in raw['results']}}


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def complete(self, messages, schema):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        if isinstance(value.get('results'), list):
            value = wire_answers(value)
        return json.dumps(value), {'eval_count': 50}


class ContractTests(unittest.TestCase):
    def test_official_formula_and_independent_flag(self):
        c = checklist()
        a = answers()
        for item in a['results']:
            if item['criterion_id'] in ('needs', 'identification'):
                item.update(status='not_applicable', value=None)
            if item['criterion_id'] == 'consultation':
                item['value'] = 15
            if item['criterion_id'] == 'dialogue_management':
                item['value'] = 7
            if item['criterion_id'] == 'gross_errors':
                item.update(status='fail', value=True)
        result = summarize(validate_results(a, c, dialog(), []), c)
        self.assertEqual(result['final_score'], 85.38)
        self.assertEqual(result['coverage'], 100)
        self.assertIs(result['gross_error_detected'], True)
        a['results'][-1].update(status='pass', value=False)
        self.assertEqual(summarize(a['results'], c)['final_score'], 85.38)

    def test_half_up(self):
        c = rubric({'name': 'Test', 'version': '1', 'criteria': [{'id': 'x', 'title': 'x',
             'description': 'x', 'weight': 100, 'answer_type': 'scale', 'allow_na': False,
             'scale': [{'value': n, 'label': str(n)} for n in (0, 405, 800)]}]})
        self.assertEqual(summarize([{'criterion_id': 'x', 'status': 'scored', 'value': 405}], c)['final_score'], 50.63)

    def test_unknown_not_na_and_unknown_flag(self):
        c, a = checklist(), answers()['results']
        a[0].update(status='needs_review', value=None)
        result = summarize(a, c)
        self.assertIsNone(result['final_score'])
        self.assertEqual(result['coverage'], 90)
        a[0].update(status='pass', value=True)
        a[-1].update(status='needs_review', value=None)
        result = summarize(a, c)
        self.assertEqual(result['final_score'], 100)
        self.assertIsNone(result['gross_error_detected'])

    def test_zero_denominator(self):
        c, a = checklist(), answers()['results']
        for criterion, row in zip(c['criteria'], a):
            if criterion['weight']:
                row.update(status='not_applicable', value=None)
        self.assertIsNone(summarize(a, c)['final_score'])

    def test_reject_invalid_model_decisions(self):
        changes = [
            (0, {'status': 'not_applicable', 'value': None}),
            (0, {'value': 1}), (0, {'value': True, 'status': 'fail'}),
            (3, {'value': 12}), (3, {'value': True}),
            (0, {'evidence_message_ids': ['invented']}),
            (0, {'reviewed_range': {'start_message_id': 'm3', 'end_message_id': 'm1'}}),
            (0, {'evidence_message_ids': [], 'reviewed_range': None}),
            (0, {'value': False, 'status': 'fail', 'reviewed_range': None}),
            (-1, {'value': True, 'status': 'pass'}),
            (3, {'knowledge_status': 'missing'}),
            (3, {'knowledge_status': 'supported'}),
            (3, {'knowledge_refs': ['unknown']}),
            (0, {'criterion_id': 'needs'}),
        ]
        for index, change in changes:
            with self.subTest(change=change):
                a = answers()
                a['results'][index].update(change)
                with self.assertRaises(ContractError):
                    validate_results(a, checklist(), dialog(), [])

    def test_server_resolves_verbatim_quotes(self):
        d = dialog()
        d['messages'][1]['text'] = '  Исходная реплика <без изменений>  '
        r = validate_results(answers(), checklist(), d, [])
        self.assertEqual(r[0]['evidence'][0]['quote'], d['messages'][1]['text'])

    def test_new_criterion_no_fixed_id_dependency(self):
        c = checklist()
        c['criteria'][0].update(id='new_jury_rule', title='Новый критерий', description='Проверить новый сценарий')
        result = validate_results(answers(c), c, dialog(), [])
        self.assertEqual(result[0]['criterion_id'], 'new_jury_rule')
        self.assertEqual(summarize(result, c)['final_score'], 100)
        self.assertNotEqual(digest(c), digest(checklist()))

    def test_invalid_configuration(self):
        for change in ({'weight': 11}, {'allow_na': 'yes'}, {'answer_type': 'arbitrary'}):
            c = checklist()
            c['criteria'][0].update(change)
            with self.assertRaises(ContractError):
                rubric(c)

    def test_strict_json(self):
        for raw in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ContractError):
                loads(raw)

    def test_organizer_input_and_unchanged_text(self):
        raw = {'isSuccess': True, 'data': {'total_records': 1, 'records': [{
            'conversation_id': 'test-kk', 'channel': 'agent chat', 'language': 'KZ',
            'transcript': [{'speaker': 'client', 'text': '  Сәлем  ', 'timestamp': '00:01'}]}]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.json'
            path.write_text(json.dumps(raw))
            rows = dataset(path)
            self.assertEqual(rows[0]['language'], 'kk')
            self.assertEqual(rows[0]['messages'][0]['text'], '  Сәлем  ')
            self.assertNotIn('start_ms', rows[0]['messages'][0])
            raw['data']['total_records'] = 2
            path.write_text(json.dumps(raw))
            with self.assertRaises(ContractError):
                dataset(path)

    def test_voice_exception_does_not_change_chat(self):
        voice = rubric(read_json(ROOT / 'configs/voice.json'))
        self.assertTrue(voice['criteria'][0]['allow_na'])
        self.assertFalse(checklist()['criteria'][0]['allow_na'])


class EngineTests(unittest.TestCase):
    def test_single_repair_and_real_error_after_two_failures(self):
        provider = FakeProvider([{'results': []}, answers()])
        result = Evaluator(provider, checklist()).evaluate(dialog())
        self.assertEqual(provider.calls, 2)
        self.assertEqual(len(result['provenance']['attempts']), 2)
        provider = FakeProvider([{'results': []}, {'results': []}])
        with self.assertRaises(EvaluationFailure):
            Evaluator(provider, checklist()).evaluate(dialog())
        self.assertEqual(provider.calls, 2)

    def test_no_retry_on_transport_error(self):
        p = FakeProvider([ModelError('timeout')])
        with self.assertRaises(EvaluationFailure):
            Evaluator(p, checklist()).evaluate(dialog())
        self.assertEqual(p.calls, 1)

    def test_no_external_provider_or_silent_truncation(self):
        for url in ('https://example.com', 'http://127.0.0.1:3/?secret=x', 'http://user:pass@localhost'):
            with self.assertRaises(ModelError):
                Ollama(Settings(base_url=url))
        p = Ollama(Settings(context=4096, output_tokens=512))
        with self.assertRaises(ModelError):
            p.complete([{'role': 'user', 'content': 'x' * 10000}], {})
        with patch.object(p, '_request', return_value={'done': True, 'done_reason': 'length'}):
            with self.assertRaises(ModelError):
                p.complete([], {})

    def test_knowledge_validity_and_grounding(self):
        doc = {'id': 'support-1', 'title': 'Поддержка', 'source': 'synthetic test', 'version': '1',
               'text': 'Поддержка доступна в тестовом разделе.', 'valid_from': '2026-01-01', 'valid_until': '2026-12-31'}
        kb = KnowledgeBase({'version': 'test', 'documents': [doc]})
        self.assertFalse(kb.retrieve(dialog()))
        self.assertFalse(kb.retrieve(dialog(), '2027-01-01'))
        self.assertEqual(kb.retrieve(dialog(), '2026-11-07')[0]['id'], 'support-1')
        a = answers()
        a['results'][3].update(knowledge_status='supported', knowledge_refs=['support-1'])
        validate_results(a, checklist(), dialog(), [doc])
        with self.assertRaises(ContractError):
            validate_results(a, checklist(), dialog(), [])


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.c = checklist()
        self.pred = Evaluator(FakeProvider([answers()]), self.c).evaluate(dialog())
        self.gold = {'conversation_id': 'synthetic-test', 'conversation_hash': digest(dialog()),
                     'rubric_hash': digest(self.c), 'language': 'ru', 'channel': 'chat',
                     'label_source': 'synthetic_test', 'results': answers()['results']}

    def test_all_missing_kept_in_denominator(self):
        r = report([self.gold], [], self.c)
        self.assertEqual((r['decisions'], r['accuracy'], r['complete_fraction']), (8, 0, 0))
        self.assertIsNone(r['score_mae'])

    def test_comparison_same_denominators(self):
        b = copy.deepcopy(self.pred)
        b['results'][0].update(status='needs_review', value=None)
        r = compare([self.gold], [self.pred], [b], self.c)
        self.assertEqual(r['accuracy_delta_b_minus_a'], -1 / 8)
        self.assertEqual(r['b']['score_pairs'], 0)
        self.assertEqual(len(r['changed_correctness']), 1)
        self.assertEqual(r['a']['label_sources'], ['synthetic_test'])

    def test_unknown_flag_is_false_negative_not_removed(self):
        self.gold['results'][-1].update(status='fail', value=True)
        self.pred['results'][-1].update(status='needs_review', value=None)
        r = report([self.gold], [self.pred], self.c)
        self.assertEqual(r['by_criterion']['gross_errors']['recall'], 0)
        self.assertIsNone(r['by_criterion']['gross_errors']['precision'])

    def test_different_rubric_and_input_rejected(self):
        for key in ('rubric_hash', 'conversation_hash'):
            p = copy.deepcopy(self.pred)
            p['provenance'][key] = 'wrong'
            with self.assertRaises(ContractError):
                report([self.gold], [p], self.c)

    def test_invalid_step_and_bool_number_are_errors(self):
        self.pred['results'][0]['value'] = 1
        self.pred['results'][3]['value'] = 12
        r = report([self.gold], [self.pred], self.c)
        self.assertEqual(r['accuracy'], 6 / 8)
        self.assertEqual(r['score_pairs'], 0)


if __name__ == '__main__':
    unittest.main()
