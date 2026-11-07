from copy import deepcopy

from flask import Blueprint, jsonify, request, url_for, current_app
from sqlalchemy import select, func

from models import db, Conversation, Checklist, Evaluation, Review, Appeal, now
from services import validation
from services.evaluation import ENGINE, evaluate, apply_overrides

cqa_bp = Blueprint('cqa', __name__)


def body():
    return request.get_json()


def created(data, endpoint, **values):
    return jsonify(data), 201, {'Location': url_for(endpoint, **values)}


def pagination(statement, serialize):
    for key in ('page', 'per_page'):
        raw = request.args.get(key, '1' if key == 'page' else '20')
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 7:
            validation.fail(f'{key}: ожидается положительное целое число.')
    page, per_page = int(request.args.get('page', 1)), int(request.args.get('per_page', 20))
    if not 1 <= page <= 100000 or not 1 <= per_page <= 100:
        validation.fail('page: 1–100000, per_page: 1–100.')
    result = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return jsonify({'items': [serialize(item) for item in result.items],
                    'pagination': {'page': page, 'per_page': per_page, 'total': result.total, 'pages': result.pages}})


@cqa_bp.get('/conversations')
def conversations():
    statement = select(Conversation)
    for field, options in (('channel', ('chat', 'call')), ('language', ('ru', 'kk', 'en'))):
        if field in request.args:
            value = validation.choice(request.args[field], field, options)
            statement = statement.where(getattr(Conversation, field) == value)
    if 'external_id' in request.args:
        statement = statement.where(Conversation.external_id == validation.string(request.args['external_id'], 'external_id', 160))
    if 'dataset_group_id' in request.args:
        from services.freedom import validate_group, IntegrationError
        try:
            group_id = validate_group(request.args['dataset_group_id'])
        except IntegrationError as error:
            validation.fail(str(error))
        statement = statement.where(Conversation.source_metadata['dataset_group_id'].as_string() == group_id)
    statement = statement.order_by(Conversation.created_at.desc(), Conversation.id.desc())
    return pagination(statement, lambda item: item.to_dict(detail=False))


@cqa_bp.post('/conversations')
def create_conversation():
    item = Conversation(**validation.conversation(body()))
    db.session.add(item)
    db.session.commit()
    return created(item.to_dict(), 'cqa.conversation_detail', conversation_id=item.id)


@cqa_bp.post('/conversations/import')
def import_conversations():
    payload = validation.obj(body(), ('conversations',), ('conversations',))
    items = [Conversation(**validation.conversation(value))
             for value in validation.sequence(payload['conversations'], 'conversations', 100)]
    db.session.add_all(items)
    db.session.commit()
    return jsonify({'items': [item.to_dict(detail=False) for item in items], 'imported': len(items)}), 201


@cqa_bp.get('/conversations/<conversation_id>')
def conversation_detail(conversation_id):
    item = db.get_or_404(Conversation, conversation_id)
    data = item.to_dict()
    latest = db.session.scalar(select(Evaluation).where(Evaluation.conversation_id == item.id)
                               .order_by(Evaluation.created_at.desc(), Evaluation.id.desc()).limit(1))
    data['latest_evaluation'] = latest.to_dict() if latest else None
    return jsonify(data)


@cqa_bp.get('/checklists')
def checklists():
    return pagination(select(Checklist).order_by(Checklist.created_at.desc(), Checklist.id.desc()), lambda c: c.to_dict())


@cqa_bp.post('/checklists')
def create_checklist():
    item = Checklist(**validation.checklist(body()))
    db.session.add(item)
    db.session.commit()
    return created(item.to_dict(), 'cqa.checklist_detail', checklist_id=item.id)


@cqa_bp.get('/checklists/<checklist_id>')
def checklist_detail(checklist_id):
    return jsonify(db.get_or_404(Checklist, checklist_id).to_dict())


@cqa_bp.post('/conversations/<conversation_id>/evaluations')
def create_evaluation(conversation_id):
    payload = validation.obj(body(), ('checklist_id', 'engine'), ('checklist_id',))
    checklist_id = validation.string(payload['checklist_id'], 'checklist_id', 36)
    conversation = db.get_or_404(Conversation, conversation_id)
    checklist = db.get_or_404(Checklist, checklist_id)
    selected = validation.choice(payload.get('engine', 'auto'), 'engine', ('auto', 'baseline', 'ollama'))
    if selected == 'auto':
        selected = 'ollama' if any(c['rule']['type'] == 'semantic' for c in checklist.criteria) else 'baseline'
    metadata, engine = None, ENGINE
    if selected == 'ollama':
        from services.ollama import assess
        results, engine, metadata = assess(conversation, checklist, current_app.config)
    else:
        results = evaluate(conversation, checklist)
    item = Evaluation(conversation_id=conversation.id, checklist_id=checklist.id, engine=engine, run_metadata=metadata,
                      original_results=deepcopy(results), results=results)
    db.session.add(item)
    db.session.commit()
    return created(item.to_dict(), 'cqa.evaluation_detail', evaluation_id=item.id)


