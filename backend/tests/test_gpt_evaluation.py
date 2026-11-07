"""Provider contract, evidence validation, and credential-safe failures."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gpt_evaluation', ROOT / 'scripts/run_gpt_evaluation.py')
gpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpt)


@pytest.fixture
def sample():
    from services.validation import checklist
    c = SimpleNamespace(language='ru', channel='chat', messages=[{'id': 't0001', 'speaker': 'operator', 'text': 'Здравствуйте'}])
    k = SimpleNamespace(**checklist({'name': 'Test', 'version': '1', 'criteria': [{'id': 'contact', 'title': 'Greeting',
        'answer_type': 'binary', 'weight': 10, 'allow_na': False}]}))
    document = {'results': {'contact': {'status': 'pass', 'value': True, 'explanation': 'Есть приветствие.',
        'evidence_message_ids': ['t0001'], 'reviewed_range': {'start_message_id': 't0001', 'end_message_id': 't0001'}}}}
    envelope = {'status': 'completed', 'model': gpt.DEFAULT_MODEL, 'usage': {'input_tokens': 15, 'output_tokens': 10},
                'output': [{'type': 'reasoning', 'encrypted_content': 'DO NOT SAVE'},
                           {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(document)}]}]}
    return c, k, envelope


def test_final_output_uses_shared_validator_and_excludes_hidden_reasoning(sample):
    c, k, envelope = sample
    with patch.object(gpt, 'send', return_value=envelope):
        prediction, captured = gpt.assess_one('a', c, k, gpt.DEFAULT_MODEL, 12000, 'SECRET')
    assert prediction['state'] == 'ok'
    assert prediction['summary']['final_score'] == 100
    assert prediction['metadata']['prompt_eval_count'] == 15
    assert 'DO NOT SAVE' not in json.dumps(captured)
    assert 'SECRET' not in json.dumps((prediction, captured))


def test_rejects_nonexistent_evidence_and_truncated_answers(sample):
    c, k, envelope = sample
    envelope['status'] = 'incomplete'
    with pytest.raises(gpt.APIError):
        gpt.parse(envelope, c, k)
    envelope['status'] = 'completed'
    envelope['output'][1]['content'][0]['text'] = envelope['output'][1]['content'][0]['text'].replace('t0001', 'invented')
    with pytest.raises(ValueError):
        gpt.parse(envelope, c, k)


def test_http_failures_never_echo_key_or_remote_error_body():
    failure = HTTPError(gpt.ENDPOINT, 429, 'error', {}, io.BytesIO(json.dumps({'error': {
        'code': 'insufficient_quota', 'message': 'SECRET echoed private transcript'}}).encode()))
    with patch.object(gpt.request, 'build_opener') as opener:
        opener.return_value.open.side_effect = failure
        with pytest.raises(gpt.APIError, match='insufficient_quota') as caught:
            gpt.send({}, 'SECRET')
    assert 'SECRET' not in str(caught.value)
    assert caught.value.status == 429


def test_schema_and_request_on_full_release_have_no_labels():
    if not (ROOT / 'data/releases/dev-reviewed-v1/manifest.json').exists():
        pytest.skip('Private release unavailable')
    rows, _, rubrics, _ = gpt.load_release(ROOT / 'data/releases/dev-reviewed-v1')
    for row in rows:
        c, k = gpt.adapt_input(row), gpt.adapt_rubric(rubrics[row['checklist_hash']])
        body = gpt.payload(c, k, gpt.DEFAULT_MODEL, 12000)
        data = json.loads(body['input'][1]['content'])
        assert set(data) == {'rubric_description', 'criteria', 'language', 'channel', 'messages'}
        schema = body['text']['format']['schema']
        encoded = json.dumps(schema)
        assert encoded.count('"t0001"') == 1  # one shared enum, not repeated for every decision union
        assert 'const' not in encoded
        assert body['store'] is False


def test_full_baseline_comparison_checks_inputs_and_pairs_scores(tmp_path):
    baseline = ROOT / 'data/runs/full-compare-20261107/local-v1'
    if not (baseline / 'predictions.json').exists():
        pytest.skip('Private full baseline unavailable')
    rows, original, rubrics, _ = gpt.load_release(ROOT / 'data/releases/dev-reviewed-v1')
    prepared, refs = {}, {}
    for row in rows:
        cid = row['conversation_id']
        c, k = gpt.adapt_input(row), gpt.adapt_rubric(rubrics[row['checklist_hash']])
        prepared[cid] = (c, k)
        results = gpt.adapt_reference(original[cid], c, k)
        refs[cid] = {'results': results, 'summary': gpt.summarize(results),
                    'audio_reviewed': original[cid].get('assessment_context', {}).get('audio_reviewed', False)}
    local = json.loads((baseline / 'predictions.json').read_text(encoding='utf-8'))
    gpt.compare_baseline(tmp_path, rows, refs, prepared, {})
    assert not (tmp_path / 'comparison-with-qwen.json').exists()
    gpt.compare_baseline(tmp_path, rows, refs, prepared, local)
    report = json.loads((tmp_path / 'comparison-with-qwen.json').read_text(encoding='utf-8'))
    assert report['complete'] and report['accuracy_delta_gpt_minus_qwen'] == 0
    assert report['score_pairs_with_both_complete'] == 63
    prepared[rows[0]['conversation_id']][0].messages[0]['text'] = 'Altered input'
    with pytest.raises(ValueError, match='input/rubric mismatch'):
        gpt.compare_baseline(tmp_path, rows, refs, prepared, local)
