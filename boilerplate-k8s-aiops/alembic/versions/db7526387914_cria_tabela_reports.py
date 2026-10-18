"""cria tabela reports

Revision ID: db7526387914
Revises: 
Create Date: 2026-10-18 16:20:15.693191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'db7526387914'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('markdown', sa.Text(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('event_uids', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('severity', sa.Text(), nullable=True),
    sa.Column('namespace', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('corrected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('correction_result', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('EM_ANALISE', 'COMPLETO', 'INCOMPLETO', 'CORRIGINDO', 'CORRIGIDO', 'FALHA_CORRECAO')", name='ck_reports_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reports_event_uids', 'reports', ['event_uids'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_reports_event_uids', table_name='reports', postgresql_using='gin')
    op.drop_table('reports')
