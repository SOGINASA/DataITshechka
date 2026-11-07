"""OpenAPI 3.1 contract for the unauthenticated hackathon backend."""
from copy import deepcopy


def ref(name):
    return {'$ref': f'#/components/schemas/{name}'}


def text(limit=None, nullable=False, minimum=1):
    value = {'type': ['string', 'null'] if nullable else 'string', 'minLength': minimum}
    if limit:
        value['maxLength'] = limit
    return value


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


def array(items, maximum=None, minimum=0):
    value = {'type': 'array', 'items': items, 'minItems': minimum}
    if maximum:
        value['maxItems'] = maximum
    return value


def obj(properties, required=(), strict=True):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': not strict}


def specification():
    identifier = text(36)
    status = enum('pass', 'fail', 'not_applicable', 'needs_review')
    timestamp = {'type': 'string', 'format': 'date-time'}
    millisecond = {'type': ['integer', 'null'], 'minimum': 0, 'maximum': 86400000}
    message = obj({'id': text(80), 'speaker': enum('client', 'operator', 'bot', 'system'),
                   'text': text(10000), 'start_ms': millisecond, 'end_ms': millisecond}, ('speaker', 'text'))
    conversation = obj({'external_id': text(160, True), 'title': text(200), 'channel': enum('chat', 'call'),
                        'language': enum('ru', 'kk', 'en'), 'operator_name': text(120, True),
                        'recording_url': {**text(2048, True), 'description': 'HTTP(S) ссылка без логина/пароля; сервер её не загружает.'},
                        'messages': array(ref('Message'), 2000, 1)}, ('title', 'channel', 'language', 'messages'))
    terms = obj({language: array(text(200), 30, 1) for language in ('ru', 'kk', 'en')})
    terms['minProperties'] = 1
    rule = {'oneOf': [obj({'type': enum('manual')}, ('type',)),
                      obj({'type': enum('contains_any', 'contains_none'),
                           'speaker': enum('client', 'operator', 'bot', 'system', 'any'),
                           'terms': terms}, ('type', 'terms'))]}
    criterion = obj({'id': {**text(80), 'pattern': '^[a-zA-Z0-9_-]+$'}, 'title': text(200),
                     'description': text(4000, minimum=0), 'weight': {'type': 'number', 'minimum': 0.01, 'maximum': 100},
                     'critical': {'type': 'boolean'}, 'rule': ref('Rule')}, ('id', 'title'))
    checklist = obj({'name': text(160), 'version': text(40), 'description': text(4000, minimum=0),
                     'is_demo': {'type': 'boolean'}, 'criteria': array(ref('Criterion'), 100, 1)}, ('name', 'version', 'criteria'))
    evidence = obj({'message_id': text(80), 'quote': text(10000), 'start_ms': millisecond,
                    'end_ms': millisecond, 'matched_terms': array(text(200), 30, 1)},
                   ('message_id', 'quote', 'start_ms', 'end_ms', 'matched_terms'))
    result = obj({'criterion_id': text(80), 'title': text(200), 'weight': {'type': 'number'},
                  'critical': {'type': 'boolean'}, 'status': status, 'source': enum('baseline', 'human'),
                  'evidence': array(ref('Evidence')), 'explanation': text(4000)},
                 ('criterion_id', 'title', 'weight', 'critical', 'status', 'source', 'evidence', 'explanation'))
    evaluation = obj({'id': identifier, 'conversation_id': identifier, 'checklist_id': identifier,
                      'engine': enum('keyword-baseline-v1'), 'original_results': array(ref('Result')),
                      'results': array(ref('Result')), 'revision': {'type': 'integer', 'minimum': 1},
                      'created_at': timestamp, 'score': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100},
                      'coverage': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100},
                      'needs_review': {'type': 'boolean'}, 'critical_failures': array(text(80)),
                      'counts': obj({s: {'type': 'integer', 'minimum': 0} for s in status['enum']}, status['enum'])})
    evaluation['required'] = list(evaluation['properties'])
    review_input = obj({'expected_revision': {'type': 'integer', 'minimum': 1, 'maximum': 2147483647},
                        'reviewer': {**text(120), 'description': 'Свободная подпись, не подтверждённая учётная запись.'},
                        'comment': text(4000), 'overrides': array(obj({'criterion_id': text(80), 'status': status,
                                                                      'explanation': text(4000)},
                                                                     ('criterion_id', 'status', 'explanation')), 100, 1)},
                       ('expected_revision', 'reviewer', 'comment', 'overrides'))
    review = obj({'id': identifier, 'evaluation_id': identifier, 'revision': {'type': 'integer'},
                  'reviewer': text(120), 'comment': text(4000), 'created_at': timestamp,
                  'changes': array(obj({'criterion_id': text(80), 'before': ref('Result'), 'after': ref('Result')},
                                       ('criterion_id', 'before', 'after')))})
    review['required'] = list(review['properties'])
    conversation_output = deepcopy(conversation)
    conversation_output['properties'].update(id=identifier, created_at=timestamp, message_count={'type': 'integer'})
    checklist_output = deepcopy(checklist)
    checklist_output['properties'].update(id=identifier, created_at=timestamp)
    conversation_summary = deepcopy(conversation_output)
    del conversation_summary['properties']['messages']
    conversation_summary['required'].remove('messages')
    conversation_output['properties']['source_metadata'] = {
        'anyOf': [{'type': 'null'}, obj({
            'provider': enum('freedom'), 'dataset_group_id': enum('DEV'), 'conversation_id': text(120),
            'timestamp_reference': enum('conversation_start', 'first_message'),
            'time_origin': text(80, True), 'audio_alignment_verified': {'type': 'boolean'},
            'source_timestamps': {'type': 'object', 'additionalProperties': text(80)}
        }, ('provider', 'dataset_group_id', 'conversation_id', 'timestamp_reference',
            'time_origin', 'audio_alignment_verified', 'source_timestamps'))],
        'description': 'Происхождение импорта. first_message не подтверждает синхронизацию с аудио.'}
    conversation_detail = deepcopy(conversation_output)
    conversation_detail['properties']['latest_evaluation'] = {'anyOf': [ref('Evaluation'), {'type': 'null'}]}
    schemas = {'Message': message, 'ConversationInput': conversation, 'Conversation': conversation_output,
               'ConversationSummary': conversation_summary, 'ConversationDetail': conversation_detail,
               'Rule': rule, 'Criterion': criterion, 'ChecklistInput': checklist, 'Checklist': checklist_output,
               'Evidence': evidence, 'Result': result, 'Evaluation': evaluation, 'ReviewInput': review_input, 'Review': review,
               'Error': obj({'error': obj({'code': text(), 'message': text(), 'current_revision': {'type': 'integer'}},
                                        ('code', 'message'))}, ('error',)),
               'Pagination': obj({p: {'type': 'integer'} for p in ('page', 'per_page', 'total', 'pages')},
                                 ('page', 'per_page', 'total', 'pages'))}
    paths = {}

    def operation(path, method, summary, response, request=None, paginated=False, filters=None):
        parameters = []
        for part in path.split('/'):
            if part.startswith('{'):
                parameters.append({'name': part[1:-1], 'in': 'path', 'required': True, 'schema': identifier})
        if paginated:
            parameters.extend({'name': name, 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1,
                               'maximum': maximum, 'default': default}}
                              for name, maximum, default in [('page', 100000, 1), ('per_page', 100, 20)])
            response = obj({'items': array(response), 'pagination': ref('Pagination')}, ('items', 'pagination'))
        for name, schema in (filters or {}).items():
            parameters.append({'name': name, 'in': 'query', 'schema': schema})
        code = '201' if method == 'post' else '200'
        data = {'summary': summary, 'operationId': method + '_' + path.replace('/api', '').strip('/').replace('/', '_').replace('{', '').replace('}', ''),
                'parameters': parameters, 'responses': {code: {'description': 'Успех', 'content': {'application/json': {'schema': response}}},
                                                       'default': {'description': 'Ошибка (400/404/409/413/415/422/500/503)',
                                                                   'content': {'application/json': {'schema': ref('Error')}}}}}
        if request:
            data['requestBody'] = {'required': True, 'content': {'application/json': {'schema': request}}}
        paths.setdefault(path, {})[method] = data

    operation('/api', 'get', 'Описание сервиса', obj({}, strict=False))
    operation('/api/health', 'get', 'Работоспособность процесса', obj({'status': enum('ok')}, ('status',)))
    operation('/api/ready', 'get', 'Доступность БД и таблицы диалогов', obj({'status': enum('ready')}, ('status',)))
    paths['/api/ready']['get']['responses']['503'] = {'description': 'БД не готова', 'content': {'application/json': {
        'schema': obj({'status': enum('database_unavailable_or_uninitialized')}, ('status',))}}}
    operation('/api/openapi.json', 'get', 'OpenAPI 3.1', obj({}, strict=False))
    operation('/api/conversations', 'get', 'Диалоги', ref('ConversationSummary'), paginated=True,
              filters={'channel': enum('chat', 'call'), 'language': enum('ru', 'kk', 'en'), 'external_id': text(160)})
    operation('/api/conversations', 'post', 'Добавить диалог', ref('Conversation'), ref('ConversationInput'))
    operation('/api/conversations/import', 'post', 'Атомарный импорт до 100 диалогов',
              obj({'items': array(ref('ConversationSummary')), 'imported': {'type': 'integer'}}, ('items', 'imported')),
              obj({'conversations': array(ref('ConversationInput'), 100, 1)}, ('conversations',)))
    operation('/api/conversations/{conversation_id}', 'get', 'Реплики и последняя оценка', ref('ConversationDetail'))
    operation('/api/checklists', 'get', 'Версии чек-листов', ref('Checklist'), paginated=True)
    operation('/api/checklists', 'post', 'Добавить неизменяемую версию чек-листа', ref('Checklist'), ref('ChecklistInput'))
    operation('/api/checklists/{checklist_id}', 'get', 'Чек-лист', ref('Checklist'))
    operation('/api/conversations/{conversation_id}/evaluations', 'get', 'История оценок', ref('Evaluation'), paginated=True)
    operation('/api/conversations/{conversation_id}/evaluations', 'post', 'Синхронная оценка по выбранному чек-листу', ref('Evaluation'),
              obj({'checklist_id': identifier}, ('checklist_id',)))
    operation('/api/evaluations/{evaluation_id}', 'get', 'Исходная и текущая оценка', ref('Evaluation'))
    operation('/api/evaluations/{evaluation_id}/reviews', 'get', 'История ручных решений', ref('Review'), paginated=True)
    operation('/api/evaluations/{evaluation_id}/reviews', 'post', 'Ручной пересмотр; конфликт ревизии возвращает 409',
              obj({'review': ref('Review'), 'evaluation': ref('Evaluation')}, ('review', 'evaluation')), ref('ReviewInput'))
    operation('/api/evaluations/{evaluation_id}/export', 'get', 'Полный JSON-отчёт с историей',
              obj({'schema_version': enum('1.0'), 'conversation': ref('Conversation'), 'checklist': ref('Checklist'),
                   'evaluation': ref('Evaluation'), 'reviews': array(ref('Review'))},
                  ('schema_version', 'conversation', 'checklist', 'evaluation', 'reviews')))
    operation('/api/stats', 'get', 'Счётчики диалогов, оценок и пересмотров', obj({}, strict=False))
    return {'openapi': '3.1.0', 'info': {'title': 'CQA API', 'version': '1.0.0',
            'description': 'Прототип без авторизации. Keyword baseline требует подтверждения человеком; официальный чек-лист предоставляется отдельно.'},
            'servers': [{'url': '/'}], 'security': [], 'paths': paths, 'components': {'schemas': schemas}}
