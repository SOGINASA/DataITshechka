"""Preserve DEV source timestamps and explicit timing reference.

Revision ID: 6b907f143a21
Revises: c2349e861e54
"""
from alembic import op
import sqlalchemy as sa

revision = '6b907f143a21'
down_revision = 'c2349e861e54'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('source_metadata', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_column('source_metadata')
