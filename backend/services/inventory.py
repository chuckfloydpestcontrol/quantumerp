"""Inventory Spoke Service - manages stock levels and vendor information."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Item
from schemas import StockCheckResult


class InventoryService:
    """Service for inventory management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_stock(
        self,
        item_id: int,
        quantity_required: int
    ) -> StockCheckResult:
        """
        Check stock availability for an item.

        Returns availability status, shortage amount, and estimated restock date.
        """
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Item with ID {item_id} not found")

        available = item.quantity_on_hand >= quantity_required
        shortage = max(0, quantity_required - item.quantity_on_hand)

        # Calculate restock date if there's a shortage
        restock_date = None
        if shortage > 0:
            restock_date = datetime.utcnow() + timedelta(
                days=item.vendor_lead_time_days
            )

        return StockCheckResult(
            item_id=item.id,
            item_name=item.name,
            available=available,
            quantity_on_hand=item.quantity_on_hand,
            quantity_required=quantity_required,
            shortage=shortage,
            restock_date=restock_date,
            vendor_lead_time_days=item.vendor_lead_time_days,
        )

    async def check_stock_by_sku(
        self,
        sku: str,
        quantity_required: int
    ) -> StockCheckResult:
        """Check stock by SKU."""
        result = await self.db.execute(
            select(Item).where(Item.sku == sku)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Item with SKU '{sku}' not found")

        return await self.check_stock(item.id, quantity_required)

    async def check_multiple_items(
        self,
        items: list[dict]
    ) -> list[StockCheckResult]:
        """
        Check stock for multiple items (BOM check).

        Args:
            items: List of dicts with 'item_id' and 'quantity' keys

        Returns:
            List of StockCheckResult for each item
        """
        results = []
        for item_req in items:
            result = await self.check_stock(
                item_id=item_req["item_id"],
                quantity_required=item_req["quantity"]
            )
            results.append(result)
        return results

    async def get_item_by_name(self, name: str) -> Optional[Item]:
        """Search for item by name (partial match)."""
        result = await self.db.execute(
            select(Item).where(Item.name.ilike(f"%{name}%"))
        )
        return result.scalar_one_or_none()

    async def get_item_by_category(
        self,
        category: str
    ) -> list[Item]:
        """Get all items in a category."""
        result = await self.db.execute(
            select(Item).where(Item.category == category)
        )
        return list(result.scalars().all())

    async def get_low_stock_items(self) -> list[Item]:
        """Get items below reorder point."""
        result = await self.db.execute(
            select(Item).where(Item.quantity_on_hand < Item.reorder_point)
        )
        return list(result.scalars().all())

    async def reserve_stock(
        self,
        item_id: int,
        quantity: int
    ) -> bool:
        """
        Reserve stock for a job (decrements quantity_on_hand).

        Returns True if successful, False if insufficient stock.
        """
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Item with ID {item_id} not found")

        if item.quantity_on_hand < quantity:
            return False

        item.quantity_on_hand -= quantity
        await self.db.flush()
        return True

    async def release_stock(
        self,
        item_id: int,
        quantity: int
    ) -> None:
        """Release reserved stock back to inventory."""
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Item with ID {item_id} not found")

        item.quantity_on_hand += quantity
        await self.db.flush()

    async def create_item(
        self,
        name: str,
        sku: str,
        cost_per_unit: float,
        quantity_on_hand: int = 0,
        **kwargs
    ) -> Item:
        """Create a new inventory item."""
        item = Item(
            name=name,
            sku=sku,
            cost_per_unit=cost_per_unit,
            quantity_on_hand=quantity_on_hand,
            **kwargs
        )
        self.db.add(item)
        await self.db.flush()
        return item
