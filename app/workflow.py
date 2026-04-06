from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import HTTPException, status


class ContentWorkflowStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


VALID_CONTENT_STATUSES = {status.value for status in ContentWorkflowStatus}

LEGAL_CONTENT_STATUS_TRANSITIONS = {
    ContentWorkflowStatus.DRAFT.value: {
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.PENDING_REVIEW.value,
        ContentWorkflowStatus.PUBLISHED.value,
        ContentWorkflowStatus.ARCHIVED.value,
    },
    ContentWorkflowStatus.PENDING_REVIEW.value: {
        ContentWorkflowStatus.PENDING_REVIEW.value,
        ContentWorkflowStatus.PUBLISHED.value,
        ContentWorkflowStatus.REJECTED.value,
        ContentWorkflowStatus.ARCHIVED.value,
    },
    ContentWorkflowStatus.REJECTED.value: {
        ContentWorkflowStatus.REJECTED.value,
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.PENDING_REVIEW.value,
        ContentWorkflowStatus.PUBLISHED.value,
        ContentWorkflowStatus.ARCHIVED.value,
    },
    ContentWorkflowStatus.PUBLISHED.value: {
        ContentWorkflowStatus.PUBLISHED.value,
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.ARCHIVED.value,
    },
    ContentWorkflowStatus.ARCHIVED.value: {
        ContentWorkflowStatus.ARCHIVED.value,
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.PUBLISHED.value,
    },
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_content_status(
    *,
    current_status: str | None,
    requested_status: str | None = None,
    requested_is_published: bool | None = None,
) -> str:
    if isinstance(requested_status, str) and requested_status in VALID_CONTENT_STATUSES:
        return requested_status

    if requested_is_published is True:
        return ContentWorkflowStatus.PUBLISHED.value

    if requested_is_published is False:
        return ContentWorkflowStatus.DRAFT.value

    return current_status or ContentWorkflowStatus.DRAFT.value


def assert_valid_content_status(status_value: str) -> None:
    if status_value not in VALID_CONTENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported workflow status: {status_value}",
        )


def apply_content_status(instance: Any, *, next_status: str, actor_id: int) -> None:
    assert_valid_content_status(next_status)
    now = utc_now()

    if hasattr(instance, "status"):
        instance.status = next_status

    if hasattr(instance, "updated_by_id"):
        instance.updated_by_id = actor_id

    if next_status == ContentWorkflowStatus.PENDING_REVIEW.value:
        if hasattr(instance, "submitted_at"):
            instance.submitted_at = now
        if hasattr(instance, "submitted_by_id"):
            instance.submitted_by_id = actor_id
        _set_public_visibility(instance, is_live=False)
        return

    if next_status == ContentWorkflowStatus.PUBLISHED.value:
        if hasattr(instance, "reviewed_at") and getattr(instance, "reviewed_at", None) is None:
            instance.reviewed_at = now
        if hasattr(instance, "reviewed_by_id") and getattr(instance, "reviewed_by_id", None) is None:
            instance.reviewed_by_id = actor_id
        if hasattr(instance, "published_at") and getattr(instance, "published_at", None) is None:
            instance.published_at = now
        if hasattr(instance, "published_by_id"):
            instance.published_by_id = actor_id
        _set_public_visibility(instance, is_live=True)
        return

    if next_status == ContentWorkflowStatus.REJECTED.value:
        if hasattr(instance, "reviewed_at"):
            instance.reviewed_at = now
        if hasattr(instance, "reviewed_by_id"):
            instance.reviewed_by_id = actor_id
        _set_public_visibility(instance, is_live=False)
        return

    if next_status == ContentWorkflowStatus.DRAFT.value:
        _set_public_visibility(instance, is_live=False)
        return

    if next_status == ContentWorkflowStatus.ARCHIVED.value:
        _set_public_visibility(instance, is_live=False)


def set_creator(instance: Any, actor_id: int) -> None:
    if hasattr(instance, "created_by_id") and getattr(instance, "created_by_id", None) is None:
        instance.created_by_id = actor_id
    if hasattr(instance, "updated_by_id"):
        instance.updated_by_id = actor_id


def is_owned_draft(instance: Any, actor_id: int) -> bool:
    status_value = getattr(instance, "status", None)
    created_by_id = getattr(instance, "created_by_id", None)
    return created_by_id == actor_id and status_value in {
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.REJECTED.value,
    }


def assert_legal_status_transition(current_status: str, next_status: str) -> None:
    assert_valid_content_status(current_status)
    assert_valid_content_status(next_status)

    if next_status not in LEGAL_CONTENT_STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal content workflow transition: {current_status} -> {next_status}",
        )


def _set_public_visibility(instance: Any, *, is_live: bool) -> None:
    if hasattr(instance, "is_published"):
        instance.is_published = is_live
    if hasattr(instance, "is_active"):
        instance.is_active = is_live
