from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import _unauthorized
from app.core.security import decode_token
from app.crud import consultation as consultation_crud
from app.schemas.consultation import (
    ConsultationCreateResponse,
    ConsultationMagicLinkRequest,
    ConsultationMagicLinkResponse,
    ConsultationPublicCreate,
    ConsultationPublicOut,
    ConsultationStatusHistoryPublicOut,
)
from app.services.consultation_notifications import (
    build_confirmation_notification,
    build_magic_link,
    queue_notification,
)

router = APIRouter(prefix="/public/consultations", tags=["public-consultations"])
bearer_scheme = HTTPBearer(auto_error=False)


def _serialize_staff(admin) -> dict | None:
    if admin is None:
        return None

    return {
        "id": admin.id,
        "full_name": admin.email,
        "email": admin.email,
    }


def _public_history_entry(history) -> ConsultationStatusHistoryPublicOut:
    return ConsultationStatusHistoryPublicOut(
        new_status=history.new_status,
        changed_at=history.created_at,
        comment=history.comment,
    )


def _public_response(consultation) -> ConsultationPublicOut:
    return ConsultationPublicOut(
        id=consultation.id,
        tracking_id=consultation.tracking_id,
        full_name=consultation.full_name,
        email=consultation.email,
        phone=consultation.phone,
        company=consultation.company,
        message=consultation.message,
        status=consultation.status,
        assigned_to=_serialize_staff(consultation.assigned_admin),
        public_notes=consultation.public_notes,
        status_history=[_public_history_entry(item) for item in consultation.status_history],
        created_at=consultation.created_at,
        updated_at=consultation.updated_at,
    )


async def _get_consultation_from_magic_token(
    tracking_id: str,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Magic link token is required")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise _unauthorized("Invalid magic link token") from exc

    if payload.get("token_type") != "consultation_magic":
        raise _unauthorized("Invalid magic link token")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise _unauthorized("Invalid magic link token")

    consultation = await consultation_crud.get_consultation_by_id(db, int(subject))
    if consultation is None:
        raise _unauthorized("Consultation could not be found")

    if consultation.tracking_id != tracking_id:
        raise _unauthorized("Magic link does not match this consultation")

    if payload.get("email") != consultation.email or payload.get("tracking_id") != tracking_id:
        raise _unauthorized("Magic link does not match this consultation")

    return consultation


@router.post("", response_model=ConsultationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_public_consultation(
    payload: ConsultationPublicCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ConsultationCreateResponse:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    existing = await consultation_crud.get_consultation_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        return ConsultationCreateResponse(
            id=existing.id,
            tracking_id=existing.tracking_id,
            full_name=existing.full_name,
            email=existing.email,
            phone=existing.phone,
            company=existing.company,
            message=existing.message,
            status=existing.status,
            created_at=existing.created_at,
            magic_link=build_magic_link(existing),
        )

    tracking_id = await consultation_crud.generate_tracking_id(db)
    consultation = consultation_crud.build_consultation(
        payload,
        tracking_id=tracking_id,
        idempotency_key=idempotency_key,
    )
    db.add(consultation)
    await db.flush()

    db.add(
        consultation_crud.build_status_history(
            consultation_id=consultation.id,
            old_status=None,
            new_status=consultation.status,
            changed_by=None,
            comment="Initial submission",
        )
    )

    subject, body = build_confirmation_notification(consultation)
    notification_log = consultation_crud.build_notification_log(
        consultation_id=consultation.id,
        notification_type="email",
        recipient=consultation.email,
        subject=subject,
        body=body,
    )
    db.add(notification_log)

    await db.commit()
    await db.refresh(consultation)
    await db.refresh(notification_log)
    queue_notification(background_tasks, notification_log_id=notification_log.id)

    return ConsultationCreateResponse(
        id=consultation.id,
        tracking_id=consultation.tracking_id,
        full_name=consultation.full_name,
        email=consultation.email,
        phone=consultation.phone,
        company=consultation.company,
        message=consultation.message,
        status=consultation.status,
        created_at=consultation.created_at,
        magic_link=build_magic_link(consultation)
        if request.url.hostname in {"localhost", "127.0.0.1"}
        else None,
    )


@router.get("/{tracking_id}", response_model=ConsultationPublicOut)
async def get_public_consultation(
    tracking_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> ConsultationPublicOut:
    consultation = await _get_consultation_from_magic_token(tracking_id, credentials, db)
    return _public_response(consultation)


@router.post("/magic-link", response_model=ConsultationMagicLinkResponse)
async def send_magic_link(
    payload: ConsultationMagicLinkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ConsultationMagicLinkResponse:
    consultation = await consultation_crud.get_consultation_by_tracking_id(
        db,
        payload.tracking_id,
    )
    if consultation is None or consultation.email != str(payload.email).lower():
        return ConsultationMagicLinkResponse(ok=True)

    subject, body = build_confirmation_notification(consultation)
    notification_log = consultation_crud.build_notification_log(
        consultation_id=consultation.id,
        notification_type="email",
        recipient=consultation.email,
        subject=subject,
        body=body,
    )
    db.add(notification_log)
    await db.commit()
    await db.refresh(notification_log)
    queue_notification(background_tasks, notification_log_id=notification_log.id)

    return ConsultationMagicLinkResponse(
        ok=True,
        magic_link=build_magic_link(consultation)
        if request.url.hostname in {"localhost", "127.0.0.1"}
        else None,
    )