@cqa_bp.get('/conversations/<conversation_id>/evaluations')
def evaluations(conversation_id):
    db.get_or_404(Conversation, conversation_id)
    return pagination(select(Evaluation).where(Evaluation.conversation_id == conversation_id)
                      .order_by(Evaluation.created_at.desc(), Evaluation.id.desc()), lambda e: e.to_dict())


@cqa_bp.get('/evaluations/<evaluation_id>')
def evaluation_detail(evaluation_id):
    return jsonify(db.get_or_404(Evaluation, evaluation_id).to_dict())


@cqa_bp.get('/evaluations/<evaluation_id>/reviews')
def reviews(evaluation_id):
    db.get_or_404(Evaluation, evaluation_id)
    return pagination(select(Review).where(Review.evaluation_id == evaluation_id)
                      .order_by(Review.revision.asc()), lambda r: r.to_dict())


@cqa_bp.post('/evaluations/<evaluation_id>/reviews')
def create_review(evaluation_id):
    payload = validation.review(body())
    item = db.get_or_404(Evaluation, evaluation_id)
    if item.revision != payload['expected_revision']:
        return jsonify({'error': {'code': 'revision_conflict',
                                 'message': 'Оценка уже изменена. Загрузите актуальную версию.',
                                 'current_revision': item.revision}}), 409
    conversation = db.get_or_404(Conversation, item.conversation_id)
    updated, changes = apply_overrides(item.results, payload['overrides'], conversation.messages)
    item.results = updated
    # Always mark a revision, including explicit reconfirmation of the same decision.
    # SQLAlchemy emits UPDATE ... WHERE revision = old_revision atomically.
    item.revision += 1
    record = Review(evaluation_id=item.id, revision=item.revision, reviewer=payload['reviewer'],
                    comment=payload['comment'], changes=changes)
    db.session.add(record)
    db.session.commit()
    return jsonify({'review': record.to_dict(), 'evaluation': item.to_dict()}), 201


@cqa_bp.get('/evaluations/<evaluation_id>/export')
def export_evaluation(evaluation_id):
    item = db.get_or_404(Evaluation, evaluation_id)
    response = jsonify({'schema_version': '1.0',
                        'conversation': db.get_or_404(Conversation, item.conversation_id).to_dict(),
                        'checklist': db.get_or_404(Checklist, item.checklist_id).to_dict(),
                        'evaluation': item.to_dict(),
                        'appeals': [a.to_dict() for a in db.session.scalars(select(Appeal)
                                    .where(Appeal.evaluation_id == item.id).order_by(Appeal.created_at, Appeal.id))],
                        'reviews': [r.to_dict() for r in db.session.scalars(select(Review)
                                    .where(Review.evaluation_id == item.id).order_by(Review.revision))]})
    response.headers['Content-Disposition'] = f'attachment; filename="evaluation-{item.id}.json"'
    return response


@cqa_bp.get('/stats')
def stats():
    return jsonify({'conversations': db.session.scalar(select(func.count()).select_from(Conversation)),
                    'evaluations': db.session.scalar(select(func.count()).select_from(Evaluation)),
                    'reviews': db.session.scalar(select(func.count()).select_from(Review)),
                    'open_appeals': db.session.scalar(select(func.count()).select_from(Appeal).where(Appeal.status == 'open')),
                    'by_channel': dict(db.session.execute(select(Conversation.channel, func.count())
                                                         .group_by(Conversation.channel)).all()),
                    'by_language': dict(db.session.execute(select(Conversation.language, func.count())
                                                          .group_by(Conversation.language)).all())})


@cqa_bp.post('/checklists/<checklist_id>/versions')
def create_checklist_version(checklist_id):
    original = db.get_or_404(Checklist, checklist_id)
    payload = validation.obj(body(), ('version', 'name', 'description', 'criteria'), ('version',))
    source = {key: getattr(original, key) for key in ('name', 'version', 'description', 'is_demo', 'criteria')}
    source.update(payload)
    item = Checklist(**validation.checklist(source))
    db.session.add(item)
    db.session.commit()
    return created(item.to_dict(), 'cqa.checklist_detail', checklist_id=item.id)


