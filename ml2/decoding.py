"""Model wire format: fixed criterion keys and one answer, no redundant status/value pair."""
from copy import deepcopy
from .contracts import require, response_schema


def schema_for(checklist, dialog, excerpts):
    properties = deepcopy(response_schema(checklist)['properties']['results']['items']['properties'])
    for field in ('criterion_id', 'status', 'value', 'reviewed_range'):
        properties.pop(field)
    allowed = [True, False, 'needs_review']
    if any(c['allow_na'] for c in checklist['criteria']):
        allowed.append('N/A')
    # bool and number must stay distinct, including false and zero.
    numbers = sorted({s['value'] for c in checklist['criteria'] for s in c['scale']})
    properties = {'answer': {'enum': allowed + numbers}, **properties}
    ids = [m['id'] for m in dialog['messages']]
    properties['evidence_message_ids']['items']['enum'] = ids
    if not excerpts:
        properties['knowledge_status']['enum'] = ['not_needed', 'missing']
    assessment = {'type': 'object', 'additionalProperties': False,
                  'required': list(properties), 'properties': properties}
    keys = [c['id'] for c in checklist['criteria']]
    return {'type': 'object', 'additionalProperties': False, 'required': ['results'],
            '$defs': {'assessment': assessment}, 'properties': {'results': {
                'type': 'object', 'additionalProperties': False, 'required': keys,
                'properties': {k: {'$ref': '#/$defs/assessment'} for k in keys}}}}


def _reviewed_range(dialog, criterion):
    messages = dialog['messages']
    operators = [i for i, message in enumerate(messages) if message['speaker'] == 'operator']
    scope = criterion['review_scope']
    start, end = 0, len(messages) - 1
    if scope == 'through_first_operator' and operators:
        end = operators[0]
    elif scope == 'closing_exchange' and operators:
        last_operator = operators[-1]
        last_client = next((i for i in range(last_operator - 1, -1, -1)
                            if messages[i]['speaker'] == 'client'), None)
        previous_operator = next((i for i in range((last_client if last_client is not None else last_operator) - 1,
                                                   -1, -1)
                                  if messages[i]['speaker'] == 'operator'), None)
        start = previous_operator if previous_operator is not None else (
            last_client if last_client is not None else last_operator)
    return {'start_message_id': messages[start]['id'], 'end_message_id': messages[end]['id']}


def decode(raw, checklist, dialog):
    require(isinstance(raw, dict) and set(raw) == {'results'}, 'Expected only results')
    rows = raw['results']
    require(isinstance(rows, dict), 'Model results must be keyed by criterion ID')
    require(set(rows) == {c['id'] for c in checklist['criteria']}, 'Missing or unknown criterion keys')
    results = []
    for c in checklist['criteria']:
        row = rows[c['id']]
        require(isinstance(row, dict) and 'answer' in row, 'Missing model answer')
        row = deepcopy(row)
        require('reviewed_range' not in row, 'reviewed_range is assigned by the server')
        value = row.pop('answer')
        if value == 'N/A':
            status, value = 'not_applicable', None
        elif value == 'needs_review':
            status, value = 'needs_review', None
        elif c['answer_type'] == 'scale':
            status = 'scored'
        else:
            status = ('fail' if value else 'pass') if c['answer_type'] == 'flag' else ('pass' if value else 'fail')
        # Types, steps, N/A eligibility, knowledge and proof still go through validate_results.
        require(not ({'criterion_id', 'status', 'value'} & set(row)), 'Redundant assessment fields')
        results.append({**row, 'criterion_id': c['id'], 'status': status, 'value': value,
                        'reviewed_range': _reviewed_range(dialog, c)})
    return {'results': results}
