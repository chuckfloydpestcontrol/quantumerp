"""Job Spoke Service - manages job lifecycle and orchestration."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Job, JobStatus, Quote, QuoteType, ProductionSlot


class JobService:
    """Service for job management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        customer_name: str,
        description: Optional[str] = None,
        customer_email: Optional[str] = None,
        priority: int = 5,
        requested_delivery_date: Optional[datetime] = None,
        metadata: Optional[dict] = None
    ) -> Job:
        """
        Create a new job in DRAFT status.

        This supports Dynamic Entry - no quote or PO required.
        """
        job_number = await self._generate_job_number()

        job = Job(
            job_number=job_number,
            customer_name=customer_name,
            customer_email=customer_email,
            description=description,
            status=JobStatus.DRAFT,
            priority=priority,
            requested_delivery_date=requested_delivery_date,
            metadata=metadata
        )

        self.db.add(job)
        await self.db.flush()
        return job

    async def create_scheduled_job(
        self,
        customer_name: str,
        description: Optional[str] = None,
        customer_email: Optional[str] = None,
        priority: int = 5,
        financial_hold_reason: Optional[str] = "Awaiting PO",
        metadata: Optional[dict] = None
    ) -> Job:
        """
        Create a job directly in SCHEDULED status with financial hold.

        This is the "Schedule-First" Dynamic Entry workflow.
        """
        job_number = await self._generate_job_number()

        job = Job(
            job_number=job_number,
            customer_name=customer_name,
            customer_email=customer_email,
            description=description,
            status=JobStatus.SCHEDULED,
            priority=priority,
            financial_hold=True,
            financial_hold_reason=financial_hold_reason,
            metadata=metadata
        )

        self.db.add(job)
        await self.db.flush()
        return job

    async def _generate_job_number(self) -> str:
        """Generate a unique job number."""
        # Get count for today
        today = datetime.utcnow().date()
        prefix = today.strftime("%Y%m%d")

        result = await self.db.execute(
            select(func.count(Job.id)).where(
                Job.job_number.like(f"{prefix}%")
            )
        )
        count = result.scalar() or 0

        return f"{prefix}-{count + 1:04d}"

    async def get_job(self, job_id: int) -> Optional[Job]:
        """Get a job by ID with related data."""
        result = await self.db.execute(
            select(Job)
            .options(selectinload(Job.production_slots))
            .options(selectinload(Job.quote))
            .where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job_by_number(self, job_number: str) -> Optional[Job]:
        """Get a job by job number."""
        result = await self.db.execute(
            select(Job)
            .options(selectinload(Job.production_slots))
            .options(selectinload(Job.quote))
            .where(Job.job_number == job_number)
        )
        return result.scalar_one_or_none()

    async def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        clear_financial_hold: bool = False
    ) -> Job:
        """Update job status."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = status

        if clear_financial_hold:
            job.financial_hold = False
            job.financial_hold_reason = None

        await self.db.flush()
        return job

    async def attach_quote(
        self,
        job_id: int,
        quote_type: QuoteType,
        total_price: float,
        material_cost: float,
        labor_cost: float,
        overhead_cost: float,
        margin_percentage: float,
        estimated_delivery_date: datetime,
        lead_time_days: int,
        analysis_data: Optional[dict] = None
    ) -> Quote:
        """Attach a quote to a job."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        quote_number = f"Q-{job.job_number}"

        quote = Quote(
            quote_number=quote_number,
            job_id=job_id,
            quote_type=quote_type,
            total_price=total_price,
            material_cost=material_cost,
            labor_cost=labor_cost,
            overhead_cost=overhead_cost,
            margin_percentage=margin_percentage,
            estimated_delivery_date=estimated_delivery_date,
            lead_time_days=lead_time_days,
            analysis_data=analysis_data
        )

        self.db.add(quote)
        await self.db.flush()

        # Update job with quote reference and status
        job.quote_id = quote.id
        job.estimated_delivery_date = estimated_delivery_date
        job.status = JobStatus.QUOTED

        await self.db.flush()
        return quote

    async def accept_quote(self, job_id: int) -> Job:
        """Accept a quote and move job to SCHEDULED status."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if not job.quote:
            raise ValueError(f"Job {job_id} has no quote attached")

        # Mark quote as accepted
        result = await self.db.execute(
            select(Quote).where(Quote.id == job.quote_id)
        )
        quote = result.scalar_one()
        quote.is_accepted = True
        quote.accepted_at = datetime.utcnow()

        # Update job status
        job.status = JobStatus.SCHEDULED

        await self.db.flush()
        return job

    async def attach_po(self, job_id: int, po_number: str) -> Job:
        """Attach a PO number and clear financial hold."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.po_number = po_number
        job.financial_hold = False
        job.financial_hold_reason = None

        await self.db.flush()
        return job

    async def get_active_jobs(self) -> list[Job]:
        """Get all active jobs (not completed or cancelled)."""
        result = await self.db.execute(
            select(Job)
            .where(Job.status.not_in([JobStatus.COMPLETED, JobStatus.CANCELLED]))
            .order_by(Job.priority, Job.created_at)
        )
        return list(result.scalars().all())

    async def get_jobs_on_financial_hold(self) -> list[Job]:
        """Get jobs that are on financial hold."""
        result = await self.db.execute(
            select(Job).where(Job.financial_hold == True)
        )
        return list(result.scalars().all())

    async def search_jobs(
        self,
        query: str,
        status: Optional[JobStatus] = None
    ) -> list[Job]:
        """Search jobs by customer name or description."""
        stmt = select(Job).where(
            (Job.customer_name.ilike(f"%{query}%")) |
            (Job.description.ilike(f"%{query}%")) |
            (Job.job_number.ilike(f"%{query}%"))
        )

        if status:
            stmt = stmt.where(Job.status == status)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
