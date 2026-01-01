"""add_estimating_module

Revision ID: 004
Revises: 003
Create Date: 2026-01-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enum types
estimate_status_enum = ENUM(
    'draft', 'pending_approval', 'approved', 'sent',
    'accepted', 'rejected', 'expired',
    name='estimate_status',
    create_type=False
)

atp_status_enum = ENUM(
    'available', 'partial', 'backorder',
    name='atp_status',
    create_type=False
)


def upgrade() -> None:
    # Create enum types first
    estimate_status_enum.create(op.get_bind(), checkfirst=True)
    atp_status_enum.create(op.get_bind(), checkfirst=True)

    # Price Books table
    op.create_table(
        'price_books',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('customer_segment', sa.String(50), nullable=True),
        sa.Column('currency_code', sa.String(3), default='USD'),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Price Book Entries table
    op.create_table(
        'price_book_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('price_book_id', sa.Integer(), sa.ForeignKey('price_books.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=False),
        sa.Column('min_qty', sa.Numeric(12, 4), default=1),
        sa.Column('max_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_price_book_entry', 'price_book_entries', ['price_book_id', 'item_id', 'min_qty'])
    op.create_index('ix_price_book_entries_item_id', 'price_book_entries', ['item_id'])

    # Approval Rules table
    op.create_table(
        'approval_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('condition_type', sa.String(50), nullable=False),
        sa.Column('threshold_value', sa.Numeric(12, 4), nullable=True),
        sa.Column('approver_role', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Estimates table (header)
    op.create_table(
        'estimates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_number', sa.String(50), nullable=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('parent_estimate_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=True),
        sa.Column('superseded_by_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('status', estimate_status_enum, default='draft'),
        sa.Column('currency_code', sa.String(3), default='USD'),
        sa.Column('exchange_rate', sa.Numeric(10, 6), default=1.0),
        sa.Column('price_book_id', sa.Integer(), sa.ForeignKey('price_books.id'), nullable=True),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('subtotal', sa.Numeric(12, 2), default=0),
        sa.Column('tax_amount', sa.Numeric(12, 2), default=0),
        sa.Column('total_amount', sa.Numeric(12, 2), default=0),
        sa.Column('margin_percent', sa.Numeric(5, 4), nullable=True),
        sa.Column('requested_delivery_date', sa.Date(), nullable=True),
        sa.Column('earliest_delivery_date', sa.Date(), nullable=True),
        sa.Column('delivery_feasible', sa.Boolean(), default=True),
        sa.Column('pending_approvers', JSONB, nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_unique_constraint('uq_estimate_version', 'estimates', ['estimate_number', 'version'])

    # Estimate Line Items table
    op.create_table(
        'estimate_line_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_id', sa.Integer(), sa.ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 4), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('list_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('unit_cost', sa.Numeric(12, 4), nullable=True),
        sa.Column('discount_pct', sa.Numeric(5, 4), default=0),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(12, 2), default=0),
        sa.Column('atp_status', atp_status_enum, default='available'),
        sa.Column('atp_available_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('atp_shortage_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('atp_lead_time_days', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index('ix_estimates_customer_id', 'estimates', ['customer_id'])
    op.create_index('ix_estimates_status', 'estimates', ['status'])
    op.create_index('ix_estimates_estimate_number', 'estimates', ['estimate_number'])
    op.create_index('ix_estimate_line_items_estimate_id', 'estimate_line_items', ['estimate_id'])


def downgrade() -> None:
    op.drop_index('ix_estimate_line_items_estimate_id')
    op.drop_index('ix_estimates_estimate_number')
    op.drop_index('ix_estimates_status')
    op.drop_index('ix_estimates_customer_id')
    op.drop_index('ix_price_book_entries_item_id')
    op.drop_table('estimate_line_items')
    op.drop_table('estimates')
    op.drop_table('approval_rules')
    op.drop_table('price_book_entries')
    op.drop_table('price_books')
    atp_status_enum.drop(op.get_bind(), checkfirst=True)
    estimate_status_enum.drop(op.get_bind(), checkfirst=True)
