"""Available to Promise (ATP) service for inventory and delivery checks."""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from models import Item, ATPStatus
from schemas import ATPWarning


class ATPService:
    """Checks inventory availability and calculates delivery feasibility."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_availability(
        self,
        item_id: int,
        quantity_required: float
    ) -> dict:
        """
        Check availability of an item.

        Returns:
            Dict with atp_status, available_qty, shortage_qty, lead_time_days
        """
        item = await self.db.get(Item, item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")

        available = float(item.quantity_on_hand)
        required = float(quantity_required)

        if available >= required:
            return {
                "atp_status": ATPStatus.AVAILABLE,
                "atp_available_qty": available,
                "atp_shortage_qty": 0,
                "atp_lead_time_days": 0
            }
        elif available > 0:
            return {
                "atp_status": ATPStatus.PARTIAL,
                "atp_available_qty": available,
                "atp_shortage_qty": required - available,
                "atp_lead_time_days": item.vendor_lead_time_days
            }
        else:
            return {
                "atp_status": ATPStatus.BACKORDER,
                "atp_available_qty": 0,
                "atp_shortage_qty": required,
                "atp_lead_time_days": item.vendor_lead_time_days
            }

    async def calculate_earliest_delivery(
        self,
        line_items: list[dict],
        requested_date: Optional[datetime] = None
    ) -> tuple[datetime, bool, list[ATPWarning]]:
        """
        Calculate earliest possible delivery date based on line items.

        Args:
            line_items: List of dicts with item_id and quantity
            requested_date: Customer's requested delivery date

        Returns:
            Tuple of (earliest_date, is_feasible, warnings)
        """
        today = datetime.utcnow().date()
        max_lead_time = 0
        warnings = []

        for line in line_items:
            item_id = line.get("item_id")
            if not item_id:
                continue

            quantity = line.get("quantity", 1)
            atp = await self.check_availability(item_id, quantity)

            if atp["atp_status"] != ATPStatus.AVAILABLE:
                item = await self.db.get(Item, item_id)
                lead_time = atp["atp_lead_time_days"] or 0
                max_lead_time = max(max_lead_time, lead_time)

                warnings.append(ATPWarning(
                    line_item_id=line.get("id", 0),
                    item_name=item.name if item else f"Item {item_id}",
                    required_qty=quantity,
                    available_qty=atp["atp_available_qty"],
                    shortage_qty=atp["atp_shortage_qty"],
                    lead_time_days=lead_time,
                    message=self._format_warning(atp, item.name if item else "Item")
                ))

        # Add processing time (2 days minimum)
        processing_days = 2
        earliest_date = datetime.combine(
            today + timedelta(days=max_lead_time + processing_days),
            datetime.min.time()
        )

        is_feasible = True
        if requested_date:
            is_feasible = earliest_date.date() <= requested_date.date()

        return earliest_date, is_feasible, warnings

    def _format_warning(self, atp: dict, item_name: str) -> str:
        """Format ATP warning message."""
        status = atp["atp_status"]
        shortage = atp["atp_shortage_qty"]
        lead_time = atp["atp_lead_time_days"]

        if status == ATPStatus.PARTIAL:
            return f"{shortage:.0f} units of {item_name} backordered (+{lead_time} days)"
        elif status == ATPStatus.BACKORDER:
            return f"{item_name} not in stock. Lead time: {lead_time} days"
        return ""

    async def get_line_item_atp(
        self,
        item_id: int,
        quantity: float
    ) -> dict:
        """Get ATP data for a single line item."""
        atp = await self.check_availability(item_id, quantity)
        return {
            "atp_status": atp["atp_status"],
            "atp_available_qty": atp["atp_available_qty"],
            "atp_shortage_qty": atp["atp_shortage_qty"],
            "atp_lead_time_days": atp["atp_lead_time_days"]
        }
