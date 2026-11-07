"""Bridge immutable annotation releases to the production evaluator contract."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from services import validation
from services.evaluation import evaluate, apply_overrides, summarize

ALIASES = {'management': 'dialogue_management', 'critical_errors': 'gross_errors'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line]


def load_release(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files_sha256'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or sha256(path) != expected:
            raise ValueError(f'Release file checksum mismatch: {name}')
    inputs = read_lines(root / 'inputs.jsonl')
    references = read_lines(root / 'references.jsonl')
    rubrics = json.loads((root / 'checklists.json').read_text(encoding='utf-8'))
    for rows in (inputs, references):
        if len({r['conversation_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate conversation_id in release')
    if {r['conversation_id'] for r in inputs} != {r['conversation_id'] for r in references}:
        raise ValueError('Release inputs and references differ')
    return inputs, {r['conversation_id']: r for r in references}, rubrics, manifest


def adapt_rubric(source):
    criteria = []
    for item in source['criteria']:
        # This alias is specific to the legacy annotation format. Other IDs stay configurable.
        flag = item['id'] == 'critical_errors'
        kind = 'flag' if flag else 'scale' if item['type'] == 'ordinal' else 'binary'
        description = '\n'.join(item.get(k, '') for k in ('description', 'pass_rule', 'fail_rule'))
        criteria.append({
            'id': ALIASES.get(item['id'], item['id']), 'title': item['name'],
            'description': description, 'answer_type': kind, 'weight': item['weight'],
            'critical': bool(item.get('is_critical')), 'allow_na': item['na_allowed'],
            'na_condition': item['na_rule'], 'section': item.get('section', ''),
            'require_evidence': True, 'rule': {'type': 'semantic'},
            'scale': [{'value': v, 'label': str(v)} for v in item.get('allowed_scores', [])]})
    description = source.get('scoring_notes', '')
    if source.get('assessment_scope'):
        description += '\n' + json.dumps(source['assessment_scope'], ensure_ascii=False)
    return SimpleNamespace(**validation.checklist({
        'name': source['name'], 'version': source['version'],
        'description': description, 'criteria': criteria}))


def adapt_input(source):
    # No reference labels, reviewer rationale, audio links or gold-only span exclusions.
    # Timestamps in voice transcripts are not guaranteed to align with the audio player.
    data = validation.conversation({
        'external_id': source['conversation_id'], 'title': source['conversation_id'],
        'language': {'RU': 'ru', 'KZ': 'kk', 'EN': 'en'}[source['language']],
        'channel': {'agent chat': 'chat', 'voice call': 'call'}[source['channel']],
        'messages': [{'id': t['turn_id'], 'speaker': t['speaker'], 'text': t['text']}
                     for t in source['transcript']]})
    return SimpleNamespace(**data)


def adapt_reference(source, conversation, rubric):
    overrides = []
    for label in source['labels']:
        verdict = label['verdict']
        flag = label['criterion_id'] == 'critical_errors'
        status = {'score': 'scored', 'na': 'not_applicable', 'uncertain': 'needs_review'}.get(verdict, verdict)
        value = label['score'] if verdict == 'score' else verdict == 'pass' if verdict in ('pass', 'fail') else None
        if flag and verdict in ('pass', 'fail'):
            status = 'fail' if value else 'pass'
        override = {'criterion_id': ALIASES.get(label['criterion_id'], label['criterion_id']),
                    'status': status, 'value': value, 'explanation': label['reason'],
                    'evidence_message_ids': label.get('evidence_turn_ids', [])}
        span = label.get('checked_span')
        if span:
            override['reviewed_range'] = {'start_message_id': span['start_turn_id'],
                                          'end_message_id': span['end_turn_id']}
        overrides.append(validation.assessment_item(override))
    results, _ = apply_overrides(evaluate(conversation, rubric), overrides, conversation.messages)
    if summarize(results)['final_score'] != source['score_summary']['total']:
        raise ValueError('Reference score changed during contract conversion')
    return results
