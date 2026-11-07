"""Model wire format: fixed criterion keys and one answer, no redundant status/value pair."""
from copy import deepcopy
from .contracts import require, response_schema


def schema_for(checklist, dialog, excerpts):
    properties = deepcopy(response_schema(checklist)['properties']['results']['items']['properties'])
    for field in ('criterion_id', 'status', 'value'):
        properties.pop(field)
    allowed = [True, False, 'needs_review']
    if any(c['allow_na'] for c in checklist['criteria']):
        allowed.append('N/A')
    # bool and number must stay distinct, including false and zero.
    numbers = sorted({s['value'] for c in checklist['criteria'] for s in c['scale']})
    properties = {'answer': {'enum': allowed + numbers}, **properties}
    properties['reviewed_range'] = properties['reviewed_range']['anyOf'][1]
    ids = [m['id'] for m in dialog['messages']]
    for field in properties['reviewed_range']['properties'].values():
        field['enum'] = ids
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


def decode(raw, checklist):
    require(isinstance(raw, dict) and set(raw) == {'results'}, 'Expected only results')
    rows = raw['results']
    require(isinstance(rows, dict), 'Model results must be keyed by criterion ID')
    require(set(rows) == {c['id'] for c in checklist['criteria']}, 'Missing or unknown criterion keys')
    results = []
    for c in checklist['criteria']:
        row = rows[c['id']]
        require(isinstance(row, dict) and 'answer' in row, 'Missing model answer')
        row = deepcopy(row)
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
        results.append({**row, 'criterion_id': c['id'], 'status': status, 'value': value})
    return {'results': results}
