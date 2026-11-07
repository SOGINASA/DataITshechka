from copy import deepcopy
from pathlib import Path

import pytest

from ml.dataset import load_release, adapt_input, adapt_rubric
from services.assessment_logic import reconcile, refinement_criteria


def published_example():
    path = Path(__file__).resolve().parents[2] / 'annotation/checklist.official.json'
    import json
    k = adapt_rubric(json.loads(path.read_text(encoding='utf-8')))
    criteria = [c for c in k.criteria if c['id'] == 'needs']
    messages = [{'id': 'c1', 'speaker': 'client', 'text': 'Где посмотреть условия услуги?'},
                {'id': 'o1', 'speaker': 'operator', 'text': 'Откройте раздел условий.'}]
    rows = [{'criterion_id': 'needs', 'status': 'pass', 'value': True, 'explanation': 'Wrong encoding',
             'evidence_message_ids': ['o1']}]
    return criteria, messages, rows


def test_sufficient_information_binds_official_na_rule_and_audits_change():
    criteria, messages, rows = published_example()
    updated, adjustments = reconcile(criteria, rows, {'initial_information': 'sufficient', 'context_message_ids': ['c1', 'o1']}, messages)
    assert updated[0]['status'] == 'not_applicable' and updated[0]['value'] is None
    assert updated[0]['evidence_message_ids'] == ['c1']
    assert rows[0]['status'] == 'pass'  # raw model decision retained, no mutation
    assert adjustments[0]['before'] == {'status': 'pass', 'value': True}


def test_customized_definition_disables_specialized_binding():
    criteria, messages, rows = published_example()
    criteria[0]['na_condition'] = 'Only if there are no client messages.'
    updated, adjustments = reconcile(criteria, rows, {'initial_information': 'sufficient', 'context_message_ids': ['c1']}, messages)
    assert updated == rows and adjustments == []
    assert refinement_criteria(criteria) == []


def test_missing_details_do_not_automatically_prove_success():
    criteria, messages, rows = published_example()
    updated, adjustments = reconcile(criteria, rows, {'initial_information': 'missing', 'context_message_ids': ['c1']}, messages)
    assert updated == rows and adjustments == []


@pytest.mark.parametrize('state,context', [('unclear', ['c1']), ('sufficient', ['o1'])])
def test_unknown_initial_context_cannot_become_na_or_success(state, context):
    criteria, messages, rows = published_example()
    updated, _ = reconcile(criteria, rows, {'initial_information': state, 'context_message_ids': context}, messages)
    assert updated[0]['status'] == 'needs_review' and updated[0]['value'] is None


def test_ivr_selection_is_not_proof_of_a_known_business_request():
    criteria, messages, rows = published_example()
    messages[0]['text'] = '2'
    updated, _ = reconcile(criteria, rows, {'initial_information': 'sufficient', 'context_message_ids': ['c1']}, messages)
    assert updated[0]['status'] == 'needs_review'
