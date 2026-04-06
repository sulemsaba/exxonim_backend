from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import notification as notification_crud
from app.crud import service_request as service_request_crud
from app.models import Consultation, ConsultationStatusHistory
from app.schemas.consultation import (
    ConsultationStatus,
    PublicConsultationCreate,
    PublicConsultationCreateResponse,
)
from app.schemas.service_request import CustomerCreate, CustomerUpdate, InboxMessageCreate, ServiceRequestCreate

router = APIRouter(prefix="/consultations", tags=["consultations"])


def _normalize_service_type_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or None


def _normalize_optional_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    return normalized or None


def _compatibility_status(value: str) -> ConsultationStatus:
    return service_request_crud.compatibility_status_from_service_request_status(value)  # type: ignore[return-value]


@router.post(
    "",
    response_model=PublicConsultationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_consultation(
    payload: PublicConsultationCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PublicConsultationCreateResponse:
    idempotency_key = _normalize_optional_text(payload.idempotency_key) or f"public:{uuid4()}"
    existing_consultation = await db.scalar(
        select(Consultation).where(Consultation.idempotency_key == idempotency_key)
    )
    if existing_consultation is not None:
        existing_request = await service_request_crud.get_service_request_by_legacy_consultation_id(
            db,
            existing_consultation.id,
        )
        if existing_request is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A request with this submission key already exists but is incomplete.",
            )

        response.status_code = status.HTTP_200_OK
        return PublicConsultationCreateResponse(
            consultation_id=existing_consultation.id,
            service_request_id=existing_request.id,
            tracking_id=existing_request.tracking_id,
            status=_compatibility_status(existing_request.status),
            message="Your request has already been received.",
            received_at=existing_request.created_at,
        )

    normalized_email = service_request_crud.normalize_email(payload.email)
    customer = await service_request_crud.get_customer_by_normalized_email(db, normalized_email)
    if customer is None:
        customer = await service_request_crud.create_customer(
            db,
            CustomerCreate(
                display_name=payload.full_name.strip(),
                primary_email=payload.email.strip(),
                primary_phone=_normalize_optional_text(payload.phone),
                company_name=_normalize_optional_text(payload.company),
                customer_kind="organization" if _normalize_optional_text(payload.company) else "individual",
                source=payload.source_channel,
            ),
        )
    else:
        update_payload = CustomerUpdate(
            display_name=customer.display_name or payload.full_name.strip(),
            primary_phone=customer.primary_phone or _normalize_optional_text(payload.phone),
            company_name=customer.company_name or _normalize_optional_text(payload.company),
            source=customer.source,
        )
        await service_request_crud.update_customer(db, customer, update_payload)

    service_type_code = _normalize_service_type_code(payload.service_type_code) or (
        service_request_crud.infer_service_type_code_from_text(
            payload.message,
            payload.company,
        )
    )
    service_type = await service_request_crud.get_or_create_service_type_by_code(
        db,
        service_type_code,
    )

    service_request = await service_request_crud.create_service_request(
        db,
        payload=ServiceRequestCreate(
            customer_id=customer.id,
            service_type_id=service_type.id,
            title=f"{payload.full_name.strip()} request",
            intake_message=payload.message.strip(),
            source_channel=payload.source_channel,
            priority="normal",
            status="new",
        ),
    )

    legacy_consultation = Consultation(
        tracking_id=service_request.tracking_id,
        idempotency_key=idempotency_key,
        full_name=payload.full_name.strip(),
        email=payload.email.strip(),
        phone=_normalize_optional_text(payload.phone),
        company=_normalize_optional_text(payload.company),
        message=payload.message.strip(),
        status="pending",
    )
    db.add(legacy_consultation)
    await db.flush()

    service_request.legacy_consultation_id = legacy_consultation.id
    db.add(service_request)
    await db.flush()

    await service_request_crud.add_status_history(
        db,
        service_request=service_request,
        old_status=None,
        new_status=service_request.status,
        changed_by_admin=None,
        comment="Public request submitted from the website contact flow.",
    )

    primary_thread = await service_request_crud.get_or_create_primary_thread(
        db,
        service_request=service_request,
        subject=service_request.title,
    )
    await service_request_crud.add_inbox_message(
        db,
        thread=primary_thread,
        payload=InboxMessageCreate(
            direction="inbound",
            channel="web_form",
            body=payload.message.strip(),
            customer_author_name=payload.full_name.strip(),
            customer_author_email=payload.email.strip(),
        ),
        author_admin=None,
        service_request=service_request,
    )

    db.add(
        ConsultationStatusHistory(
            consultation_id=legacy_consultation.id,
            old_status=None,
            new_status="pending",
            changed_by=None,
            comment="Public request submitted from the website contact flow.",
        )
    )

    await notification_crud.emit_request_submitted_notifications(
        db,
        service_request=service_request,
        customer_name=customer.display_name,
    )

    await db.commit()

    return PublicConsultationCreateResponse(
        consultation_id=legacy_consultation.id,
        service_request_id=service_request.id,
        tracking_id=service_request.tracking_id,
        status="pending",
        message="Your request has been received.",
        received_at=service_request.created_at,
    )
