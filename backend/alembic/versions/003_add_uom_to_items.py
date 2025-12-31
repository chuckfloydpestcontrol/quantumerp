"""Add UOM field to items

Revision ID: 003
Revises: 002
Create Date: 2024-12-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add uom column to items table with default value
    op.add_column('items', sa.Column('uom', sa.String(length=20), nullable=False, server_default='each'))


def downgrade() -> None:
    # Remove uom column from items
    op.drop_column('items', 'uom')
