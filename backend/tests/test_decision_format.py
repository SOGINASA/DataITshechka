from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest
from jsonschema import validate, ValidationError

from services import decision_format as wire, ollama
from services.validation import checklist


def fixture():
    c = SimpleNamespace(channel='chat', language='ru', messages=[
        {'id': 't0001', 'speaker': 'operator', 'text': 'Здравствуйте', 'start_ms': None, 'end_ms': None}])
    k = SimpleNamespace(**checklist({'name': 'Configurable', 'version': '1', 'criteria': [
        {'id': 'custom_binary', 'title': 'Binary', 'answer_type': 'binary', 'allow_na': True, 'na_condition': 'No request'},
        {'id': 'custom_flag', 'title': 'Flag', 'answer_type': 'flag', 'weight': 0},
        {'id': 'custom_scale', 'title': 'Scale', 'answer_type': 'scale',
         'scale': [{'value': 0, 'label': 'No'}, {'value': 7, 'label': 'Yes'}]}]}))
    return c, k


def document():
    return {'results': {key: {'answer': value, 'explanation': 'Evidence', 'evidence_message_ids': ['t0001'],
                              'reviewed_range': {'start_message_id': 't0001', 'end_message_id': 't0001'}}
                       for key, value in [('custom_binary', 'not_applicable'), ('custom_flag', 'yes'),
                                          ('custom_scale', 'score_7')]}}


def test_configurable_schema_and_polarity():
    c, k = fixture()
    raw = document()
    validate(raw, wire.schema(k.criteria, c.messages))
    rows = wire.decode(raw, k.criteria)
    assert [(r['status'], r['value']) for r in rows] == [('not_applicable', None), ('fail', True), ('scored', 7)]
    assert 'status not_applicable and value null' not in wire.system_prompt(ollama.SYSTEM)
    assert 'never emit status or value' in wire.system_prompt(ollama.SYSTEM)


@pytest.mark.parametrize('key,value', [('custom_binary', True), ('custom_flag', 'not_applicable'),
                                      ('custom_scale', 'score_10'), ('custom_scale', 'yes')])
def test_illegal_answers_rejected_by_schema_and_decoder(key, value):
    c, k = fixture()
    raw = document()
    raw['results'][key]['answer'] = value
    with pytest.raises(ValidationError):
        validate(raw, wire.schema(k.criteria, c.messages))
    with pytest.raises(ValueError):
        wire.decode(raw, k.criteria)


def test_live_adapter_keeps_evidence_validation(monkeypatch):
    c, k = fixture()
    raw = document()
    bodies = []
    class Opener:
        def open(self, req, timeout):
            bodies.append(json.loads(req.data))
            return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps(raw)}}).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    config = {'OLLAMA_MODEL': 'test', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_THINK': False}
    results, _, metadata = ollama.assess(c, k, config, wire_format='decision')
    assert results[1]['status'] == 'fail' and results[1]['value'] is True
    assert metadata['wire_version'] == wire.VERSION
    assert bodies[0]['think'] is False
    raw['results']['custom_binary']['evidence_message_ids'] = ['invented']
    with pytest.raises(ollama.AssessmentError):
        ollama.assess(c, k, config, wire_format='decision')


def test_guidance_is_explicit_and_preserves_the_single_decision_schema(monkeypatch):
    from services.decision_guidance import GUIDANCE, VERSION
    c, k = fixture()
    bodies = []
    class Opener:
        def open(self, req, timeout):
            bodies.append(json.loads(req.data))
            return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps(document())}}).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    config = {'OLLAMA_MODEL': 'test', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434'}
    _, _, metadata = ollama.assess(c, k, config, wire_format='decision-guided')
    assert bodies[0]['format'] == wire.schema(k.criteria, c.messages)
    assert bodies[0]['messages'][0]['content'] == wire.system_prompt(ollama.SYSTEM) + GUIDANCE
    assert metadata['wire_version'] == VERSION


def test_full_release_fits_candidate_context_without_truncation():
    from pathlib import Path
    from ml.dataset import load_release, adapt_input, adapt_rubric
    from services.decision_guidance import GUIDANCE
    root = Path(__file__).resolve().parents[2] / 'data/releases/dev-reviewed-v1'
    if not (root / 'manifest.json').exists():
        pytest.skip('Private release unavailable')
    rows, _, rubrics, _ = load_release(root)
    for row in rows:
        c, k = adapt_input(row), adapt_rubric(rubrics[row['checklist_hash']])
        content = json.dumps({'rubric_description': k.description, 'criteria': k.criteria,
                             'language': c.language, 'channel': c.channel, 'messages': c.messages}, ensure_ascii=False)
        limit = 45056 if c.channel == 'call' else 28672
        assert len((wire.system_prompt(ollama.SYSTEM) + GUIDANCE + content).encode('utf-8')) <= limit - 4096 - 1024
