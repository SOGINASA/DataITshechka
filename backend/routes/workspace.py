"""Read models for screens: bounded responses, no per-conversation HTTP/SQL fan-out."""
from datetime import datetime, timedelta, timezone
from math import ceil

from flask import Blueprint, jsonify, request
from sqlalchemy import select, func

from models import db, Conversation, Evaluation, Checklist, Appeal, Review, iso
from services import validation
from services.evaluation import score_summary

workspace_bp = Blueprint('workspace', __name__)
LOCAL_TZ = timezone(timedelta(hours=5))


def page_args():
    values = []
    for key, default, maximum in (('page', '1', 100000), ('per_page', '20', 100)):
        raw = request.args.get(key, default)
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 7 or not 1 <= int(raw) <= maximum:
            validation.fail(f'{key}: ожидается число от 1 до {maximum}.')
        values.append(int(raw))
    return values


def page_info(page, per_page, total):
    return {'page': page, 'per_page': per_page, 'total': total, 'pages': ceil(total / per_page)}


def open_count():
    return db.session.scalar(select(func.count()).select_from(Appeal).where(Appeal.status == 'open'))


def summaries():
    # Window ordering matches the detail API, including timestamp ties. Do not load
    # messages, original_results, evidence histories or ORM relationships here.
    latest = select(
        Evaluation.conversation_id, Evaluation.id.label('evaluation_id'), Evaluation.checklist_id,
        Evaluation.results,
        func.row_number().over(partition_by=Evaluation.conversation_id,
                               order_by=(Evaluation.created_at.desc(), Evaluation.id.desc())).label('rank'),
    ).subquery()
    pending = select(Evaluation.conversation_id, func.count().label('open_appeals')).join(
        Appeal, Appeal.evaluation_id == Evaluation.id).where(Appeal.status == 'open').group_by(
        Evaluation.conversation_id).subquery()
    statement = select(
        Conversation.id, Conversation.external_id, Conversation.title, Conversation.operator_name,
        Conversation.channel, Conversation.language, Conversation.created_at,
        latest.c.evaluation_id, latest.c.checklist_id, latest.c.results,
        func.coalesce(pending.c.open_appeals, 0).label('open_appeals'),
    ).outerjoin(latest, (latest.c.conversation_id == Conversation.id) & (latest.c.rank == 1)).outerjoin(
        pending, pending.c.conversation_id == Conversation.id).order_by(Conversation.created_at.desc(), Conversation.id.desc())
    records = []
    for row in db.session.execute(statement).mappings():
        item = dict(row)
        results = item.pop('results')
        item['created_at'] = iso(item['created_at'])
        item['assessed'] = results is not None and not any(r['status'] == 'needs_review' for r in results)
        item['final_score'] = score_summary(results)['final_score'] if results is not None else None
        # Kept only within the server for the overview's criterion chart.
        item['_results'] = results or []
        records.append(item)
    return records


def public_summary(item):
    return {key: value for key, value in item.items() if not key.startswith('_')}


def appeal_rows(statement):
    rows = db.session.execute(statement.join(Evaluation, Appeal.evaluation_id == Evaluation.id)
                              .join(Conversation, Evaluation.conversation_id == Conversation.id)
                              .join(Checklist, Evaluation.checklist_id == Checklist.id)).mappings()
    items = []
    for row in rows:
        item = dict(row)
        criteria = item.pop('criteria')
        item['created_at'] = iso(item['created_at'])
        item['criterion_name'] = next((c['title'] for c in criteria if c['id'] == item['criterion_id']), item['criterion_id'])
        items.append(item)
    return items


def appeal_statement():
    return select(Appeal.id, Appeal.evaluation_id, Appeal.criterion_id, Appeal.status, Appeal.created_at,
                  Conversation.id.label('conversation_id'), Conversation.operator_name, Checklist.criteria).select_from(Appeal)


