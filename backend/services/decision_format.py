"""Single string decision per criterion; deterministic, strictly typed decoding."""
from copy import deepcopy

VERSION = 'cqa-decision-v1'


def system_prompt(original):
    return original.replace(
        'A binary value true means Yes/pass; false means No/fail.\n'
        'A flag value true means a violation IS PRESENT (status fail); false means absent (status pass).\n'
        'A scale value must be one of the configured steps (status scored). N/A (status not_applicable,\n'
        'value null) is permitted only if allow_na is true and its stated condition is satisfied.\n'
        'If the provided evidence is insufficient to judge, use needs_review and null, never invent success.',
        'Output one answer string per criterion, without status or value fields.\n'
        'For binary: yes = fulfilled, no = not fulfilled. For flag: yes = violation PRESENT, no = absent.\n'
        'For scale use score_<number>, one of the exact schema choices.\n'
        'not_applicable is permitted only if allow_na is true and its stated condition is satisfied.\n'
        'Insufficient evidence: needs_review, never invent success.'
    ).replace('output status not_applicable and value null, never pass/true.',
              'output answer not_applicable, never yes.').replace(
        "Each value must match that criterion's\nanswer_type; a numeric scale result always uses status scored, never pass.",
        "Each answer must match that criterion's\nanswer_type and exact allowed answer strings; never emit status or value.")


def answers(criterion):
    if criterion['answer_type'] == 'scale':
        options = {f'score_{step["value"]}': ('scored', step['value']) for step in criterion['scale']}
    elif criterion['answer_type'] == 'flag':
        options = {'yes': ('fail', True), 'no': ('pass', False)}
    else:
        options = {'yes': ('pass', True), 'no': ('fail', False)}
    if criterion['allow_na']:
        options['not_applicable'] = ('not_applicable', None)
    options['needs_review'] = ('needs_review', None)
    return options


def schema(criteria, messages):
    mid = {'$ref': '#/$defs/message_id'}
    properties = {}
    for c in criteria:
        fields = {'answer': {'type': 'string', 'enum': list(answers(c))},
                  'explanation': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
                  'evidence_message_ids': {'type': 'array', 'maxItems': 50, 'items': mid},
                  'reviewed_range': {'type': 'object', 'additionalProperties': False,
                      'required': ['start_message_id', 'end_message_id'],
                      'properties': {'start_message_id': mid, 'end_message_id': mid}}}
        properties[c['id']] = {'type': 'object', 'additionalProperties': False,
                               'properties': fields, 'required': list(fields)}
    return {'type': 'object', 'additionalProperties': False, 'required': ['results'],
            '$defs': {'message_id': {'type': 'string', 'enum': [m['id'] for m in messages]}},
            'properties': {'results': {'type': 'object', 'additionalProperties': False,
                          'required': list(properties), 'properties': properties}}}


def decode(document, criteria):
    from services.validation import obj, fail
    rows = obj(document, ('results',), ('results',))['results']
    keys = [c['id'] for c in criteria]
    obj(rows, keys, keys)
    results = []
    fields = ('answer', 'explanation', 'evidence_message_ids', 'reviewed_range')
    for c in criteria:
        row = deepcopy(obj(rows[c['id']], fields, fields))
        answer = row.pop('answer')
        allowed = answers(c)
        if type(answer) is not str or answer not in allowed:
            fail('Invalid decision for criterion ' + c['id'])
        if row['reviewed_range'] is None:
            fail('A reviewed range is required')
        status, value = allowed[answer]
        results.append({**row, 'criterion_id': c['id'], 'status': status, 'value': value})
    return results
