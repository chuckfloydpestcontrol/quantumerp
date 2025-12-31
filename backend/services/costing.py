"""Costing Spoke Service - manages quote calculations and pricing."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Item, Machine
from schemas import CostCalculation


class CostingService:
    """Service for cost estimation and quote calculation."""

    # Default overhead rates
    DEFAULT_OVERHEAD_RATE = 0.15  # 15% of direct costs
    DEFAULT_MARGIN = 0.20  # 20% profit margin

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_quote(
        self,
        bom: list[dict],
        labor_hours: float,
        machine_id: Optional[int] = None,
        margin: float = DEFAULT_MARGIN,
        expedited: bool = False
    ) -> CostCalculation:
        """
        Calculate a quote based on BOM and labor requirements.

        Args:
            bom: List of dicts with 'item_id' and 'quantity' keys
            labor_hours: Estimated labor hours
            machine_id: Optional machine ID for hourly rate lookup
            margin: Profit margin (0.0 to 1.0)
            expedited: If True, apply expedited pricing premium

        Returns:
            CostCalculation with full breakdown
        """
        # Calculate material cost
        material_cost = await self._calculate_material_cost(bom)

        # Calculate labor cost
        labor_cost = await self._calculate_labor_cost(
            labor_hours, machine_id, expedited
        )

        # Calculate overhead
        direct_costs = material_cost + labor_cost
        overhead_cost = direct_costs * self.DEFAULT_OVERHEAD_RATE

        # Apply expedited premium if requested
        if expedited:
            overhead_cost *= 1.25  # 25% premium for expedited

        # Calculate margin and total
        subtotal = direct_costs + overhead_cost
        margin_amount = subtotal * margin
        total_price = subtotal + margin_amount

        breakdown = {
            "materials": await self._get_material_breakdown(bom),
            "labor_hours": labor_hours,
            "labor_rate": await self._get_labor_rate(machine_id),
            "overhead_rate": self.DEFAULT_OVERHEAD_RATE,
            "margin_rate": margin,
            "expedited": expedited,
            "expedited_premium": 0.25 if expedited else 0,
        }

        return CostCalculation(
            material_cost=round(material_cost, 2),
            labor_cost=round(labor_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            margin_amount=round(margin_amount, 2),
            total_price=round(total_price, 2),
            breakdown=breakdown
        )

    async def _calculate_material_cost(self, bom: list[dict]) -> float:
        """Calculate total material cost from BOM."""
        total = 0.0

        for item_req in bom:
            item_id = item_req.get("item_id")
            quantity = item_req.get("quantity", 1)

            result = await self.db.execute(
                select(Item).where(Item.id == item_id)
            )
            item = result.scalar_one_or_none()

            if item:
                total += item.cost_per_unit * quantity

        return total

    async def _calculate_labor_cost(
        self,
        hours: float,
        machine_id: Optional[int],
        expedited: bool
    ) -> float:
        """Calculate labor cost based on machine hourly rate."""
        rate = await self._get_labor_rate(machine_id)

        if expedited:
            rate *= 1.5  # Overtime rate

        return hours * rate

    async def _get_labor_rate(self, machine_id: Optional[int]) -> float:
        """Get hourly rate for labor calculation."""
        if machine_id:
            result = await self.db.execute(
                select(Machine).where(Machine.id == machine_id)
            )
            machine = result.scalar_one_or_none()
            if machine:
                return machine.hourly_rate

        # Default rate if no machine specified
        return 75.0

    async def _get_material_breakdown(self, bom: list[dict]) -> list[dict]:
        """Get detailed material breakdown."""
        breakdown = []

        for item_req in bom:
            item_id = item_req.get("item_id")
            quantity = item_req.get("quantity", 1)

            result = await self.db.execute(
                select(Item).where(Item.id == item_id)
            )
            item = result.scalar_one_or_none()

            if item:
                breakdown.append({
                    "item_id": item.id,
                    "name": item.name,
                    "sku": item.sku,
                    "quantity": quantity,
                    "unit_cost": item.cost_per_unit,
                    "total_cost": round(item.cost_per_unit * quantity, 2)
                })

        return breakdown

    async def calculate_quote_options(
        self,
        bom: list[dict],
        labor_hours: float,
        machine_id: Optional[int] = None,
        requested_date: Optional[datetime] = None,
        current_lead_time_days: int = 7
    ) -> dict:
        """
        Calculate three quote options: Fastest, Cheapest, Balanced.

        This is the core parallel quoting output synthesizer.

        Args:
            bom: Bill of materials
            labor_hours: Base labor hours
            machine_id: Machine ID for rate lookup
            requested_date: Customer's requested delivery date
            current_lead_time_days: Standard lead time based on scheduling

        Returns:
            Dict with three quote options
        """
        now = datetime.utcnow()
        standard_date = now + timedelta(days=current_lead_time_days)

        # Fastest option: expedited, minimum margin
        fastest = await self.calculate_quote(
            bom=bom,
            labor_hours=labor_hours * 0.85,  # Assume 15% time reduction
            machine_id=machine_id,
            margin=0.15,  # Lower margin for speed
            expedited=True
        )
        fastest_date = now + timedelta(days=max(2, current_lead_time_days // 2))

        # Cheapest option: standard timing, maximize efficiency
        cheapest = await self.calculate_quote(
            bom=bom,
            labor_hours=labor_hours * 1.1,  # Allow 10% more time for efficiency
            machine_id=machine_id,
            margin=0.15,  # Lower margin
            expedited=False
        )
        cheapest_date = now + timedelta(days=current_lead_time_days + 3)

        # Balanced option: standard pricing and timing
        balanced = await self.calculate_quote(
            bom=bom,
            labor_hours=labor_hours,
            machine_id=machine_id,
            margin=self.DEFAULT_MARGIN,
            expedited=False
        )

        return {
            "fastest": {
                "quote_type": "fastest",
                "total_price": fastest.total_price,
                "estimated_delivery_date": fastest_date.isoformat(),
                "lead_time_days": (fastest_date - now).days,
                "material_cost": fastest.material_cost,
                "labor_cost": fastest.labor_cost,
                "overhead_cost": fastest.overhead_cost,
                "details": "Expedited production with overtime labor. Priority scheduling.",
                "highlights": [
                    "Fastest delivery option",
                    f"Ready in {(fastest_date - now).days} days",
                    "Priority machine scheduling"
                ]
            },
            "cheapest": {
                "quote_type": "cheapest",
                "total_price": cheapest.total_price,
                "estimated_delivery_date": cheapest_date.isoformat(),
                "lead_time_days": (cheapest_date - now).days,
                "material_cost": cheapest.material_cost,
                "labor_cost": cheapest.labor_cost,
                "overhead_cost": cheapest.overhead_cost,
                "details": "Standard production schedule with optimized efficiency.",
                "highlights": [
                    "Most economical option",
                    f"Delivery in {(cheapest_date - now).days} days",
                    "Standard scheduling"
                ]
            },
            "balanced": {
                "quote_type": "balanced",
                "total_price": balanced.total_price,
                "estimated_delivery_date": standard_date.isoformat(),
                "lead_time_days": (standard_date - now).days,
                "material_cost": balanced.material_cost,
                "labor_cost": balanced.labor_cost,
                "overhead_cost": balanced.overhead_cost,
                "details": "Optimal balance of cost and delivery time.",
                "highlights": [
                    "Recommended option",
                    f"Delivery in {(standard_date - now).days} days",
                    "Best value"
                ]
            }
        }
