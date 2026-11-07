from copy import deepcopy

from flask import Blueprint, jsonify, request, url_for
from sqlalchemy import select, func

from models import db, Conversation, Checklist, Evaluation, Review
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
    payload = validation.obj(body(), ('checklist_id',), ('checklist_id',))
    checklist_id = validation.string(payload['checklist_id'], 'checklist_id', 36)
    conversation = db.get_or_404(Conversation, conversation_id)
    checklist = db.get_or_404(Checklist, checklist_id)
    results = evaluate(conversation, checklist)
    item = Evaluation(conversation_id=conversation.id, checklist_id=checklist.id, engine=ENGINE,
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
    updated, changes = apply_overrides(item.results, payload['overrides'])
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
                        'reviews': [r.to_dict() for r in db.session.scalars(select(Review)
                                    .where(Review.evaluation_id == item.id).order_by(Review.revision))]})
    response.headers['Content-Disposition'] = f'attachment; filename="evaluation-{item.id}.json"'
    return response


@cqa_bp.get('/stats')
def stats():
    return jsonify({'conversations': db.session.scalar(select(func.count()).select_from(Conversation)),
                    'evaluations': db.session.scalar(select(func.count()).select_from(Evaluation)),
                    'reviews': db.session.scalar(select(func.count()).select_from(Review)),
                    'by_channel': dict(db.session.execute(select(Conversation.channel, func.count())
                                                         .group_by(Conversation.channel)).all()),
                    'by_language': dict(db.session.execute(select(Conversation.language, func.count())
                                                          .group_by(Conversation.language)).all())})
