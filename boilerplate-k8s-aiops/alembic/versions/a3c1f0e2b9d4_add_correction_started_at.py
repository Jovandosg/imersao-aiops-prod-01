"""add correction_started_at

Revision ID: a3c1f0e2b9d4
Revises: db7526387914
Create Date: 2026-10-18 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3c1f0e2b9d4'
down_revision: Union[str, Sequence[str], None] = 'db7526387914'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reports', sa.Column('correction_started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reports', 'correction_started_at')
