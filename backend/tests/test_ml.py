"""Contract and evaluation failure accounting, without downloading a model."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ml.dataset import adapt_input, adapt_rubric, adapt_reference, load_release
from ml.metrics import measure
from ml.run import choose
from services.evaluation import summarize


def fixture_data():
    rubric = {'name': 'Test rubric', 'version': '1', 'criteria': [
        {'id': 'critical_errors', 'name': 'Violation flag', 'type': 'binary', 'weight': 0,
         'is_critical': True, 'na_allowed': False, 'na_rule': '', 'description': 'Yes = violation.'},
        {'id': 'consultation', 'name': 'Consultation', 'type': 'ordinal', 'weight': 100,
         'allowed_scores': [0, 5, 20], 'na_allowed': True, 'na_rule': 'No request.', 'description': 'Scoring anchors.'}]}
    source = {'conversation_id': 'test', 'language': 'RU', 'channel': 'voice call',
              'transcript': [{'turn_id': 't0001', 'speaker': 'operator', 'text': 'Evidence',
                              'timestamp': '2026-11-07T10:00:00Z'}]}
    reference = {'labels': [
        {'criterion_id': 'critical_errors', 'verdict': 'pass', 'score': None, 'reason': 'Violation',
         'evidence_turn_ids': ['t0001']},
        {'criterion_id': 'consultation', 'verdict': 'score', 'score': 5, 'reason': 'Partial answer',
         'checked_span': {'start_turn_id': 't0001', 'end_turn_id': 't0001'}}],
        'score_summary': {'total': 25.0}}
    return source, rubric, reference


def test_legacy_violation_polarity_score_and_stable_evidence():
    source, rubric, reference = fixture_data()
    c, k = adapt_input(source), adapt_rubric(rubric)
    results = adapt_reference(reference, c, k)
    assert results[0]['criterion_id'] == 'gross_errors'
    assert results[0]['value'] is True and results[0]['status'] == 'fail'
    assert summarize(results)['gross_error_detected'] is True
    assert summarize(results)['final_score'] == 25
    assert results[0]['evidence'][0]['message_id'] == 't0001'
    assert c.messages[0]['start_ms'] is None  # no invented audio alignment
    reference['labels'][0]['verdict'] = 'fail'
    results = adapt_reference(reference, c, k)
    assert results[0]['value'] is False and results[0]['status'] == 'pass'


def test_input_conversion_does_not_leak_gold_or_audio():
    source, rubric, _ = fixture_data()
    source.update(audio_url='secret', labels=[{'reason': 'gold'}], assessment_context={'excluded_turn_spans': ['gold']})
    prompt = json.dumps(vars(adapt_input(source)))
    assert 'secret' not in prompt and 'gold' not in prompt and 'excluded_turn_spans' not in prompt
    rubric['criteria'][1]['id'] = 'new_criterion'
    assert adapt_rubric(rubric).criteria[1]['id'] == 'new_criterion'


def test_error_and_abstention_stay_in_denominator():
    source, rubric, reference = fixture_data()
    results = adapt_reference(reference, adapt_input(source), adapt_rubric(rubric))
    gold = {'test': {'results': results, 'summary': summarize(results), 'audio_reviewed': True}}
    report = measure([source], gold, {'test': {'state': 'error', 'elapsed_seconds': 2}})
    assert report['breakdown']['all'] == {'expected': 2, 'correct': 0, 'abstained_or_missing': 2, 'accuracy': 0}
    assert report['errors'] == 1 and report['score_mae'] is None
    assert report['violation_metrics']['gross_errors']['recall'] == 0
    assert report['violation_metrics']['gross_errors']['precision'] is None
    predicted = deepcopy(results)
    predicted[1].update(status='needs_review', value=None)
    report = measure([source], gold, {'test': {'state': 'ok', 'results': predicted, 'summary': summarize(predicted)}})
    assert report['breakdown']['all']['accuracy'] == 0.5
    assert report['score_comparable_dialogues'] == 0


def test_release_tampering_is_rejected(tmp_path):
    (tmp_path / 'inputs.jsonl').write_text('changed', encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps({'files_sha256': {'inputs.jsonl': 'incorrect'}}), encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        load_release(tmp_path)


def test_control_sample_balanced_without_gold():
    rows = [{'conversation_id': f'{lang}{i}', 'language': lang, 'channel': 'agent chat'}
            for lang in ['EN', 'KZ', 'RU'] for i in range(4)]
    selected = choose(rows, 3, None)
    assert {r['language'] for r in selected} == {'RU', 'KZ', 'EN'}
    with pytest.raises(ValueError):
        choose(rows, None, 'missing')


def test_optional_thinking_flag_sent_to_local_model(monkeypatch):
    from services import ollama
    source, rubric, reference = fixture_data()
    c, k = adapt_input(source), adapt_rubric(rubric)
    gold = adapt_reference(reference, c, k)
    output = [{'criterion_id': r['criterion_id'], 'status': r['status'], 'value': r['value'],
               'explanation': 'Supported', 'evidence_message_ids': ['t0001'], 'reviewed_range': None} for r in gold]
    import io
    captured = []
    class Opener:
        def open(self, req, timeout):
            captured.append(json.loads(req.data))
            keyed = {r['criterion_id']: {k: v for k, v in r.items() if k != 'criterion_id'} for r in output}
            return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps({'results': keyed}),
                                                                 'thinking': 'Must not be captured'}}).encode())
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    capture = {}
    _, _, metadata = ollama.assess(c, k, {'OLLAMA_MODEL': 'test', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434',
                                       'OLLAMA_THINK': False, 'OLLAMA_NUM_CTX_CALL': 40960,
                                       'OLLAMA_NUM_PREDICT_CALL': 3072}, response_capture=capture)
    assert captured[0]['think'] is False and metadata['think'] is False
    assert 'Must not be captured' not in json.dumps(capture)
    assert capture['request_attempted'] is True
    assert captured[0]['options']['num_ctx'] == metadata['num_ctx'] == 40960
    assert captured[0]['options']['num_predict'] == metadata['num_predict'] == 3072


def test_schema_prevents_numeric_pass_and_inverted_flag():
    from jsonschema import validate, ValidationError
    from services.ollama import response_schema
    source, rubric, reference = fixture_data()
    c, k = adapt_input(source), adapt_rubric(rubric)
    results = adapt_reference(reference, c, k)
    document = {'results': {r['criterion_id']: {
        'status': r['status'], 'value': r['value'], 'explanation': 'Supported', 'evidence_message_ids': ['t0001'],
        'reviewed_range': {'start_message_id': 't0001', 'end_message_id': 't0001'}} for r in results}}
    schema = response_schema(k.criteria, c.messages)
    validate(document, schema)
    invalid = deepcopy(document)
    invalid['results']['consultation']['status'] = 'pass'
    with pytest.raises(ValidationError):
        validate(invalid, schema)
    invalid = deepcopy(document)
    invalid['results']['gross_errors']['status'] = 'pass'
    with pytest.raises(ValidationError):
        validate(invalid, schema)
    invalid = deepcopy(document)
    invalid['results']['gross_errors']['reviewed_range'] = None
    with pytest.raises(ValidationError):
        validate(invalid, schema)


def test_ollama_http_error_without_body_is_safe(monkeypatch):
    from urllib.error import HTTPError
    from services import ollama
    source, rubric, _ = fixture_data()
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError('http://localhost/private', 500, 'private', {}, None)
    monkeypatch.setattr(ollama.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(ollama.AssessmentError) as caught:
        ollama.assess(adapt_input(source), adapt_rubric(rubric),
                      {'OLLAMA_MODEL': 'test', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434'})
    assert caught.value.status == 503 and '500' in str(caught.value)
    assert 'private' not in str(caught.value)