@cqa_bp.get('/evaluations/<evaluation_id>/appeals')
def appeals(evaluation_id):
    db.get_or_404(Evaluation, evaluation_id)
    return pagination(select(Appeal).where(Appeal.evaluation_id == evaluation_id)
                      .order_by(Appeal.created_at, Appeal.id), lambda item: item.to_dict())


@cqa_bp.post('/evaluations/<evaluation_id>/appeals')
def create_appeal(evaluation_id):
    payload = validation.appeal(body())
    evaluation = db.get_or_404(Evaluation, evaluation_id)
    if evaluation.revision != payload['expected_revision']:
        return jsonify({'error': {'code': 'revision_conflict', 'message': 'Оценка изменилась. Загрузите актуальную версию.'}}), 409
    result = next((r for r in evaluation.results if r['criterion_id'] == payload['criterion_id']), None)
    if result is None:
        validation.fail('Критерий отсутствует в оценке.')
    item = Appeal(evaluation_id=evaluation.id, criterion_id=payload['criterion_id'],
                  evaluation_revision=evaluation.revision, author=payload['author'], comment=payload['comment'],
                  disputed_result=deepcopy(result))
    db.session.add(item)
    db.session.commit()
    return created(item.to_dict(), 'cqa.appeal_detail', appeal_id=item.id)


@cqa_bp.get('/appeals/<appeal_id>')
def appeal_detail(appeal_id):
    item = db.get_or_404(Appeal, appeal_id)
    return jsonify(item.to_dict())


@cqa_bp.post('/appeals/<appeal_id>/decision')
def decide_appeal(appeal_id):
    payload = validation.obj(body(), ('expected_revision', 'reviewer', 'reason', 'decision', 'override'),
                             ('expected_revision', 'reviewer', 'reason', 'decision'))
    decision = validation.choice(payload['decision'], 'decision', ('confirm', 'change'))
    revision = validation.number(payload['expected_revision'], 'expected_revision', 1, 2147483647, integer=True)
    reviewer = validation.string(payload['reviewer'], 'reviewer', 120)
    reason = validation.string(payload['reason'], 'reason', 4000)
    appeal = db.get_or_404(Appeal, appeal_id)
    evaluation = db.get_or_404(Evaluation, appeal.evaluation_id)
    if appeal.status != 'open' or evaluation.revision != revision:
        return jsonify({'error': {'code': 'revision_conflict', 'message': 'Апелляция закрыта или оценка уже изменилась.'}}), 409
    current = next(r for r in evaluation.results if r['criterion_id'] == appeal.criterion_id)
    if decision == 'confirm':
        if 'override' in payload:
            validation.fail('Для confirm override не допускается.')
        # A later review may have changed this criterion while this appeal was pending.
        if current['status'] != appeal.disputed_result['status'] or current.get('value') != appeal.disputed_result.get('value'):
            return jsonify({'error': {'code': 'revision_conflict', 'message': 'Спорная оценка уже изменена; подтвердить исходную нельзя.'}}), 409
        override = {'criterion_id': appeal.criterion_id, 'status': current['status'], 'explanation': reason}
        if current.get('answer_type') == 'scale':
            override['value'] = current.get('value')
    else:
        override = validation.assessment_item(payload.get('override'))
        if override['criterion_id'] != appeal.criterion_id:
            validation.fail('Решение должно относиться к оспариваемому критерию.')
    conversation = db.get_or_404(Conversation, evaluation.conversation_id)
    updated, changes = apply_overrides(evaluation.results, [override], conversation.messages)
    evaluation.results = updated
    evaluation.revision += 1
    record = Review(evaluation_id=evaluation.id, revision=evaluation.revision, reviewer=reviewer,
                    comment=reason, changes=changes)
    db.session.add(record)
    db.session.flush()
    appeal.status, appeal.decision, appeal.review_id, appeal.resolved_at = 'resolved', decision, record.id, now()
    db.session.commit()
    return jsonify({'appeal': appeal.to_dict(), 'review': record.to_dict(), 'evaluation': evaluation.to_dict()})


@cqa_bp.post('/datasets/import')
def import_organizer_dataset():
    from services.freedom import fetch_dataset, import_dataset, validate_group, IntegrationError
    payload = validation.obj(body(), ('group_id', 'dry_run'), ('group_id',))
    try:
        group_id = validate_group(payload['group_id'])
    except IntegrationError as error:
        validation.fail(str(error))
    dry_run = payload.get('dry_run', False)
    if type(dry_run) is not bool:
        validation.fail('dry_run должен быть boolean.')
    data = fetch_dataset(current_app.config['FREEDOM_API_URL'], group_id=group_id)
    return jsonify(import_dataset(data, dry_run=dry_run, group_id=group_id))
