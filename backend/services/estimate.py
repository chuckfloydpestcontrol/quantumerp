"""Estimate service for CRUD, versioning, and status transitions."""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import (
    Estimate, EstimateLineItem, EstimateStatus, ATPStatus,
    Item, ApprovalRule
)
from schemas import (
    EstimateCreate, EstimateLineItemCreate, EstimateUpdate,
    EstimateLineItemUpdate
)
from services.pricing import PricingService
from services.atp import ATPService


class EstimateService:
    """Manages estimate lifecycle, versioning, and calculations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.pricing = PricingService(db)
        self.atp = ATPService(db)

    async def create_estimate(
        self,
        customer_id: int,
        line_items: Optional[list[EstimateLineItemCreate]] = None,
        valid_days: int = 30,
        requested_delivery_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> Estimate:
        """Create a new estimate with optional line items."""
        # Generate estimate number
        estimate_number = await self._generate_estimate_number()

        estimate = Estimate(
            estimate_number=estimate_number,
            version=1,
            customer_id=customer_id,
            status=EstimateStatus.DRAFT,
            valid_until=datetime.utcnow() + timedelta(days=valid_days),
            requested_delivery_date=requested_delivery_date,
            notes=notes,
            created_by=created_by
        )
        self.db.add(estimate)
        await self.db.flush()

        # Add line items if provided
        if line_items:
            for i, item_data in enumerate(line_items):
                await self.add_line_item(estimate.id, item_data, sort_order=i)

        # Recalculate totals
        await self._recalculate_totals(estimate)

        await self.db.flush()
        return estimate

    async def get_estimate(self, estimate_id: int) -> Optional[Estimate]:
        """Get estimate with all line items."""
        result = await self.db.execute(
            select(Estimate)
            .options(selectinload(Estimate.line_items))
            .options(selectinload(Estimate.customer))
            .where(Estimate.id == estimate_id)
        )
        return result.scalar_one_or_none()

    async def get_estimate_by_number(
        self,
        estimate_number: str,
        version: Optional[int] = None
    ) -> Optional[Estimate]:
        """Get estimate by number, optionally specific version."""
        query = select(Estimate).where(Estimate.estimate_number == estimate_number)
        if version:
            query = query.where(Estimate.version == version)
        else:
            # Get latest version
            query = query.order_by(Estimate.version.desc()).limit(1)

        result = await self.db.execute(
            query.options(selectinload(Estimate.line_items))
        )
        return result.scalar_one_or_none()

    async def list_estimates(
        self,
        customer_id: Optional[int] = None,
        status: Optional[EstimateStatus] = None,
        limit: int = 50
    ) -> list[Estimate]:
        """List estimates with optional filters."""
        query = select(Estimate).order_by(Estimate.created_at.desc())

        if customer_id:
            query = query.where(Estimate.customer_id == customer_id)
        if status:
            query = query.where(Estimate.status == status)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_line_item(
        self,
        estimate_id: int,
        item_data: EstimateLineItemCreate,
        sort_order: Optional[int] = None
    ) -> EstimateLineItem:
        """Add line item to estimate with price and ATP resolution."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only add lines to draft estimates")

        # Resolve pricing
        unit_price = item_data.unit_price
        list_price = None
        unit_cost = None
        price_book_id = None

        if item_data.item_id:
            unit_price, price_book_id = await self.pricing.resolve_price(
                item_data.item_id,
                estimate.customer_id,
                item_data.quantity
            )
            list_price = await self.pricing.get_list_price(item_data.item_id)

            # Get item cost
            item = await self.db.get(Item, item_data.item_id)
            if item:
                unit_cost = float(item.cost_per_unit)

        # Calculate line total (apply discount to unit_price for calculation only)
        discount_pct = item_data.discount_pct or 0
        effective_price = unit_price * (1 - discount_pct)
        line_total = effective_price * item_data.quantity

        # Check ATP
        atp_data = {}
        if item_data.item_id:
            atp_data = await self.atp.get_line_item_atp(
                item_data.item_id,
                item_data.quantity
            )

        # Determine sort order
        if sort_order is None:
            result = await self.db.execute(
                select(func.max(EstimateLineItem.sort_order))
                .where(EstimateLineItem.estimate_id == estimate_id)
            )
            max_order = result.scalar() or 0
            sort_order = max_order + 1

        line_item = EstimateLineItem(
            estimate_id=estimate_id,
            item_id=item_data.item_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=unit_price,
            list_price=list_price,
            unit_cost=unit_cost,
            discount_pct=discount_pct,
            line_total=line_total,
            sort_order=sort_order,
            notes=item_data.notes,
            **atp_data
        )
        self.db.add(line_item)
        await self.db.flush()

        # Recalculate totals
        await self._recalculate_totals(estimate)

        return line_item

    async def update_line_item(
        self,
        line_item_id: int,
        updates: EstimateLineItemUpdate
    ) -> EstimateLineItem:
        """Update line item and recalculate."""
        line_item = await self.db.get(EstimateLineItem, line_item_id)
        if not line_item:
            raise ValueError(f"Line item {line_item_id} not found")

        estimate = await self.get_estimate(line_item.estimate_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only update lines on draft estimates")

        # Apply updates
        if updates.description is not None:
            line_item.description = updates.description
        if updates.quantity is not None:
            line_item.quantity = updates.quantity
        if updates.unit_price is not None:
            line_item.unit_price = updates.unit_price
        if updates.discount_pct is not None:
            line_item.discount_pct = updates.discount_pct
        if updates.notes is not None:
            line_item.notes = updates.notes

        # Recalculate line total
        effective_price = line_item.unit_price * (1 - line_item.discount_pct)
        line_item.line_total = effective_price * line_item.quantity

        # Re-check ATP if quantity changed
        if updates.quantity is not None and line_item.item_id:
            atp_data = await self.atp.get_line_item_atp(
                line_item.item_id,
                line_item.quantity
            )
            line_item.atp_status = atp_data["atp_status"]
            line_item.atp_available_qty = atp_data["atp_available_qty"]
            line_item.atp_shortage_qty = atp_data["atp_shortage_qty"]
            line_item.atp_lead_time_days = atp_data["atp_lead_time_days"]

        await self.db.flush()

        # Recalculate estimate totals
        await self._recalculate_totals(estimate)

        return line_item

    async def delete_line_item(self, line_item_id: int) -> None:
        """Delete line item."""
        line_item = await self.db.get(EstimateLineItem, line_item_id)
        if not line_item:
            return

        estimate = await self.get_estimate(line_item.estimate_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only delete lines from draft estimates")

        await self.db.delete(line_item)
        await self.db.flush()

        # Recalculate totals
        await self._recalculate_totals(estimate)

    async def submit_for_approval(self, estimate_id: int) -> Estimate:
        """Submit estimate for approval, checking rules."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only submit draft estimates")

        if not estimate.line_items:
            raise ValueError("Cannot submit estimate with no line items")

        # Check delivery feasibility - block if impossible
        if not estimate.delivery_feasible:
            raise ValueError(
                f"Cannot submit: requested delivery date cannot be met. "
                f"Earliest possible: {estimate.earliest_delivery_date}"
            )

        # Check approval rules
        triggered_rules = await self._check_approval_rules(estimate)

        if triggered_rules:
            estimate.status = EstimateStatus.PENDING_APPROVAL
            estimate.pending_approvers = [r.approver_role for r in triggered_rules]
        else:
            estimate.status = EstimateStatus.APPROVED

        await self.db.flush()
        return estimate

    async def approve(
        self,
        estimate_id: int,
        approved_by: int,
        comment: Optional[str] = None
    ) -> Estimate:
        """Approve pending estimate."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.PENDING_APPROVAL:
            raise ValueError("Can only approve pending estimates")

        estimate.status = EstimateStatus.APPROVED
        estimate.approved_by = approved_by
        estimate.approved_at = datetime.utcnow()
        estimate.pending_approvers = None

        if comment:
            estimate.notes = f"{estimate.notes or ''}\n\nApproval: {comment}".strip()

        await self.db.flush()
        return estimate

    async def reject(
        self,
        estimate_id: int,
        reason: str
    ) -> Estimate:
        """Reject pending estimate."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.PENDING_APPROVAL:
            raise ValueError("Can only reject pending estimates")

        estimate.status = EstimateStatus.REJECTED
        estimate.rejection_reason = reason
        estimate.pending_approvers = None

        await self.db.flush()
        return estimate

    async def send_to_customer(self, estimate_id: int) -> Estimate:
        """Mark estimate as sent to customer."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.APPROVED:
            raise ValueError("Can only send approved estimates")

        estimate.status = EstimateStatus.SENT
        estimate.sent_at = datetime.utcnow()

        await self.db.flush()
        return estimate

    async def accept(self, estimate_id: int) -> Estimate:
        """Mark estimate as accepted by customer."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.SENT:
            raise ValueError("Can only accept sent estimates")

        estimate.status = EstimateStatus.ACCEPTED
        estimate.accepted_at = datetime.utcnow()

        await self.db.flush()
        return estimate

    async def create_revision(self, estimate_id: int) -> Estimate:
        """Create new version of estimate."""
        original = await self.get_estimate(estimate_id)
        if not original:
            raise ValueError(f"Estimate {estimate_id} not found")

        if original.status not in [EstimateStatus.SENT, EstimateStatus.REJECTED]:
            raise ValueError("Can only revise sent or rejected estimates")

        # Create new version
        new_estimate = Estimate(
            estimate_number=original.estimate_number,
            version=original.version + 1,
            parent_estimate_id=original.id,
            customer_id=original.customer_id,
            status=EstimateStatus.DRAFT,
            currency_code=original.currency_code,
            price_book_id=original.price_book_id,
            valid_until=datetime.utcnow() + timedelta(days=30),
            requested_delivery_date=original.requested_delivery_date,
            notes=original.notes
        )
        self.db.add(new_estimate)
        await self.db.flush()

        # Clone line items
        for line in original.line_items:
            new_line = EstimateLineItem(
                estimate_id=new_estimate.id,
                item_id=line.item_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                list_price=line.list_price,
                unit_cost=line.unit_cost,
                discount_pct=line.discount_pct,
                line_total=line.line_total,
                sort_order=line.sort_order,
                notes=line.notes
            )
            self.db.add(new_line)

        # Mark original as superseded
        original.superseded_by_id = new_estimate.id

        await self.db.flush()

        # Recalculate (re-checks ATP)
        await self._recalculate_totals(new_estimate)

        return new_estimate

    async def get_version_history(self, estimate_number: str) -> list[dict]:
        """Get version history for an estimate."""
        result = await self.db.execute(
            select(Estimate)
            .where(Estimate.estimate_number == estimate_number)
            .order_by(Estimate.version.desc())
        )
        estimates = list(result.scalars().all())

        history = []
        for est in estimates:
            history.append({
                "version": est.version,
                "status": est.status.value,
                "created_at": est.created_at.isoformat(),
                "rejection_reason": est.rejection_reason
            })
        return history

    async def _generate_estimate_number(self) -> str:
        """Generate unique estimate number."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"E-{today}"

        result = await self.db.execute(
            select(func.count(Estimate.id))
            .where(Estimate.estimate_number.like(f"{prefix}%"))
        )
        count = result.scalar() or 0

        return f"{prefix}-{count + 1:04d}"

    async def _recalculate_totals(self, estimate: Estimate) -> None:
        """Recalculate estimate totals and delivery date."""
        # Reload line items
        result = await self.db.execute(
            select(EstimateLineItem)
            .where(EstimateLineItem.estimate_id == estimate.id)
        )
        line_items = list(result.scalars().all())

        # Calculate subtotal
        subtotal = sum(line.line_total for line in line_items)
        estimate.subtotal = subtotal

        # Calculate tax (simplified - 8% flat rate for now)
        estimate.tax_amount = subtotal * 0.08
        estimate.total_amount = subtotal + estimate.tax_amount

        # Calculate margin
        total_cost = sum(
            (line.unit_cost or 0) * line.quantity
            for line in line_items
        )
        if subtotal > 0:
            estimate.margin_percent = (subtotal - total_cost) / subtotal
        else:
            estimate.margin_percent = 0

        # Calculate earliest delivery
        line_data = [
            {"id": line.id, "item_id": line.item_id, "quantity": line.quantity}
            for line in line_items if line.item_id
        ]
        earliest, feasible, _ = await self.atp.calculate_earliest_delivery(
            line_data,
            estimate.requested_delivery_date
        )
        estimate.earliest_delivery_date = earliest
        estimate.delivery_feasible = feasible

        await self.db.flush()

    async def _check_approval_rules(self, estimate: Estimate) -> list[ApprovalRule]:
        """Check which approval rules are triggered."""
        result = await self.db.execute(
            select(ApprovalRule)
            .where(ApprovalRule.active == True)
            .order_by(ApprovalRule.priority)
        )
        rules = list(result.scalars().all())

        triggered = []
        for rule in rules:
            if self._rule_applies(rule, estimate):
                triggered.append(rule)

        return triggered

    def _rule_applies(self, rule: ApprovalRule, estimate: Estimate) -> bool:
        """Check if a specific rule applies to the estimate."""
        if rule.condition_type == "margin_below":
            return (estimate.margin_percent or 0) < (rule.threshold_value or 0)
        elif rule.condition_type == "total_above":
            return estimate.total_amount > (rule.threshold_value or 0)
        elif rule.condition_type == "payment_terms_above":
            # Would check customer payment terms
            return False
        return False
