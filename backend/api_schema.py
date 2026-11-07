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
    status = enum('pass', 'fail', 'scored', 'not_applicable', 'needs_review')
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
    rule = {'oneOf': [obj({'type': enum('manual', 'semantic')}, ('type',)),
                      obj({'type': enum('contains_any', 'contains_none'),
                           'speaker': enum('client', 'operator', 'bot', 'system', 'any'),
                           'terms': terms}, ('type', 'terms'))]}
    criterion = obj({'id': {**text(80), 'pattern': '^[a-zA-Z0-9_-]+$'}, 'title': text(200),
                     'description': text(4000, minimum=0), 'weight': {'type': 'number', 'minimum': 0, 'maximum': 100},
                     'critical': {'type': 'boolean'}, 'rule': ref('Rule'),
                     'answer_type': enum('binary', 'scale', 'flag'), 'allow_na': {'type': 'boolean'},
                     'na_condition': text(2000, minimum=0), 'section': text(200, minimum=0),
                     'require_evidence': {'type': 'boolean'},
                     'scale': array(obj({'value': {'type': 'number', 'minimum': 0, 'maximum': 1000},
                                         'label': text(2000)}, ('value', 'label')), 30)}, ('id', 'title'))
    checklist = obj({'name': text(160), 'version': text(40), 'description': text(4000, minimum=0),
                     'is_demo': {'type': 'boolean'}, 'criteria': array(ref('Criterion'), 100, 1)}, ('name', 'version', 'criteria'))
    evidence = obj({'message_id': text(80), 'quote': text(10000), 'start_ms': millisecond,
                    'end_ms': millisecond, 'matched_terms': array(text(200), 30)},
                   ('message_id', 'quote', 'start_ms', 'end_ms', 'matched_terms'))
    result = obj({'criterion_id': text(80), 'title': text(200), 'weight': {'type': 'number'},
                  'critical': {'type': 'boolean'}, 'status': status, 'source': enum('baseline', 'human', 'model'),
                  'evidence': array(ref('Evidence')), 'explanation': text(4000)},
                 ('criterion_id', 'title', 'weight', 'critical', 'status', 'source', 'evidence', 'explanation'))
    span = obj({'start_message_id': text(80), 'end_message_id': text(80)}, ('start_message_id', 'end_message_id'))
    for key in ('answer_type', 'allow_na', 'na_condition', 'section', 'require_evidence', 'scale'):
        result['properties'][key] = criterion['properties'][key]
    result['properties'].update(value={'type': ['boolean', 'number', 'null']}, reviewed_range=span,
                                points={'type': ['number', 'null']}, effective_weight={'type': 'number'},
                                effective_points={'type': ['number', 'null']})
    override = obj({'criterion_id': text(80), 'status': status, 'value': {'type': ['boolean', 'number', 'null']},
                    'explanation': text(4000), 'evidence_message_ids': array(text(80), 50), 'reviewed_range': span},
                   ('criterion_id', 'explanation'))
    override['anyOf'] = [{'required': ['value']}, {'required': ['status']}]
    evaluation = obj({'id': identifier, 'conversation_id': identifier, 'checklist_id': identifier,
                      'engine': text(80), 'original_results': array(ref('Result')),
                      'results': array(ref('Result')), 'revision': {'type': 'integer', 'minimum': 1},
                      'created_at': timestamp, 'score': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100},
                      'coverage': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100},
                      'needs_review': {'type': 'boolean'}, 'critical_failures': array(text(80)),
                      'counts': obj({s: {'type': 'integer', 'minimum': 0} for s in status['enum']}, status['enum'])})
    evaluation['required'] = list(evaluation['properties'])
    evaluation['properties'].update(final_score={'type': ['number', 'null']}, score_is_partial={'type': 'boolean'},
                                    applicable_weight={'type': 'number'}, gross_error_detected={'type': ['boolean', 'null']},
                                    sections=array(obj({}, strict=False)), original_summary=obj({}, strict=False),
                                    run_metadata={'anyOf': [{'type': 'null'}, obj({}, strict=False)]})
    review_input = obj({'expected_revision': {'type': 'integer', 'minimum': 1, 'maximum': 2147483647},
                        'reviewer': {**text(120), 'description': 'Свободная подпись, не подтверждённая учётная запись.'},
                        'comment': text(4000), 'overrides': array(override, 100, 1)},
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
            'provider': enum('freedom'), 'dataset_group_id': text(24), 'conversation_id': text(120),
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
    appeal = obj({'id': identifier, 'evaluation_id': identifier, 'criterion_id': text(80),
                  'evaluation_revision': {'type': 'integer'}, 'revision': {'type': 'integer'},
                  'author': text(120), 'comment': text(4000), 'disputed_result': ref('Result'),
                  'status': enum('open', 'resolved'), 'decision': {'type': ['string', 'null'], 'enum': ['confirm', 'change', None]},
                  'review_id': text(36, True), 'created_at': timestamp,
                  'resolved_at': {'type': ['string', 'null'], 'format': 'date-time'}})
    appeal['required'] = list(appeal['properties'])
    schemas['Appeal'] = appeal
    schemas['AssessmentOverride'] = override
    paths = {}

    def operation(path, method, summary, response, request=None, paginated=False, filters=None, success_code=None):
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
        code = success_code or ('201' if method == 'post' else '200')
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
              filters={'channel': enum('chat', 'call'), 'language': enum('ru', 'kk', 'en'), 'external_id': text(160),
                       'dataset_group_id': {**text(24), 'pattern': '^[A-Za-z0-9_-]+$'}})
    operation('/api/conversations', 'post', 'Добавить диалог', ref('Conversation'), ref('ConversationInput'))
    operation('/api/conversations/import', 'post', 'Атомарный импорт до 100 диалогов',
              obj({'items': array(ref('ConversationSummary')), 'imported': {'type': 'integer'}}, ('items', 'imported')),
              obj({'conversations': array(ref('ConversationInput'), 100, 1)}, ('conversations',)))
    operation('/api/conversations/{conversation_id}', 'get', 'Реплики и последняя оценка', ref('ConversationDetail'))
    operation('/api/checklists', 'get', 'Версии чек-листов', ref('Checklist'), paginated=True)
    operation('/api/checklists', 'post', 'Добавить неизменяемую версию чек-листа', ref('Checklist'), ref('ChecklistInput'))
    operation('/api/checklists/{checklist_id}', 'get', 'Чек-лист', ref('Checklist'))
    operation('/api/checklists/{checklist_id}/versions', 'post', 'Сохранить изменения новой версией', ref('Checklist'),
              obj({'version': text(40), 'name': text(160), 'description': text(4000, minimum=0),
                   'criteria': array(ref('Criterion'), 100, 1)}, ('version',)))
    operation('/api/conversations/{conversation_id}/evaluations', 'get', 'История оценок', ref('Evaluation'), paginated=True)
    operation('/api/conversations/{conversation_id}/evaluations', 'post', 'Синхронная оценка по выбранному чек-листу', ref('Evaluation'),
              obj({'checklist_id': identifier, 'engine': enum('auto', 'baseline', 'ollama')}, ('checklist_id',)))
    operation('/api/evaluations/{evaluation_id}', 'get', 'Исходная и текущая оценка', ref('Evaluation'))
    operation('/api/evaluations/{evaluation_id}/reviews', 'get', 'История ручных решений', ref('Review'), paginated=True)
    operation('/api/evaluations/{evaluation_id}/reviews', 'post', 'Ручной пересмотр; конфликт ревизии возвращает 409',
              obj({'review': ref('Review'), 'evaluation': ref('Evaluation')}, ('review', 'evaluation')), ref('ReviewInput'))
    operation('/api/evaluations/{evaluation_id}/export', 'get', 'Полный JSON-отчёт с историей',
              obj({'schema_version': enum('1.0'), 'conversation': ref('Conversation'), 'checklist': ref('Checklist'),
                   'evaluation': ref('Evaluation'), 'reviews': array(ref('Review')), 'appeals': array(ref('Appeal'))},
                  ('schema_version', 'conversation', 'checklist', 'evaluation', 'reviews', 'appeals')))
    operation('/api/evaluations/{evaluation_id}/appeals', 'get', 'История апелляций', ref('Appeal'), paginated=True)
    operation('/api/evaluations/{evaluation_id}/appeals', 'post', 'Подать апелляцию по критерию', ref('Appeal'),
              obj({'criterion_id': text(80), 'expected_revision': {'type': 'integer', 'minimum': 1, 'maximum': 2147483647},
                   'author': text(120), 'comment': text(4000)}, ('criterion_id', 'expected_revision', 'author', 'comment')))
    operation('/api/appeals/{appeal_id}', 'get', 'Спорная оценка и состояние апелляции', ref('Appeal'))
    operation('/api/appeals/{appeal_id}/decision', 'post', 'Решение проверяющего с пересчётом итога',
              obj({'appeal': ref('Appeal'), 'review': ref('Review'), 'evaluation': ref('Evaluation')}, ('appeal', 'review', 'evaluation')),
              obj({'expected_revision': {'type': 'integer', 'minimum': 1, 'maximum': 2147483647}, 'reviewer': text(120),
                   'reason': text(4000), 'decision': enum('confirm', 'change'), 'override': ref('AssessmentOverride')},
                  ('expected_revision', 'reviewer', 'reason', 'decision')), success_code='200')
    operation('/api/datasets/import', 'post', 'Импорт DEV или контрольной группы через сервер',
              obj({'dataset_group_id': text(24), 'received': {'type': 'integer'}, 'imported': {'type': 'integer'},
                   'pending': {'type': 'integer'}, 'skipped': {'type': 'integer'}, 'dry_run': {'type': 'boolean'}},
                  ('dataset_group_id', 'received', 'imported', 'pending', 'skipped', 'dry_run')),
              obj({'group_id': {**text(24), 'pattern': '^[A-Za-z0-9_-]+$'}, 'dry_run': {'type': 'boolean'}}, ('group_id',)), success_code='200')
    paths['/api/transcribe'] = {'post': {
        'summary': 'Локальная транскрибация аудио; исходный файл после запроса удаляется',
        'operationId': 'post_transcribe',
        'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': obj({
            'file': {'type': 'string', 'format': 'binary'}, 'language': enum('auto', 'ru', 'kk', 'en')}, ('file',))}}},
        'responses': {'200': {'description': 'Сегменты распознанной речи', 'content': {'application/json': {'schema': obj({
            'language': text(8), 'duration_seconds': {'type': 'number'}, 'model': text(160),
            'segments': array(obj({'start_seconds': {'type': 'number'}, 'end_seconds': {'type': 'number'}, 'text': text(10000)},
                                  ('start_seconds', 'end_seconds', 'text')), 2000, 1)}, ('language', 'duration_seconds', 'model', 'segments'))}}},
                      'default': {'description': 'Ошибка загрузки или локального STT', 'content': {'application/json': {'schema': ref('Error')}}}}
    }}
    operation('/api/stats', 'get', 'Счётчики диалогов, оценок и пересмотров', obj({}, strict=False))
    number_or_null = {'type': ['number', 'null']}
    count = {'type': 'integer', 'minimum': 0}
    summary = obj({'id': identifier, 'external_id': text(160, True), 'title': text(200),
                   'operator_name': text(120, True), 'channel': enum('chat', 'call'), 'language': enum('ru', 'kk', 'en'),
                   'created_at': timestamp, 'evaluation_id': text(36, True), 'checklist_id': text(36, True),
                   'assessed': {'type': 'boolean'}, 'final_score': number_or_null, 'open_appeals': count})
    summary['required'] = list(summary['properties'])
    schemas['WorkspaceConversation'] = summary
    row = obj({key: appeal['properties'][key] for key in ('id', 'evaluation_id', 'criterion_id', 'status', 'created_at')})
    row['properties'].update(conversation_id=identifier, operator_name=text(120, True), criterion_name=text(200))
    row['required'] = list(row['properties'])
    schemas['WorkspaceAppeal'] = row
    bundle = obj({'conversation': ref('Conversation'), 'evaluations': array(ref('Evaluation')),
                  'checklists': array(ref('Checklist')), 'appeals': array(ref('Appeal')), 'reviews': array(ref('Review'))},
                 ('conversation', 'evaluations', 'checklists', 'appeals', 'reviews'))
    schemas['WorkspaceDetail'] = bundle
    page_filters = {name: {'type': 'integer', 'minimum': 1, 'maximum': maximum, 'default': default}
                    for name, maximum, default in [('page', 100000, 1), ('per_page', 100, 20)]}
    operation('/api/workspace/overview', 'get', 'Готовая сводка, 6 диалогов и 4 апелляции без транскриптов',
              obj({'total': count, 'assessed': count, 'attention': count, 'average': number_or_null, 'open_appeals': count,
                   'recent': array(ref('WorkspaceConversation'), 6), 'appeals': array(ref('WorkspaceAppeal'), 4),
                   'trend': array(obj({'date': {'type': 'string', 'format': 'date'}, 'value': number_or_null}, ('date', 'value')), 7),
                   'criteria': array(obj({'name': text(200), 'value': number_or_null}, ('name', 'value')), 5)},
                  ('total', 'assessed', 'attention', 'average', 'open_appeals', 'recent', 'appeals', 'trend', 'criteria')))
    operation('/api/workspace/conversations', 'get', 'Страница диалогов с последней оценкой и фильтрами',
              obj({'items': array(ref('WorkspaceConversation'), 100), 'pagination': ref('Pagination'), 'open_appeals': count},
                  ('items', 'pagination', 'open_appeals')),
              filters={**page_filters, 'search': text(200, minimum=0), 'language': enum('all', 'ru', 'kk', 'en'),
                       'channel': enum('all', 'chat', 'call'), 'status': enum('all', 'assessed', 'pending', 'attention', 'appeal')})
    detail_response = deepcopy(bundle)
    detail_response['properties']['open_appeals'] = count
    detail_response['required'].append('open_appeals')
    operation('/api/workspace/conversations/{conversation_id}', 'get', 'Карточка одного диалога с историей и чек-листами', detail_response)
    operation('/api/workspace/appeals', 'get', 'Страница апелляций и контекст выбранного разговора',
              obj({'items': array(ref('WorkspaceAppeal'), 100), 'pagination': ref('Pagination'), 'open_appeals': count,
                   'status': enum('all', 'open', 'resolved'), 'selected_id': text(36, True),
                   'detail': {'anyOf': [ref('WorkspaceDetail'), {'type': 'null'}]}},
                  ('items', 'pagination', 'open_appeals', 'status', 'selected_id', 'detail')),
              filters={**page_filters, 'status': enum('all', 'open', 'resolved'),
                       'selected': {**identifier, 'description': 'При прямом переходе выбирает апелляцию и её статус.'}})
    return {'openapi': '3.1.0', 'info': {'title': 'CQA API', 'version': '1.1.0',
            'description': 'Прототип без авторизации: официальный чек-лист, шкалы, N/A, апелляции и локальный Ollama.'},
            'servers': [{'url': '/'}], 'security': [], 'paths': paths, 'components': {'schemas': schemas}}
