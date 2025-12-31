"""Customer Spoke Service - manages customer entities."""

from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer


class CustomerService:
    """Service for customer management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_customer(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        billing_address: Optional[str] = None,
        active: bool = True,
        notes: Optional[str] = None,
        credit_limit: Optional[float] = None,
        payment_terms_days: int = 30,
        extra_data: Optional[dict] = None
    ) -> Customer:
        """
        Create a new customer.

        Args:
            name: Customer name (required)
            email: Email address
            phone: Phone number
            address: Shipping address
            billing_address: Billing address (defaults to address if not set)
            active: Whether customer is active
            notes: Internal notes
            credit_limit: Credit limit in dollars
            payment_terms_days: Payment terms (default 30 days)
            extra_data: Additional flexible data

        Returns:
            Created Customer entity
        """
        customer = Customer(
            name=name,
            email=email,
            phone=phone,
            address=address,
            billing_address=billing_address or address,
            active=active,
            notes=notes,
            credit_limit=credit_limit,
            payment_terms_days=payment_terms_days,
            extra_data=extra_data
        )

        self.db.add(customer)
        await self.db.flush()
        return customer

    async def get_customer(self, customer_id: int) -> Optional[Customer]:
        """Get customer by ID."""
        result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        return result.scalar_one_or_none()

    async def get_customer_by_name(self, name: str) -> Optional[Customer]:
        """Get customer by exact name match (case-insensitive)."""
        result = await self.db.execute(
            select(Customer).where(Customer.name.ilike(name))
        )
        return result.scalar_one_or_none()

    async def list_customers(self, active_only: bool = True) -> list[Customer]:
        """
        List all customers.

        Args:
            active_only: If True, only return active customers

        Returns:
            List of Customer entities
        """
        query = select(Customer)
        if active_only:
            query = query.where(Customer.active == True)
        query = query.order_by(Customer.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_customers(self, query: str) -> list[Customer]:
        """
        Search customers by name or email.

        Args:
            query: Search term

        Returns:
            List of matching Customer entities
        """
        search_pattern = f"%{query}%"
        result = await self.db.execute(
            select(Customer).where(
                or_(
                    Customer.name.ilike(search_pattern),
                    Customer.email.ilike(search_pattern)
                )
            ).order_by(Customer.name)
        )
        return list(result.scalars().all())

    async def update_customer(
        self,
        customer_id: int,
        **updates
    ) -> Optional[Customer]:
        """
        Update customer fields.

        Args:
            customer_id: Customer ID to update
            **updates: Fields to update

        Returns:
            Updated Customer or None if not found
        """
        customer = await self.get_customer(customer_id)
        if not customer:
            return None

        # Only update provided fields
        allowed_fields = {
            'name', 'email', 'phone', 'address', 'billing_address',
            'active', 'notes', 'credit_limit', 'payment_terms_days', 'extra_data'
        }

        for field, value in updates.items():
            if field in allowed_fields and value is not None:
                setattr(customer, field, value)

        await self.db.flush()
        return customer

    async def deactivate_customer(self, customer_id: int) -> Optional[Customer]:
        """Soft-delete a customer by setting active=False."""
        return await self.update_customer(customer_id, active=False)

    async def get_customer_job_count(self, customer_id: int) -> int:
        """Get count of jobs for a customer."""
        from models import Job
        result = await self.db.execute(
            select(Job).where(Job.customer_id == customer_id)
        )
        return len(list(result.scalars().all()))
