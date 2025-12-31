"""Add Customer model and update Job FK

Revision ID: 002
Revises: 001
Create Date: 2024-12-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create customers table
    op.create_table('customers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('billing_address', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('credit_limit', sa.Float(), nullable=True),
        sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for common lookups
    op.create_index('ix_customers_name', 'customers', ['name'])
    op.create_index('ix_customers_email', 'customers', ['email'])
    op.create_index('ix_customers_active', 'customers', ['active'])

    # Add customer_id to jobs table (nullable for backward compatibility)
    op.add_column('jobs', sa.Column('customer_id', sa.Integer(), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_jobs_customer_id',
        'jobs', 'customers',
        ['customer_id'], ['id']
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint('fk_jobs_customer_id', 'jobs', type_='foreignkey')

    # Drop customer_id column from jobs
    op.drop_column('jobs', 'customer_id')

    # Drop indexes
    op.drop_index('ix_customers_active', 'customers')
    op.drop_index('ix_customers_email', 'customers')
    op.drop_index('ix_customers_name', 'customers')

    # Drop customers table
    op.drop_table('customers')
