"""Bind an explicit rubric condition to validated model facts; never use gold labels."""
from copy import deepcopy
import hashlib
import json

# Fingerprints of the published chat/voice discovery definitions after the dataset adapter.
# Editing the definition, N/A policy, type, ID or rule disables this specialized binding.
DISCOVERY_DEFINITIONS = {
    '252bd0688ee987735aed61379d406a246e76c3c9b4b402b331a9faee3de10bee',
    '05b0e8a06ebb389b9600835e9135639a3ca1dfa2f710840b469121de5327618f'}
CONSULTATION_DEFINITIONS = {
    '063b2e41830033d72da96b7ae14cd6de4c718f7ef6d8749efec5a944ff0ec5e5',
    '5507197e6aa365cbd8a76e145ec73c2cead4b3851b415d4a1b5f5a16f43805ef'}


def refinement_criteria(criteria):
    return [c for c in criteria if semantic_fingerprint(c) in DISCOVERY_DEFINITIONS | CONSULTATION_DEFINITIONS]


def semantic_fingerprint(criterion):
    keys = ('id', 'answer_type', 'description', 'allow_na', 'na_condition', 'rule')
    data = {key: criterion.get(key) for key in keys}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def reconcile(criteria, rows, analysis, messages):
    updated = deepcopy(rows)
    by_id = {r['criterion_id']: r for r in updated}
    adjustments = []
    first_operator = next((i for i, m in enumerate(messages) if m['speaker'] == 'operator'), len(messages))
    available = {m['id'] for m in messages[:first_operator] if m['speaker'] in ('client', 'bot', 'system')}
    context = [mid for mid in analysis['context_message_ids'] if mid in available]
    # IVR button presses cannot establish that the client's business request was already known.
    has_client_request_context = any(m['id'] in context and m['speaker'] == 'client' and
                                     not m.get('text', '').strip().isdecimal() and m.get('text', '').strip()
                                     for m in messages[:first_operator])
    for criterion in criteria:
        if semantic_fingerprint(criterion) not in DISCOVERY_DEFINITIONS:
            continue
        row = by_id[criterion['id']]
        if analysis['initial_information'] == 'sufficient':
            answer = 'not_applicable' if context and has_client_request_context else 'needs_review'
            reason = ('Данных для первого ответа хватало с самого начала; по условию чек-листа уточнение не требовалось.'
                      if answer == 'not_applicable' else 'Не подтверждён исходный запрос клиента: меню и служебные события не заменяют содержание обращения.')
        elif analysis['initial_information'] == 'unclear':
            answer, reason = 'needs_review', 'Недостаточно данных, чтобы установить необходимость уточнения в начале разговора.'
        else:
            # Missing details alone do not prove that the operator clarified them correctly or on time.
            continue
        if (row['status'], row['value']) != (answer, None):
            adjustments.append({'criterion_id': criterion['id'], 'rule': 'initial_information_gate',
                                'before': {'status': row['status'], 'value': row['value']},
                                'after': {'status': answer, 'value': None}})
        row.update(status=answer, value=None, explanation=reason,
                   evidence_message_ids=context if answer == 'not_applicable' else [])
    return updated, adjustments
