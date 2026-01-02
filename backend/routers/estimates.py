"""API routes for estimates."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import (
    EstimateCreate, EstimateResponse, EstimateListResponse,
    EstimateUpdate, EstimateGenerateRequest,
    EstimateLineItemCreate, EstimateLineItemUpdate, EstimateLineItemResponse,
    EstimateActionRequest, EstimateRejectRequest, EstimateVersionResponse,
    EstimateStatus
)
from services.estimate import EstimateService

router = APIRouter(prefix="/api/v1/estimates", tags=["Estimates"])


@router.post("", response_model=EstimateResponse, status_code=201)
async def create_estimate(
    data: EstimateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new estimate."""
    service = EstimateService(db)
    estimate = await service.create_estimate(
        customer_id=data.customer_id,
        line_items=data.line_items,
        requested_delivery_date=data.requested_delivery_date,
        notes=data.notes
    )
    await db.commit()
    # Reload with relationships to avoid lazy loading issues
    return await service.get_estimate(estimate.id)


@router.post("/generate", response_model=EstimateResponse, status_code=201)
async def generate_estimate(
    data: EstimateGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate estimate from natural language prompt."""
    # This will be implemented in the NLP pipeline task
    raise HTTPException(status_code=501, detail="NLP generation not yet implemented")


@router.get("", response_model=list[EstimateListResponse])
async def list_estimates(
    customer_id: Optional[int] = Query(None),
    status: Optional[EstimateStatus] = Query(None),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List estimates with optional filters."""
    service = EstimateService(db)
    estimates = await service.list_estimates(
        customer_id=customer_id,
        status=status,
        limit=limit
    )

    # Map to list response with customer name
    result = []
    for est in estimates:
        result.append(EstimateListResponse(
            id=est.id,
            estimate_number=est.estimate_number,
            version=est.version,
            customer_id=est.customer_id,
            customer_name=est.customer.name if est.customer else None,
            status=est.status,
            total_amount=est.total_amount,
            valid_until=est.valid_until,
            created_at=est.created_at
        ))
    return result


@router.get("/{estimate_id}", response_model=EstimateResponse)
async def get_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get estimate by ID."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


@router.patch("/{estimate_id}", response_model=EstimateResponse)
async def update_estimate(
    estimate_id: int,
    data: EstimateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update estimate header fields."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if estimate.status != EstimateStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only update draft estimates")

    # Apply updates
    if data.valid_until is not None:
        estimate.valid_until = data.valid_until
    if data.requested_delivery_date is not None:
        estimate.requested_delivery_date = data.requested_delivery_date
    if data.notes is not None:
        estimate.notes = data.notes
    if data.price_book_id is not None:
        estimate.price_book_id = data.price_book_id

    await db.commit()
    # Reload with relationships
    return await service.get_estimate(estimate_id)


@router.delete("/{estimate_id}", status_code=204)
async def delete_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete draft estimate."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if estimate.status != EstimateStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only delete draft estimates")

    await db.delete(estimate)
    await db.commit()


# Line item routes
@router.post("/{estimate_id}/lines", response_model=EstimateLineItemResponse, status_code=201)
async def add_line_item(
    estimate_id: int,
    data: EstimateLineItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add line item to estimate."""
    service = EstimateService(db)
    try:
        line_item = await service.add_line_item(estimate_id, data)
        await db.commit()
        return line_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{estimate_id}/lines/{line_id}", response_model=EstimateLineItemResponse)
async def update_line_item(
    estimate_id: int,
    line_id: int,
    data: EstimateLineItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update line item."""
    service = EstimateService(db)
    try:
        line_item = await service.update_line_item(line_id, data)
        await db.commit()
        return line_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{estimate_id}/lines/{line_id}", status_code=204)
async def delete_line_item(
    estimate_id: int,
    line_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete line item."""
    service = EstimateService(db)
    try:
        await service.delete_line_item(line_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Action routes
@router.post("/{estimate_id}/actions/submit", response_model=EstimateResponse)
async def submit_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Submit estimate for approval."""
    service = EstimateService(db)
    try:
        await service.submit_for_approval(estimate_id)
        await db.commit()
        return await service.get_estimate(estimate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/approve", response_model=EstimateResponse)
async def approve_estimate(
    estimate_id: int,
    data: EstimateActionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Approve pending estimate."""
    service = EstimateService(db)
    try:
        # TODO: Get actual user ID from auth
        await service.approve(estimate_id, approved_by=1, comment=data.comment)
        await db.commit()
        return await service.get_estimate(estimate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/reject", response_model=EstimateResponse)
async def reject_estimate(
    estimate_id: int,
    data: EstimateRejectRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reject pending estimate."""
    service = EstimateService(db)
    try:
        await service.reject(estimate_id, reason=data.reason)
        await db.commit()
        return await service.get_estimate(estimate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/send", response_model=EstimateResponse)
async def send_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Send estimate to customer."""
    service = EstimateService(db)
    try:
        await service.send_to_customer(estimate_id)
        await db.commit()
        return await service.get_estimate(estimate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/accept", response_model=EstimateResponse)
async def accept_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Accept estimate (customer accepted)."""
    service = EstimateService(db)
    try:
        await service.accept(estimate_id)
        await db.commit()
        return await service.get_estimate(estimate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/revise", response_model=EstimateResponse)
async def revise_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Create new version of estimate."""
    service = EstimateService(db)
    try:
        new_estimate = await service.create_revision(estimate_id)
        await db.commit()
        return await service.get_estimate(new_estimate.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{estimate_id}/versions", response_model=list[EstimateVersionResponse])
async def get_version_history(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get version history for estimate."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    history = await service.get_version_history(estimate.estimate_number)
    return [EstimateVersionResponse(**h) for h in history]
