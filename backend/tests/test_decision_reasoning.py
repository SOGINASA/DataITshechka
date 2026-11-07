from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest
from jsonschema import validate

from services import decision_reasoning as logic, ollama
from services.validation import checklist


def example():
    c = SimpleNamespace(channel='chat', language='ru', messages=[
        {'id': 'c1', 'speaker': 'client', 'text': 'Как узнать условия публичной услуги?', 'start_ms': None, 'end_ms': None},
        {'id': 'o1', 'speaker': 'operator', 'text': 'Откройте раздел условий на сайте.', 'start_ms': None, 'end_ms': None},
        {'id': 'c2', 'speaker': 'client', 'text': 'Спасибо.', 'start_ms': None, 'end_ms': None}])
    k = SimpleNamespace(**checklist({'name': 'Changed rubric', 'version': '2', 'criteria': [
        {'id': 'custom_discovery', 'title': 'Discovery', 'answer_type': 'binary', 'allow_na': True,
         'na_condition': 'Information sufficient before operator joined.'},
        {'id': 'custom_consultation', 'title': 'Consultation', 'answer_type': 'scale',
         'scale': [{'value': 0, 'label': 'None'}, {'value': 7, 'label': 'Answered or next step'}]}]}))
    document = {'request_analysis': {'requests': [{'description': 'Как найти условия', 'client_message_ids': ['c1'],
        'operator_answer_ids': ['o1'], 'outcome': 'next_step', 'fact_support': 'transcript_sufficient'}],
        'initial_information': 'sufficient', 'missing_customer_details': [], 'context_message_ids': ['c1'],
        'operator_clarification_ids': []}, 'results': {}}
    for cid, answer in [('custom_discovery', 'not_applicable'), ('custom_consultation', 'score_7')]:
        document['results'][cid] = {'applicability_check': 'Проверено условие чек-листа.', 'explanation': 'Есть следующий шаг.',
            'answer': answer, 'evidence_message_ids': ['o1'], 'reviewed_range': {'start_message_id': 'c1', 'end_message_id': 'c2'}}
    return c, k, document


def test_configurable_rubric_and_valid_next_step_preserve_facts():
    c, k, doc = example()
    validate(doc, logic.schema(k.criteria, c.messages))
    rows, facts = logic.decode(doc, k.criteria, c.messages)
    assert [(r['status'], r['value']) for r in rows] == [('not_applicable', None), ('scored', 7)]
    assert facts['request_analysis']['requests'][0]['outcome'] == 'next_step'
    assert 'applicability_check' not in rows[0]
    assert set(facts['applicability_checks']) == {'custom_discovery', 'custom_consultation'}


@pytest.mark.parametrize('field,ids', [('client_message_ids', ['o1']), ('operator_answer_ids', ['c2']),
                                     ('operator_answer_ids', ['invented']), ('operator_answer_ids', []),
                                     ('operator_answer_ids', ['o1', 'o1'])])
def test_bad_request_response_evidence_cannot_be_accepted(field, ids):
    c, k, doc = example()
    doc['request_analysis']['requests'][0][field] = ids
    with pytest.raises(ValueError):
        logic.decode(doc, k.criteria, c.messages)


@pytest.mark.parametrize('state,details', [('sufficient', ['A detail']), ('missing', [])])
def test_contradictory_initial_information_is_flagged_without_losing_valid_consultation(state, details):
    c, k, doc = example()
    doc['request_analysis'].update(initial_information=state, missing_customer_details=details)
    rows, facts = logic.decode(doc, k.criteria, c.messages)
    assert facts['request_analysis']['initial_information'] == 'unclear'
    assert facts['analysis_warnings'][0]['code'] == 'contradictory_initial_information'
    assert next(r for r in rows if r['criterion_id'] == 'custom_consultation')['value'] == 7


def test_unanswered_cannot_point_at_a_relevant_answer():
    c, k, doc = example()
    doc['request_analysis']['requests'][0]['outcome'] = 'unanswered'
    with pytest.raises(ValueError, match='Unanswered'):
        logic.decode(doc, k.criteria, c.messages)


def test_response_cannot_precede_request():
    c, k, doc = example()
    c.messages = [c.messages[1], c.messages[0], c.messages[2]]
    with pytest.raises(ValueError, match='precedes'):
        logic.decode(doc, k.criteria, c.messages)


def test_real_adapter_validates_inventory_and_records_final_facts(monkeypatch):
    c, k, doc = example()
    class Opener:
        def open(self, req, timeout):
            return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps(doc), 'thinking': 'SECRET_REASONING'}}).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    config = {'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_MODEL': 'test'}
    capture = {}
    results, _, metadata = ollama.assess(c, k, config, wire_format='decision-reasoned', response_capture=capture)
    assert results[0]['status'] == 'not_applicable'
    assert metadata['wire_version'] == logic.VERSION
    assert metadata['assessment_facts']['request_analysis']['initial_information'] == 'sufficient'
    assert 'SECRET_REASONING' not in json.dumps(capture)
    doc['request_analysis']['operator_clarification_ids'] = ['c2']
    with pytest.raises(ollama.AssessmentError, match='speaker role'):
        ollama.assess(c, k, config, wire_format='decision-reasoned')


def test_initial_context_cannot_leak_later_client_information():
    c, k, doc = example()
    doc['request_analysis']['context_message_ids'] = ['c2']
    with pytest.raises(ValueError, match='later conversation turn'):
        logic.decode(doc, k.criteria, c.messages)


def test_prompt_receives_exact_preoperator_context(monkeypatch):
    c, k, doc = example()
    bodies = []
    class Opener:
        def open(self, req, timeout):
            bodies.append(json.loads(req.data))
            return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps(doc)}}).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    ollama.assess(c, k, {'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_MODEL': 'test'}, wire_format='decision-reasoned')
    task = json.loads(bodies[0]['messages'][1]['content'])
    assert task['initial_context'] == [c.messages[0]]
    assert task['messages'] == c.messages