def conversation_bundle(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    evaluations = db.session.scalars(select(Evaluation).where(Evaluation.conversation_id == conversation_id)
                                     .order_by(Evaluation.created_at, Evaluation.id)).all()
    evaluation_ids = select(Evaluation.id).where(Evaluation.conversation_id == conversation_id)
    return {
        'conversation': conversation.to_dict(),
        'evaluations': [e.to_dict() for e in evaluations],
        'checklists': [c.to_dict() for c in db.session.scalars(select(Checklist).order_by(Checklist.created_at, Checklist.id))],
        'appeals': [a.to_dict() for a in db.session.scalars(select(Appeal).where(Appeal.evaluation_id.in_(evaluation_ids))
                                                          .order_by(Appeal.created_at.desc(), Appeal.id.desc()))],
        'reviews': [r.to_dict() for r in db.session.scalars(select(Review).where(Review.evaluation_id.in_(evaluation_ids))
                                                          .order_by(Review.revision))],
    }


@workspace_bp.get('/overview')
def overview():
    records = summaries()
    assessed = [c for c in records if c['assessed']]
    scores = [c['final_score'] for c in assessed if c['final_score'] is not None]
    today = datetime.now(LOCAL_TZ).date()
    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        values = [c['final_score'] for c in records if c['final_score'] is not None
                  and datetime.fromisoformat(c['created_at'].replace('Z', '+00:00')).astimezone(LOCAL_TZ).date() == day]
        trend.append({'date': day.isoformat(), 'value': sum(values) / len(values) if values else None})
    # Each result contains the rubric configuration used for that assessment.
    latest = next((c for c in records if c['evaluation_id']), None)
    criteria = []
    if latest:
        for criterion in [r for r in latest['_results'] if r.get('answer_type', 'binary') != 'flag'][:5]:
            values = []
            for conversation in records:
                result = next((r for r in conversation['_results'] if r['criterion_id'] == criterion['criterion_id']), None)
                if result and result.get('value') is not None:
                    maximum = max((s['value'] for s in result.get('scale', [])), default=1) if result.get('answer_type') == 'scale' else 1
                    values.append(max(0, min(1, result['value'] / maximum)) * 100 if maximum > 0 else 0)
            criteria.append({'name': criterion['title'], 'value': sum(values) / len(values) if values else None})
    queue = appeal_rows(appeal_statement().where(Appeal.status == 'open')
                        .order_by(Appeal.created_at.desc(), Appeal.id.desc()).limit(4))
    return jsonify({'total': len(records), 'assessed': len(assessed),
                    'attention': sum(c['final_score'] is not None and c['final_score'] < 80 for c in records),
                    'average': sum(scores) / len(scores) if scores else None,
                    'open_appeals': sum(c['open_appeals'] for c in records),
                    'recent': [public_summary(c) for c in records[:6]], 'appeals': queue,
                    'trend': trend, 'criteria': criteria})


@workspace_bp.get('/conversations')
def conversations():
    page, per_page = page_args()
    language = validation.choice(request.args.get('language', 'all'), 'language', ('all', 'ru', 'kk', 'en'))
    channel = validation.choice(request.args.get('channel', 'all'), 'channel', ('all', 'chat', 'call'))
    status = validation.choice(request.args.get('status', 'all'), 'status', ('all', 'assessed', 'pending', 'attention', 'appeal'))
    search = request.args.get('search', '').strip().casefold()
    if len(search) > 200:
        validation.fail('search: не более 200 символов.')
    records = summaries()
    total_open = sum(c['open_appeals'] for c in records)
    filtered = [c for c in records if (language == 'all' or c['language'] == language)
                and (channel == 'all' or c['channel'] == channel)
                and (not search or search in f"{c['id']} {c['title']} {c['operator_name'] or 'Не указан'}".casefold())
                and (status == 'all' or status == 'assessed' and c['assessed']
                     or status == 'pending' and not c['assessed']
                     or status == 'attention' and c['final_score'] is not None and c['final_score'] < 80
                     or status == 'appeal' and c['open_appeals'] > 0)]
    return jsonify({'items': [public_summary(c) for c in filtered[(page - 1) * per_page:page * per_page]],
                    'pagination': page_info(page, per_page, len(filtered)), 'open_appeals': total_open})


@workspace_bp.get('/conversations/<conversation_id>')
def conversation(conversation_id):
    return jsonify({**conversation_bundle(conversation_id), 'open_appeals': open_count()})


@workspace_bp.get('/appeals')
def appeals():
    page, per_page = page_args()
    status = validation.choice(request.args.get('status', 'open'), 'status', ('all', 'open', 'resolved'))
    selected_id = request.args.get('selected')
    selected = db.get_or_404(Appeal, selected_id) if selected_id else None
    if selected and status != 'all':
        status = selected.status
    condition = Appeal.status == status if status != 'all' else True
    total = db.session.scalar(select(func.count()).select_from(Appeal).where(condition))
    items = appeal_rows(appeal_statement().where(condition).order_by(Appeal.created_at.desc(), Appeal.id.desc())
                       .offset((page - 1) * per_page).limit(per_page))
    if selected is None and items:
        selected = db.session.get(Appeal, items[0]['id'])
    bundle = None
    if selected:
        evaluation = db.session.get(Evaluation, selected.evaluation_id)
        bundle = conversation_bundle(evaluation.conversation_id)
    return jsonify({'items': items, 'pagination': page_info(page, per_page, total), 'status': status,
                    'selected_id': selected.id if selected else None, 'detail': bundle, 'open_appeals': open_count()})
