"""Pricing service for price book resolution and tiered pricing."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PriceBook, PriceBookEntry, Item, Customer


class PricingService:
    """Resolves prices from price books with tiered/volume support."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_price(
        self,
        item_id: int,
        customer_id: int,
        quantity: float = 1
    ) -> tuple[float, Optional[int]]:
        """
        Resolve price for an item based on customer and quantity.

        Returns:
            Tuple of (unit_price, price_book_id used)

        Resolution order:
        1. Customer-specific price book
        2. Customer segment price book
        3. Default price book
        4. Item cost_per_unit as fallback
        """
        # 1. Check customer-specific price book
        customer_book = await self._get_customer_price_book(customer_id)
        if customer_book:
            price = await self._get_tiered_price(customer_book.id, item_id, quantity)
            if price is not None:
                return price, customer_book.id

        # 2. Check segment price book
        customer = await self.db.get(Customer, customer_id)
        if customer and customer.extra_data and customer.extra_data.get("segment"):
            segment = customer.extra_data["segment"]
            segment_book = await self._get_segment_price_book(segment)
            if segment_book:
                price = await self._get_tiered_price(segment_book.id, item_id, quantity)
                if price is not None:
                    return price, segment_book.id

        # 3. Check default price book
        default_book = await self._get_default_price_book()
        if default_book:
            price = await self._get_tiered_price(default_book.id, item_id, quantity)
            if price is not None:
                return price, default_book.id

        # 4. Fallback to item cost
        item = await self.db.get(Item, item_id)
        if item:
            return float(item.cost_per_unit), None

        raise ValueError(f"Item {item_id} not found")

    async def _get_customer_price_book(self, customer_id: int) -> Optional[PriceBook]:
        """Get active price book for specific customer."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.customer_id == customer_id)
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_segment_price_book(self, segment: str) -> Optional[PriceBook]:
        """Get active price book for customer segment."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.customer_segment == segment)
            .where(PriceBook.customer_id.is_(None))
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_default_price_book(self) -> Optional[PriceBook]:
        """Get default price book."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.is_default == True)
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_tiered_price(
        self,
        price_book_id: int,
        item_id: int,
        quantity: float
    ) -> Optional[float]:
        """Get price from price book applying volume tier."""
        # Find the entry where quantity falls within min/max range
        result = await self.db.execute(
            select(PriceBookEntry)
            .where(PriceBookEntry.price_book_id == price_book_id)
            .where(PriceBookEntry.item_id == item_id)
            .where(PriceBookEntry.min_qty <= quantity)
            .where(
                (PriceBookEntry.max_qty.is_(None)) |
                (PriceBookEntry.max_qty >= quantity)
            )
            .order_by(PriceBookEntry.min_qty.desc())
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        return float(entry.unit_price) if entry else None

    async def get_list_price(self, item_id: int) -> Optional[float]:
        """Get standard list price from default price book."""
        default_book = await self._get_default_price_book()
        if default_book:
            return await self._get_tiered_price(default_book.id, item_id, 1)
        return None

    async def create_price_book(
        self,
        name: str,
        is_default: bool = False,
        customer_id: Optional[int] = None,
        customer_segment: Optional[str] = None,
        currency_code: str = "USD"
    ) -> PriceBook:
        """Create a new price book."""
        # If setting as default, unset other defaults
        if is_default:
            result = await self.db.execute(
                select(PriceBook).where(PriceBook.is_default == True)
            )
            for book in result.scalars():
                book.is_default = False

        price_book = PriceBook(
            name=name,
            is_default=is_default,
            customer_id=customer_id,
            customer_segment=customer_segment,
            currency_code=currency_code,
            active=True
        )
        self.db.add(price_book)
        await self.db.flush()
        return price_book

    async def add_price_book_entry(
        self,
        price_book_id: int,
        item_id: int,
        unit_price: float,
        min_qty: float = 1,
        max_qty: Optional[float] = None
    ) -> PriceBookEntry:
        """Add entry to price book."""
        entry = PriceBookEntry(
            price_book_id=price_book_id,
            item_id=item_id,
            unit_price=unit_price,
            min_qty=min_qty,
            max_qty=max_qty
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
