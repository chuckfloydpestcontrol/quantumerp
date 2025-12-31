"""Scheduling Spoke Service - manages machines and production slots."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Machine, ProductionSlot, SlotStatus
from schemas import SlotFindResult


class SchedulingService:
    """Service for production scheduling operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_slot(
        self,
        machine_type: str,
        duration_hours: int,
        earliest_start: Optional[datetime] = None,
        preferred_end: Optional[datetime] = None
    ) -> SlotFindResult:
        """
        Find the earliest available production slot for a machine type.

        Args:
            machine_type: Type of machine required (e.g., 'cnc', 'lathe', '5-axis')
            duration_hours: Required duration in hours
            earliest_start: Earliest possible start time (defaults to now)
            preferred_end: Preferred completion time (for deadline constraints)

        Returns:
            SlotFindResult with earliest available slot information
        """
        if earliest_start is None:
            earliest_start = datetime.utcnow()

        # Find machines of the specified type
        result = await self.db.execute(
            select(Machine).where(
                and_(
                    Machine.machine_type == machine_type,
                    Machine.status == "operational"
                )
            )
        )
        machines = list(result.scalars().all())

        if not machines:
            raise ValueError(f"No operational machines of type '{machine_type}' found")

        best_slot = None
        best_machine = None

        for machine in machines:
            # Find existing slots that might conflict
            slot_start = await self._find_next_available_start(
                machine.id,
                earliest_start,
                duration_hours
            )

            if best_slot is None or slot_start < best_slot:
                best_slot = slot_start
                best_machine = machine

        slot_end = best_slot + timedelta(hours=duration_hours)

        # Find alternative slots on other machines
        alternatives = []
        for machine in machines:
            if machine.id != best_machine.id:
                alt_start = await self._find_next_available_start(
                    machine.id,
                    earliest_start,
                    duration_hours
                )
                alternatives.append({
                    "machine_id": machine.id,
                    "machine_name": machine.name,
                    "start_time": alt_start.isoformat(),
                    "end_time": (alt_start + timedelta(hours=duration_hours)).isoformat()
                })

        return SlotFindResult(
            machine_id=best_machine.id,
            machine_name=best_machine.name,
            earliest_start=best_slot,
            earliest_end=slot_end,
            slot_available=True,
            alternative_slots=alternatives[:3] if alternatives else None
        )

    async def _find_next_available_start(
        self,
        machine_id: int,
        earliest_start: datetime,
        duration_hours: int
    ) -> datetime:
        """Find the next available start time for a machine."""
        duration = timedelta(hours=duration_hours)

        # Get all future reserved slots for this machine
        result = await self.db.execute(
            select(ProductionSlot).where(
                and_(
                    ProductionSlot.machine_id == machine_id,
                    ProductionSlot.end_time > earliest_start,
                    ProductionSlot.status.in_([
                        SlotStatus.RESERVED,
                        SlotStatus.IN_PROGRESS
                    ])
                )
            ).order_by(ProductionSlot.start_time)
        )
        existing_slots = list(result.scalars().all())

        if not existing_slots:
            return earliest_start

        # Check if we can fit before the first slot
        if earliest_start + duration <= existing_slots[0].start_time:
            return earliest_start

        # Find gap between slots
        for i in range(len(existing_slots) - 1):
            gap_start = existing_slots[i].end_time
            gap_end = existing_slots[i + 1].start_time

            if gap_start >= earliest_start and gap_end - gap_start >= duration:
                return max(gap_start, earliest_start)

        # No gap found, schedule after the last slot
        return existing_slots[-1].end_time

    async def reserve_slot(
        self,
        machine_id: int,
        start_time: datetime,
        end_time: datetime,
        job_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> ProductionSlot:
        """
        Reserve a production slot.

        Args:
            machine_id: ID of the machine
            start_time: Slot start time
            end_time: Slot end time
            job_id: Optional job ID (can be None for Dynamic Entry)
            notes: Optional notes

        Returns:
            Created ProductionSlot
        """
        # Verify machine exists
        result = await self.db.execute(
            select(Machine).where(Machine.id == machine_id)
        )
        machine = result.scalar_one_or_none()
        if not machine:
            raise ValueError(f"Machine with ID {machine_id} not found")

        # Check for conflicts
        result = await self.db.execute(
            select(ProductionSlot).where(
                and_(
                    ProductionSlot.machine_id == machine_id,
                    ProductionSlot.status.in_([
                        SlotStatus.RESERVED,
                        SlotStatus.IN_PROGRESS
                    ]),
                    or_(
                        and_(
                            ProductionSlot.start_time <= start_time,
                            ProductionSlot.end_time > start_time
                        ),
                        and_(
                            ProductionSlot.start_time < end_time,
                            ProductionSlot.end_time >= end_time
                        ),
                        and_(
                            ProductionSlot.start_time >= start_time,
                            ProductionSlot.end_time <= end_time
                        )
                    )
                )
            )
        )
        conflicts = list(result.scalars().all())

        if conflicts:
            raise ValueError(
                f"Slot conflicts with {len(conflicts)} existing reservation(s)"
            )

        # Create the slot
        slot = ProductionSlot(
            machine_id=machine_id,
            job_id=job_id,
            start_time=start_time,
            end_time=end_time,
            status=SlotStatus.RESERVED,
            notes=notes
        )
        self.db.add(slot)
        await self.db.flush()
        return slot

    async def get_machine_schedule(
        self,
        machine_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> list[ProductionSlot]:
        """Get schedule for a specific machine."""
        query = select(ProductionSlot).where(
            ProductionSlot.machine_id == machine_id
        )

        if start_date:
            query = query.where(ProductionSlot.start_time >= start_date)
        if end_date:
            query = query.where(ProductionSlot.end_time <= end_date)

        query = query.order_by(ProductionSlot.start_time)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_schedules(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """Get schedule for all machines (for Gantt view)."""
        machines_result = await self.db.execute(select(Machine))
        machines = list(machines_result.scalars().all())

        schedules = {}
        for machine in machines:
            slots = await self.get_machine_schedule(
                machine.id, start_date, end_date
            )
            schedules[machine.name] = {
                "machine_id": machine.id,
                "hourly_rate": machine.hourly_rate,
                "slots": [
                    {
                        "id": slot.id,
                        "job_id": slot.job_id,
                        "start": slot.start_time.isoformat(),
                        "end": slot.end_time.isoformat(),
                        "status": slot.status.value
                    }
                    for slot in slots
                ]
            }

        return schedules

    async def release_slot(self, slot_id: int) -> None:
        """Release a reserved slot."""
        result = await self.db.execute(
            select(ProductionSlot).where(ProductionSlot.id == slot_id)
        )
        slot = result.scalar_one_or_none()

        if slot:
            slot.status = SlotStatus.AVAILABLE
            slot.job_id = None
            await self.db.flush()

    async def create_machine(
        self,
        name: str,
        machine_type: str,
        hourly_rate: float,
        **kwargs
    ) -> Machine:
        """Create a new machine."""
        machine = Machine(
            name=name,
            machine_type=machine_type,
            hourly_rate=hourly_rate,
            **kwargs
        )
        self.db.add(machine)
        await self.db.flush()
        return machine
