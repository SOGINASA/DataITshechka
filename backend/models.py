"""Persistent CQA data. Dialogues and checklist versions are immutable via the API."""
from datetime import datetime, timezone
from uuid import uuid4

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

db = SQLAlchemy()


@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, _):
    if isinstance(connection, sqlite3.Connection):
        connection.execute('PRAGMA foreign_keys=ON')


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


def iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    external_id = db.Column(db.String(160), unique=True)
    title = db.Column(db.String(200), nullable=False)
    channel = db.Column(db.String(10), nullable=False)
    language = db.Column(db.String(5), nullable=False)
    operator_name = db.Column(db.String(120))
    recording_url = db.Column(db.String(2048))
    messages = db.Column(db.JSON, nullable=False)
    source_metadata = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (
        db.CheckConstraint("channel IN ('chat','call')", name='conversation_channel'),
        db.CheckConstraint("language IN ('ru','kk','en')", name='conversation_language'),
    )

    def to_dict(self, detail=True):
        result = {k: getattr(self, k) for k in (
            'id', 'external_id', 'title', 'channel', 'language', 'operator_name', 'recording_url')}
        result.update(created_at=iso(self.created_at), message_count=len(self.messages))
        if detail:
            result['messages'] = self.messages
            result['source_metadata'] = self.source_metadata
        return result


class Checklist(db.Model):
    __tablename__ = 'checklists'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    name = db.Column(db.String(160), nullable=False)
    version = db.Column(db.String(40), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    criteria = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (db.UniqueConstraint('name', 'version', name='checklist_name_version'),)

    def to_dict(self):
        return {**{k: getattr(self, k) for k in (
            'id', 'name', 'version', 'description', 'is_demo', 'criteria')},
            'created_at': iso(self.created_at)}


class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    conversation_id = db.Column(db.String(36), db.ForeignKey('conversations.id'), nullable=False, index=True)
    checklist_id = db.Column(db.String(36), db.ForeignKey('checklists.id'), nullable=False)
    engine = db.Column(db.String(80), nullable=False)
    original_results = db.Column(db.JSON, nullable=False)
    results = db.Column(db.JSON, nullable=False)
    revision = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    __mapper_args__ = {'version_id_col': revision}

    def to_dict(self):
        from services.evaluation import summarize
        return {**{k: getattr(self, k) for k in (
            'id', 'conversation_id', 'checklist_id', 'engine', 'original_results', 'results', 'revision')},
            'created_at': iso(self.created_at), **summarize(self.results)}


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    evaluation_id = db.Column(db.String(36), db.ForeignKey('evaluations.id'), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    reviewer = db.Column(db.String(120), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    changes = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (db.UniqueConstraint('evaluation_id', 'revision', name='review_revision'),)

    def to_dict(self):
        return {**{k: getattr(self, k) for k in (
            'id', 'evaluation_id', 'revision', 'reviewer', 'comment', 'changes')},
            'created_at': iso(self.created_at)}
