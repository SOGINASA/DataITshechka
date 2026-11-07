"""Separate criterion appeals from review decisions.

Revision ID: fc9387b1aa02
Revises: 6b907f143a21
"""
from alembic import op
import sqlalchemy as sa

revision = 'fc9387b1aa02'
down_revision = '6b907f143a21'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('evaluations', sa.Column('run_metadata', sa.JSON(), nullable=True))
    op.create_table('appeals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evaluation_id', sa.String(36), sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('criterion_id', sa.String(80), nullable=False),
        sa.Column('evaluation_revision', sa.Integer(), nullable=False),
        sa.Column('author', sa.String(120), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('disputed_result', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('decision', sa.String(20)),
        sa.Column('review_id', sa.String(36), sa.ForeignKey('reviews.id'), unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('open','resolved')", name='appeal_status'))
    op.create_index('ix_appeals_evaluation_id', 'appeals', ['evaluation_id'])


def downgrade():
    op.drop_index('ix_appeals_evaluation_id', table_name='appeals')
    op.drop_table('appeals')
    with op.batch_alter_table('evaluations') as batch_op:
        batch_op.drop_column('run_metadata')
