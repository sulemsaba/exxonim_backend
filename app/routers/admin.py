from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import get_request_meta, log_audit, serialize_for_audit
from app.crud import admin as admin_crud
from app.crud import blog as blog_crud
from app.crud import consultation as consultation_crud
from app.crud import job as job_crud
from app.crud import media as media_crud
from app.crud import navigation as navigation_crud
from app.crud import notification as notification_crud
from app.crud import page as page_crud
from app.crud import pricing as pricing_crud
from app.crud import site_settings as site_settings_crud
from app.crud import testimonial as testimonial_crud
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import (
    get_active_refresh_session,
    get_current_admin,
    has_any_permission,
    has_permission,
    require_admin_api_key,
    require_any_permission,
    require_csrf,
    require_permission,
)
from app.models import AdminUser, BlogPost, Page, RefreshSession, Role, SiteSetting, Testimonial
from app.routers.auth import login_via_cookies, logout_via_cookies, refresh_via_cookies
from app.schemas import (
    AdminDashboardSummary,
    AdminLoginRequest,
    AdminLogoutResponse,
    AdminRefreshResponse,
    AdminRoleOut,
    AdminSessionResponse,
    AdminUserRoleUpdate,
    AdminUserStatusUpdate,
    AdminUserOut,
    BlogAuthorCreate,
    BlogAuthorOut,
    BlogAuthorUpdate,
    BlogCategoryCreate,
    BlogCategoryOut,
    BlogCategoryUpdate,
    BlogPostCreate,
    BlogPostOut,
    BlogPostUpdate,
    ConsultationListResponse,
    ConsultationOut,
    ConsultationUpdate,
    JobCreate,
    JobOut,
    JobUpdate,
    MediaCreate,
    MediaOut,
    MediaUpdate,
    NavigationItemCreate,
    NavigationItemOut,
    NavigationItemUpdate,
    PageCreate,
    PageOut,
    PageUpdate,
    PricingPlanCreate,
    PricingPlanOut,
    PricingPlanUpdate,
    SiteSettingCreate,
    SiteSettingOut,
    SiteSettingUpdate,
    ContentWorkflowActionRequest,
    TestimonialCreate,
    TestimonialOut,
    TestimonialUpdate,
)
from app.workflow import (
    ContentWorkflowStatus,
    apply_content_status,
    assert_legal_status_transition,
    is_owned_draft,
    normalize_content_status,
    set_creator,
)

router = APIRouter(prefix="/admin", tags=["admin"])
uploads_dir = settings.media_root_path
uploads_dir.mkdir(parents=True, exist_ok=True)

ALLOWED_UPLOAD_MIME_TYPES: dict[str, tuple[str, str]] = {
    "image/jpeg": ("jpg", "JPEG"),
    "image/png": ("png", "PNG"),
    "image/webp": ("webp", "WEBP"),
}


def _conflict(detail: str = "Resource conflict") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str = "You do not have permission to perform this action.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _has_article_body(content: Any) -> bool:
    if not isinstance(content, dict):
        return False

    if _clean_text(content.get("html")):
        return True

    if _clean_text(content.get("introduction")):
        return True

    sections = content.get("sections")
    if not isinstance(sections, list):
        return False

    for section in sections:
        if not isinstance(section, dict):
            continue
        if _clean_text(section.get("heading")):
            return True
        paragraphs = section.get("paragraphs")
        if isinstance(paragraphs, list) and any(_clean_text(item) for item in paragraphs):
            return True

    return False


def _is_publish_request(*, is_published: bool, published_at: datetime | None) -> bool:
    if is_published:
        return True
    if published_at is None:
        return False
    comparison_now = datetime.now(published_at.tzinfo or timezone.utc)
    return published_at <= comparison_now


def _validate_blog_publish_fields(
    *,
    title: str,
    slug: str,
    excerpt: str | None,
    content: Any,
    category_id: int | None,
    author_id: int | None,
    featured_image: str | None,
) -> None:
    issues: list[str] = []

    if not _clean_text(title):
        issues.append("Title is required before publishing.")
    if not _clean_text(slug):
        issues.append("Slug is required before publishing.")
    if not _clean_text(excerpt):
        issues.append("Excerpt is required before publishing.")
    if category_id is None:
        issues.append("Category is required before publishing.")
    if author_id is None:
        issues.append("Author is required before publishing.")
    if not _clean_text(featured_image):
        issues.append("Cover image is required before publishing.")
    if not _has_article_body(content):
        issues.append("Add article body content before publishing.")

    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "This post is not ready to publish.",
                "issues": issues,
            },
        )


async def _commit_with_conflict(
    db: AsyncSession,
    *,
    detail: str = "Resource conflict",
) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict(detail) from exc


async def _delete_and_commit(db: AsyncSession, instance: Any) -> Response:
    local_file: Path | None = None
    storage_key = getattr(instance, "storage_key", None)
    if isinstance(storage_key, str) and storage_key:
        local_file = uploads_dir / Path(storage_key).name
    elif hasattr(instance, "url") and isinstance(instance.url, str):
        filename = instance.url.rsplit("/", 1)[-1]
        if "/uploads/" in instance.url:
            local_file = uploads_dir / filename

    if local_file is not None and local_file.exists():
        local_file.unlink()
    await db.delete(instance)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _log_route_audit(
    db: AsyncSession,
    *,
    request: Request | None,
    current_admin: AdminUser | None,
    action: str,
    target_type: str,
    target_id: int | str | None,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    ip, user_agent = get_request_meta(request)
    await log_audit(
        db,
        actor_id=current_admin.id if current_admin else None,
        actor_email=current_admin.email if current_admin else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
        ip=ip,
        user_agent=user_agent,
    )


async def _refresh_load_and_audit(
    db: AsyncSession,
    instance: Any,
    loader: Callable[[AsyncSession, int], Awaitable[Any]],
    *,
    request: Request | None,
    current_admin: AdminUser,
    action: str,
    target_type: str,
    old_value: Any = None,
) -> Any:
    refreshed = await _refresh_and_load(db, instance, loader)
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action=action,
        target_type=target_type,
        target_id=getattr(refreshed, "id", None),
        old_value=old_value,
        new_value=refreshed,
    )
    return refreshed


async def _delete_and_audit(
    db: AsyncSession,
    instance: Any,
    *,
    request: Request | None,
    current_admin: AdminUser,
    action: str,
    target_type: str,
) -> Response:
    old_value = instance
    target_id = getattr(instance, "id", None)
    response = await _delete_and_commit(db, instance)
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=None,
    )
    return response


async def _refresh_and_load(
    db: AsyncSession,
    instance: Any,
    loader: Callable[[AsyncSession, int], Awaitable[Any]],
) -> Any:
    await db.flush()
    identifier = instance.id
    await _commit_with_conflict(db)
    return await loader(db, identifier)


def _load_pillow():
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image processing support is not installed on this server.",
        ) from exc

    return Image, ImageOps, UnidentifiedImageError


def _sniff_upload_mime_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _sanitize_uploaded_image(file: UploadFile) -> tuple[bytes, str, str]:
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload is empty.",
        )

    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds the maximum allowed size.",
        )

    declared_mime_type = (file.content_type or "").lower()
    sniffed_mime_type = _sniff_upload_mime_type(content)
    if (
        declared_mime_type not in ALLOWED_UPLOAD_MIME_TYPES
        or sniffed_mime_type not in ALLOWED_UPLOAD_MIME_TYPES
        or declared_mime_type != sniffed_mime_type
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are supported.",
        )

    extension, save_format = ALLOWED_UPLOAD_MIME_TYPES[sniffed_mime_type]
    Image, ImageOps, UnidentifiedImageError = _load_pillow()
    decompression_error = getattr(Image, "DecompressionBombError", OSError)

    try:
        with Image.open(BytesIO(content)) as uploaded_image:
            uploaded_image.load()
    except (UnidentifiedImageError, OSError, ValueError, decompression_error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image could not be processed safely.",
        ) from exc

    try:
        with Image.open(BytesIO(content)) as uploaded_image:
            sanitized_image = ImageOps.exif_transpose(uploaded_image)
            width, height = sanitized_image.size
            if (
                width > settings.MAX_UPLOAD_IMAGE_DIMENSION
                or height > settings.MAX_UPLOAD_IMAGE_DIMENSION
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The uploaded image dimensions are too large.",
                )

            if save_format == "JPEG":
                sanitized_image = sanitized_image.convert("RGB")
            elif save_format in {"PNG", "WEBP"} and sanitized_image.mode not in {"RGB", "RGBA"}:
                sanitized_image = sanitized_image.convert(
                    "RGBA" if "A" in sanitized_image.getbands() else "RGB"
                )

            output = BytesIO()
            save_kwargs: dict[str, Any] = {"format": save_format}
            if save_format == "JPEG":
                save_kwargs.update({"quality": 90, "optimize": True, "progressive": True})
            elif save_format == "PNG":
                save_kwargs.update({"optimize": True})
            else:
                save_kwargs.update({"quality": 90, "method": 6})

            sanitized_image.save(output, **save_kwargs)
    except HTTPException:
        raise
    except (OSError, ValueError, decompression_error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image could not be normalized safely.",
        ) from exc

    sanitized_bytes = output.getvalue()
    if not sanitized_bytes or len(sanitized_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The processed image is not valid for storage.",
        )

    return sanitized_bytes, sniffed_mime_type, extension


def _build_media_url(request: Request, storage_key: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/uploads/{storage_key}"

def _admin_blog_edit_href(post_id: int) -> str:
    return f"/admin/blog/posts/{post_id}/edit/"


def _admin_page_edit_href(page_id: int) -> str:
    return f"/admin/pages/{page_id}/edit/"


def _admin_setting_href(setting_key: str) -> str:
    mapping = {
        "brand": "/admin/settings/brand/",
        "company_info": "/admin/settings/brand/",
        "contact_map": "/admin/settings/contact/",
        "footer": "/admin/settings/footer/",
        "seo_defaults": "/admin/settings/seo/",
    }
    return mapping.get(setting_key, "/admin/settings/brand/")


def _admin_consultation_href(consultation_id: int) -> str:
    return f"/admin/consultations/{consultation_id}/"


def _admin_job_edit_href(job_slug: str) -> str:
    return f"/admin/jobs/{job_slug}/"


def _admin_content_review_href(target_type: str, target_id: int) -> str | None:
    if target_type == "blog_post":
        return _admin_blog_edit_href(target_id)
    if target_type == "page":
        return _admin_page_edit_href(target_id)
    if target_type == "testimonial":
        return "/admin/testimonials/"
    return None


def _dashboard_status_for_post(post: BlogPost) -> str:
    return _current_content_status(post)


def _dashboard_status_for_page(page: Page) -> str:
    return _current_content_status(page)


def _assert_permission(current_admin: AdminUser, permission_code: str, detail: str | None = None) -> None:
    if not has_permission(current_admin, permission_code):
        raise _forbidden(detail or "You do not have permission to perform this action.")


def _assert_any_permission(
    current_admin: AdminUser,
    permission_codes: list[str],
    detail: str | None = None,
) -> None:
    if not has_any_permission(current_admin, *permission_codes):
        raise _forbidden(detail or "You do not have permission to perform this action.")


def _enforce_content_edit_access(
    current_admin: AdminUser,
    instance: Any,
    permission_prefix: str,
) -> None:
    if has_permission(current_admin, f"{permission_prefix}.edit_any_draft"):
        return
    if has_permission(current_admin, f"{permission_prefix}.edit_own_draft") and is_owned_draft(
        instance, current_admin.id
    ):
        return
    raise _forbidden("You can only edit your own draft content.")


def _enforce_content_transition(
    current_admin: AdminUser,
    *,
    current_status: str,
    next_status: str,
    permission_prefix: str,
) -> None:
    if next_status == current_status:
        return

    assert_legal_status_transition(current_status, next_status)

    if next_status == ContentWorkflowStatus.PENDING_REVIEW.value:
        _assert_any_permission(
            current_admin,
            [
                f"{permission_prefix}.submit_review",
                f"{permission_prefix}.approve",
                f"{permission_prefix}.publish",
            ],
        )
        return

    if next_status == ContentWorkflowStatus.PUBLISHED.value:
        if current_status == ContentWorkflowStatus.PENDING_REVIEW.value:
            _assert_any_permission(
                current_admin,
                [f"{permission_prefix}.approve", f"{permission_prefix}.publish"],
            )
        else:
            _assert_permission(current_admin, f"{permission_prefix}.publish")
        return

    if next_status == ContentWorkflowStatus.REJECTED.value:
        _assert_permission(current_admin, f"{permission_prefix}.reject")
        return

    if next_status == ContentWorkflowStatus.ARCHIVED.value:
        _assert_permission(current_admin, f"{permission_prefix}.archive")
        return

    if next_status == ContentWorkflowStatus.DRAFT.value:
        if current_status in {
            ContentWorkflowStatus.PUBLISHED.value,
            ContentWorkflowStatus.ARCHIVED.value,
        }:
            _assert_permission(current_admin, f"{permission_prefix}.publish")
            return

        _assert_any_permission(
            current_admin,
            [
                f"{permission_prefix}.edit_any_draft",
                f"{permission_prefix}.edit_own_draft",
                f"{permission_prefix}.reject",
                f"{permission_prefix}.publish",
            ],
        )
        return

    raise _forbidden()


def _validate_page_publish_fields(page: Page) -> None:
    issues: list[str] = []

    if not _clean_text(page.title):
        issues.append("Title is required before publishing.")
    if not _clean_text(page.slug):
        issues.append("Slug is required before publishing.")
    if not isinstance(page.content, dict) or not page.content:
        issues.append("Page content is required before publishing.")

    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "This page is not ready to publish.", "issues": issues},
        )


def _validate_testimonial_publish_fields(testimonial: Testimonial) -> None:
    issues: list[str] = []

    if not _clean_text(testimonial.author):
        issues.append("Author is required before publishing.")
    if not _clean_text(testimonial.content):
        issues.append("Quote content is required before publishing.")

    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "This testimonial is not ready to publish.", "issues": issues},
        )


def _current_content_status(instance: Any) -> str:
    status_value = getattr(instance, "status", None)
    if isinstance(status_value, str) and status_value:
        if status_value == "in_review":
            return ContentWorkflowStatus.PENDING_REVIEW.value
        if status_value == "scheduled":
            return ContentWorkflowStatus.DRAFT.value
        return status_value

    if getattr(instance, "is_published", False) or getattr(instance, "is_active", False):
        return ContentWorkflowStatus.PUBLISHED.value

    return ContentWorkflowStatus.DRAFT.value


async def _transition_content_status(
    db: AsyncSession,
    *,
    request: Request,
    current_admin: AdminUser,
    instance: Any,
    loader: Callable[[AsyncSession, int], Awaitable[Any]],
    permission_prefix: str,
    next_status: str,
    action: str,
    target_type: str,
    validator: Callable[[Any], None] | None = None,
    required_permission: str | None = None,
    allowed_current_statuses: set[str] | None = None,
    audit_context: dict[str, Any] | None = None,
) -> Any:
    current_status = _current_content_status(instance)
    if allowed_current_statuses is not None and current_status not in allowed_current_statuses:
        allowed_labels = ", ".join(sorted(allowed_current_statuses))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This action is only allowed when content is in: {allowed_labels}.",
        )
    if required_permission is not None:
        _assert_permission(current_admin, required_permission)
    _enforce_content_transition(
        current_admin,
        current_status=current_status,
        next_status=next_status,
        permission_prefix=permission_prefix,
    )

    if next_status == ContentWorkflowStatus.PUBLISHED.value and validator is not None:
        validator(instance)

    old_value = serialize_for_audit(instance)
    apply_content_status(instance, next_status=next_status, actor_id=current_admin.id)
    db.add(instance)
    refreshed = await _refresh_and_load(db, instance, loader)
    new_value: Any = refreshed
    if audit_context:
        new_value = {
            "record": serialize_for_audit(refreshed),
            "workflow": audit_context,
        }
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action=action,
        target_type=target_type,
        target_id=getattr(refreshed, "id", None),
        old_value=old_value,
        new_value=new_value,
    )
    if next_status == ContentWorkflowStatus.PENDING_REVIEW.value:
        target_id = getattr(refreshed, "id", None)
        title = (
            getattr(refreshed, "title", None)
            or getattr(refreshed, "headline", None)
            or getattr(refreshed, "author", None)
        )
        if isinstance(target_id, int) and isinstance(title, str):
            href = _admin_content_review_href(target_type, target_id)
            if href:
                emitted = await notification_crud.emit_content_pending_review_notifications(
                    db,
                    content_type=target_type,
                    content_id=target_id,
                    title=title,
                    href=href,
                    actor_admin=current_admin,
                )
                if emitted:
                    await _commit_with_conflict(db)
    return refreshed


def _dashboard_seo_health(
    *,
    meta_title: str | None,
    meta_description: str | None,
    share_image: str | None = None,
    require_share_image: bool = False,
) -> str:
    has_title = bool(_clean_text(meta_title))
    has_description = bool(_clean_text(meta_description))
    has_share_image = bool(_clean_text(share_image))

    if has_title and has_description and (has_share_image or not require_share_image):
        return "clean"

    if has_title or has_description or has_share_image:
        return "warning"

    return "error"


def _completion_percent(parts: list[bool]) -> int:
    if not parts:
        return 0
    complete = sum(1 for part in parts if part)
    return round((complete / len(parts)) * 100)


def _blog_completion_percent(post: BlogPost) -> int:
    return _completion_percent(
        [
            bool(_clean_text(post.title)),
            bool(_clean_text(post.slug)),
            bool(_clean_text(post.excerpt)),
            post.category_id is not None,
            post.author_id is not None,
            bool(_clean_text(post.featured_image)),
            _has_article_body(post.content),
        ]
    )


def _page_completion_percent(page: Page) -> int:
    return _completion_percent(
        [
            bool(_clean_text(page.title)),
            bool(_clean_text(page.slug)),
            _has_article_body(page.content),
            bool(_clean_text(page.meta_title)),
            bool(_clean_text(page.meta_description)),
        ]
    )


def _pipeline_priority(status: str) -> int:
    if status == ContentWorkflowStatus.PENDING_REVIEW.value:
        return 0
    if status in {
        ContentWorkflowStatus.DRAFT.value,
        ContentWorkflowStatus.REJECTED.value,
    }:
        return 1
    if status == ContentWorkflowStatus.PUBLISHED.value:
        return 2
    return 3


def _consultation_priority(status: str) -> int:
    if status == "pending":
        return 0
    if status == "contacted":
        return 1
    if status == "completed":
        return 2
    return 3


def _setting_activity_meta(setting_key: str) -> tuple[str, str]:
    mapping = {
        "brand": ("Brand settings", "/admin/settings/brand/"),
        "company_info": ("Company profile", "/admin/settings/brand/"),
        "contact_map": ("Contact & map", "/admin/settings/contact/"),
        "footer": ("Footer content", "/admin/settings/footer/"),
        "seo_defaults": ("SEO defaults", "/admin/settings/seo/"),
    }
    return mapping.get(setting_key, ("Site setting", _admin_setting_href(setting_key)))


def _consultation_assignee_label(assigned_admin: AdminUser | None) -> str | None:
    return assigned_admin.email if assigned_admin else None


def _with_consultation_document_urls(
    consultation: ConsultationOut,
    request: Request,
) -> ConsultationOut:
    if not consultation.documents:
        return consultation

    base_url = str(request.base_url).rstrip("/")
    return consultation.model_copy(
        update={
            "documents": [
                document.model_copy(
                    update={
                        "download_url": f"{base_url}/api/v1/admin/documents/{document.id}/download"
                    }
                )
                for document in consultation.documents
            ]
        }
    )


def _build_dashboard_alerts(
    *,
    posts: list[BlogPost],
    pages: list[Page],
    consultations: list[Any],
    settings_by_key: dict[str, SiteSetting],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    seo_defaults = settings_by_key.get("seo_defaults")
    seo_value = seo_defaults.value if seo_defaults else {}
    default_meta_title = seo_value.get("defaultMetaTitle") if isinstance(seo_value, dict) else None
    default_meta_description = (
        seo_value.get("defaultMetaDescription") if isinstance(seo_value, dict) else None
    )

    if not _clean_text(default_meta_title) or not _clean_text(default_meta_description):
        alerts.append(
            {
                "id": "seo-defaults-missing",
                "severity": "warning",
                "title": "SEO defaults incomplete",
                "message": "Default meta title or description is missing.",
                "href": "/admin/settings/seo/",
            }
        )

    posts_missing_cover = [post for post in posts if not _clean_text(post.featured_image)]
    if posts_missing_cover:
        alerts.append(
            {
                "id": "posts-missing-cover",
                "severity": "info",
                "title": "Cover images need attention",
                "message": f"{len(posts_missing_cover)} posts are still missing a cover image.",
                "href": "/admin/blog/posts/",
            }
        )

    unpublished_pages = [page for page in pages if not page.is_published]
    if unpublished_pages:
        alerts.append(
            {
                "id": "pages-not-live",
                "severity": "info",
                "title": "Pages still in draft",
                "message": f"{len(unpublished_pages)} pages are not published yet.",
                "href": "/admin/pages/",
            }
        )

    pending_consultations = [item for item in consultations if item.status == "pending"]
    if pending_consultations:
        alerts.append(
            {
                "id": "consultations-pending",
                "severity": "warning",
                "title": "Service requests waiting for follow-up",
                "message": f"{len(pending_consultations)} service requests are still pending review.",
                "href": "/admin/consultations/",
            }
        )

    return alerts[:4]


def _build_dashboard_recent_activity(
    *,
    current_admin: AdminUser,
    posts: list[BlogPost],
    pages: list[Page],
    consultation_history: list[Any],
    settings: list[SiteSetting],
) -> list[dict[str, Any]]:
    activity: list[tuple[datetime, dict[str, Any]]] = []

    for post in posts[:6]:
        status = _dashboard_status_for_post(post)
        actor_name = post.author.name if post.author else current_admin.email
        actor_role = post.author.role if post.author and _clean_text(post.author.role) else "Administrator"
        actor_type = "editor" if post.author else "admin"
        action_type = "published" if status == "published" else "draft_created" if post.created_at == post.updated_at else "updated"

        activity.append(
            (
                post.updated_at,
                {
                    "id": f"post-{post.id}",
                    "actor_name": actor_name,
                    "actor_role": actor_role,
                    "actor_type": actor_type,
                    "action_type": action_type,
                    "resource_type": "blog_post",
                    "target_label": post.title,
                    "target_url": _admin_blog_edit_href(post.id),
                    "detail": f"Blog post {status}.",
                    "created_at": post.updated_at,
                },
            )
        )

    for page in pages[:4]:
        activity.append(
            (
                page.updated_at,
                {
                    "id": f"page-{page.id}",
                    "actor_name": current_admin.email,
                    "actor_role": "Administrator",
                    "actor_type": "admin",
                    "action_type": "published" if page.is_published else "updated",
                    "resource_type": "page",
                    "target_label": page.title,
                    "target_url": _admin_page_edit_href(page.id),
                    "detail": "Page content updated.",
                    "created_at": page.updated_at,
                },
            )
        )

    for setting in settings[:4]:
        label, href = _setting_activity_meta(setting.key)
        activity.append(
            (
                setting.updated_at,
                {
                    "id": f"setting-{setting.key}",
                    "actor_name": current_admin.email,
                    "actor_role": "Administrator",
                    "actor_type": "admin",
                    "action_type": "settings_updated",
                    "resource_type": "seo" if setting.key == "seo_defaults" else "setting",
                    "target_label": label,
                    "target_url": href,
                    "detail": f"{label} updated.",
                    "created_at": setting.updated_at,
                },
            )
        )

    for entry in consultation_history:
        consultation = entry.consultation
        if consultation is None:
            continue

        actor_name = (
            entry.changed_by_admin.email
            if entry.changed_by_admin
            else consultation.email
        )
        actor_role = "Administrator" if entry.changed_by_admin else "Client"
        action_type = "consultation_received" if entry.old_status is None else "updated"
        detail = entry.comment or f"Consultation moved to {entry.new_status}."

        activity.append(
            (
                entry.created_at,
                {
                    "id": f"consultation-{entry.id}",
                    "actor_name": actor_name,
                    "actor_role": actor_role,
                    "actor_type": "admin" if entry.changed_by_admin else "system",
                    "action_type": action_type,
                    "resource_type": "consultation",
                    "target_label": consultation.full_name,
                    "target_url": _admin_consultation_href(consultation.id),
                    "detail": detail,
                    "created_at": entry.created_at,
                },
            )
        )

    activity.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in activity[:8]]


def _build_dashboard_pipeline(posts: list[BlogPost], pages: list[Page]) -> list[dict[str, Any]]:
    queue: list[tuple[tuple[int, int, int, float], dict[str, Any]]] = []

    for post in posts:
        status = _dashboard_status_for_post(post)
        seo_health = _dashboard_seo_health(
            meta_title=post.meta_title,
            meta_description=post.meta_description,
            share_image=post.featured_image,
            require_share_image=True,
        )
        completion_percent = _blog_completion_percent(post)
        queue.append(
            (
                (
                    _pipeline_priority(status),
                    completion_percent,
                    0 if seo_health == "error" else 1 if seo_health == "warning" else 2,
                    -post.updated_at.timestamp(),
                ),
                {
                    "id": f"post-{post.id}",
                    "title": post.title,
                    "slug": post.slug,
                    "kind": "blog_post",
                    "status": status,
                    "seo_health": seo_health,
                    "completion_percent": completion_percent,
                    "href": _admin_blog_edit_href(post.id),
                },
            )
        )

    for page in pages:
        status = _dashboard_status_for_page(page)
        seo_health = _dashboard_seo_health(
            meta_title=page.meta_title,
            meta_description=page.meta_description,
            require_share_image=False,
        )
        completion_percent = _page_completion_percent(page)
        queue.append(
            (
                (
                    _pipeline_priority(status),
                    completion_percent,
                    0 if seo_health == "error" else 1 if seo_health == "warning" else 2,
                    -page.updated_at.timestamp(),
                ),
                {
                    "id": f"page-{page.id}",
                    "title": page.title,
                    "slug": page.slug,
                    "kind": "page",
                    "status": status,
                    "seo_health": seo_health,
                    "completion_percent": completion_percent,
                    "href": _admin_page_edit_href(page.id),
                },
            )
        )

    queue.sort(key=lambda item: item[0])
    return [payload for _, payload in queue[:6]]


def _build_dashboard_consultations(consultations: list[Any]) -> list[dict[str, Any]]:
    queue = sorted(
        consultations,
        key=lambda item: (
            _consultation_priority(item.status),
            -item.updated_at.timestamp(),
            -item.id,
        ),
    )

    return [
        {
            "id": consultation.id,
            "tracking_id": consultation.tracking_id,
            "full_name": consultation.full_name,
            "company": consultation.company,
            "status": consultation.status,
            "assigned_admin_label": _consultation_assignee_label(consultation.assigned_admin),
            "created_at": consultation.created_at,
            "updated_at": consultation.updated_at,
            "href": _admin_consultation_href(consultation.id),
        }
        for consultation in queue[:4]
    ]


@router.post("/auth/login", response_model=AdminSessionResponse)
async def login_admin(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminSessionResponse:
    return await login_via_cookies(
        payload=payload,
        request=request,
        response=response,
        db=db,
    )


@router.post("/auth/refresh", response_model=AdminRefreshResponse)
async def refresh_admin_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    csrf_cookie: str | None = Cookie(default=None, alias=settings.CSRF_COOKIE_NAME),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AdminRefreshResponse:
    return await refresh_via_cookies(
        request=request,
        response=response,
        db=db,
        refresh_cookie=refresh_cookie,
        csrf_cookie=csrf_cookie,
        csrf_header=csrf_header,
    )


@router.post("/auth/logout", response_model=AdminLogoutResponse)
async def logout_admin(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
    refresh_session: RefreshSession = Depends(get_active_refresh_session),
) -> AdminLogoutResponse:
    return await logout_via_cookies(
        db=db,
        response=response,
        refresh_session=refresh_session,
    )


@router.get("/auth/me", response_model=AdminUserOut)
async def get_admin_me(
    response: Response,
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminUserOut:
    response.headers["Cache-Control"] = "no-store"
    return current_admin


@router.get("/staff", response_model=list[AdminUserOut])
async def list_admin_staff(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("user.read")),
) -> list[AdminUserOut]:
    return await admin_crud.get_all_admins(db, include_access=True)


@router.get("/users", response_model=list[AdminUserOut])
async def list_admin_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("user.read")),
) -> list[AdminUserOut]:
    return await admin_crud.get_all_admins(
        db,
        include_access=True,
        search=search,
        role_code=role,
    )


@router.put("/users/{admin_id}/role", response_model=AdminUserOut)
async def update_admin_user_role(
    admin_id: int,
    payload: AdminUserRoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("user.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> AdminUserOut:
    target_admin = await admin_crud.get_admin_by_id(db, admin_id, include_access=True)
    if target_admin is None:
        raise _not_found("Admin user not found")

    role = await admin_crud.get_role_by_code(db, payload.role)
    if role is None:
        raise _not_found("Role not found")

    old_value = serialize_for_audit(target_admin)
    previous_role = target_admin.role
    await admin_crud.set_admin_roles(db, admin=target_admin, roles=[role])
    await db.commit()
    refreshed = await admin_crud.get_admin_by_id(db, admin_id, include_access=True)
    if refreshed is None:
        raise _not_found("Admin user not found")

    emitted = await notification_crud.emit_admin_role_changed_notifications(
        db,
        target_admin=refreshed,
        actor_admin=current_admin,
        old_role=previous_role,
        new_role=refreshed.role,
        occurred_at=datetime.now(timezone.utc),
    )
    if emitted:
        await db.commit()

    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="user.role_update",
        target_type="admin_user",
        target_id=admin_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return refreshed


@router.put("/users/{admin_id}/status", response_model=AdminUserOut)
async def update_admin_user_status(
    admin_id: int,
    payload: AdminUserStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("user.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> AdminUserOut:
    target_admin = await admin_crud.get_admin_by_id(db, admin_id, include_access=True)
    if target_admin is None:
        raise _not_found("Admin user not found")

    old_value = serialize_for_audit(target_admin)
    target_admin.is_active = payload.is_active
    db.add(target_admin)
    await db.commit()
    refreshed = await admin_crud.get_admin_by_id(db, admin_id, include_access=True)
    if refreshed is None:
        raise _not_found("Admin user not found")

    emitted = await notification_crud.emit_admin_status_changed_notifications(
        db,
        target_admin=refreshed,
        actor_admin=current_admin,
        is_active=refreshed.is_active,
        occurred_at=datetime.now(timezone.utc),
    )
    if emitted:
        await db.commit()

    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="user.status_update",
        target_type="admin_user",
        target_id=admin_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return refreshed


@router.get("/roles", response_model=list[AdminRoleOut])
async def list_admin_roles(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("role.read")),
) -> list[Role]:
    return await admin_crud.get_all_roles(db)


@router.get("/dashboard/summary", response_model=AdminDashboardSummary)
async def get_admin_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("dashboard.read")),
) -> AdminDashboardSummary:
    posts = await blog_crud.get_all_posts(db)
    jobs = await job_crud.get_published_jobs(db)
    pages = await page_crud.get_all_pages(db)
    consultations = await consultation_crud.get_recent_consultations(db, limit=12)
    consultation_counts = await consultation_crud.get_consultation_status_counts(db)
    consultation_history = await consultation_crud.get_recent_consultation_history(db, limit=8)
    settings = await site_settings_crud.get_site_settings(db)
    settings_by_key = {setting.key: setting for setting in settings}
    draft_posts = [post for post in posts if _dashboard_status_for_post(post) == "draft"]
    published_posts = [post for post in posts if _dashboard_status_for_post(post) == "published"]
    published_pages = [page for page in pages if page.is_published]

    return AdminDashboardSummary(
        metrics=[
            {
                "key": "published_pages",
                "label": "Published Pages",
                "value": len(published_pages),
                "helper": "Live public pages",
                "href": "/admin/pages/",
            },
            {
                "key": "draft_posts",
                "label": "Draft Posts",
                "value": len(draft_posts),
                "helper": "Articles still being prepared",
                "href": "/admin/blog/posts/",
            },
            {
                "key": "pending_consultations",
                "label": "Pending Service Requests",
                "value": consultation_counts.get("pending", 0),
                "helper": f"{consultation_counts.get('contacted', 0)} already contacted",
                "href": "/admin/consultations/",
            },
            {
                "key": "published_posts",
                "label": "Published Posts",
                "value": len(published_posts),
                "helper": f"{len(draft_posts)} drafts waiting",
                "href": "/admin/blog/posts/",
            },
        ],
        alerts=_build_dashboard_alerts(
            posts=posts,
            pages=pages,
            consultations=consultations,
            settings_by_key=settings_by_key,
        ),
        recent_activity=_build_dashboard_recent_activity(
            current_admin=current_admin,
            posts=posts,
            pages=pages,
            consultation_history=consultation_history,
            settings=settings,
        ),
        content_pipeline=_build_dashboard_pipeline(posts, pages),
        consultations=_build_dashboard_consultations(consultations),
        open_jobs=[
            {
                "id": job.id,
                "title": job.title,
                "slug": job.slug,
                "department": job.department,
                "employment_type": job.employment_type,
                "location": ", ".join(part for part in [job.city, job.country] if part) or job.location_mode,
                "status": "published" if job.is_published else "draft",
                "posted_at": job.published_at,
                "href": _admin_job_edit_href(job.slug),
            }
            for job in jobs[:4]
        ],
    )


@router.get("/jobs", response_model=list[JobOut])
async def list_admin_jobs(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("job.read")),
) -> list[JobOut]:
    return await job_crud.get_all_jobs(db)


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("job.create")),
    _write_guard: None = Depends(require_admin_api_key),
) -> JobOut:
    job = job_crud.build_job(payload)
    db.add(job)
    return await _refresh_load_and_audit(
        db,
        job,
        job_crud.get_job_by_id,
        request=request,
        current_admin=current_admin,
        action="job.create",
        target_type="job",
    )


@router.get("/jobs/{slug}", response_model=JobOut)
async def get_admin_job(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("job.read")),
) -> JobOut:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    return job


@router.put("/jobs/{slug}", response_model=JobOut)
async def update_job(
    slug: str,
    payload: JobUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("job.update")),
    _write_guard: None = Depends(require_admin_api_key),
) -> JobOut:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    old_value = serialize_for_audit(job)
    job_crud.apply_job_update(job, payload)
    db.add(job)
    return await _refresh_load_and_audit(
        db,
        job,
        job_crud.get_job_by_id,
        request=request,
        current_admin=current_admin,
        action="job.update",
        target_type="job",
        old_value=old_value,
    )


@router.delete("/jobs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("job.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    return await _delete_and_audit(
        db,
        job,
        request=request,
        current_admin=current_admin,
        action="job.delete",
        target_type="job",
    )


@router.get("/consultations", response_model=ConsultationListResponse)
async def list_admin_consultations(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_value: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    service_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assignee_id: int | None = Query(default=None),
    source_channel: str | None = Query(default=None),
    view: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("consultation.read", "service_request.read")
    ),
) -> ConsultationListResponse:
    items, total = await consultation_crud.get_consultations(
        db,
        page=page,
        limit=limit,
        status=status_value,
        search=search,
        service_type=service_type,
        priority=priority,
        assignee_id=assignee_id,
        source_channel=source_channel,
        view=view,
        current_admin_id=current_admin.id,
        include_history=False,
    )
    return ConsultationListResponse.build(
        items=[_with_consultation_document_urls(item, request) for item in items],
        page=page,
        limit=limit,
        total=total,
    )


@router.get("/consultations/{consultation_id}", response_model=ConsultationOut)
async def get_admin_consultation(
    consultation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("consultation.read", "service_request.read")
    ),
) -> ConsultationOut:
    consultation = await consultation_crud.get_consultation_by_id(
        db,
        consultation_id,
        include_history=True,
        current_admin_id=current_admin.id,
    )
    if consultation is None:
        raise _not_found("Consultation not found")
    return _with_consultation_document_urls(consultation, request)


async def _update_admin_consultation_compatibility(
    consultation_id: int,
    payload: ConsultationUpdate,
    request: Request,
    db: AsyncSession,
    current_admin: AdminUser,
) -> ConsultationOut:
    consultation = await consultation_crud.get_consultation_by_id(
        db,
        consultation_id,
        include_history=True,
        current_admin_id=current_admin.id,
    )
    if consultation is None:
        raise _not_found("Consultation not found")

    if payload.assigned_to is not None and await admin_crud.get_admin_by_id(
        db, payload.assigned_to
    ) is None:
        raise _not_found("Assigned admin not found")

    old_value = serialize_for_audit(consultation)
    refreshed = await consultation_crud.update_consultation_from_compatibility(
        db,
        consultation_id=consultation_id,
        payload=payload,
        current_admin=current_admin,
    )
    await _commit_with_conflict(db)
    if refreshed is None:
        raise _not_found("Consultation not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="consultation.update",
        target_type="consultation",
        target_id=consultation_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return _with_consultation_document_urls(refreshed, request)


@router.put("/consultations/{consultation_id}", response_model=ConsultationOut)
async def update_admin_consultation(
    consultation_id: int,
    payload: ConsultationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("consultation.update", "service_request.update")
    ),
    _csrf: None = Depends(require_csrf),
) -> ConsultationOut:
    return await _update_admin_consultation_compatibility(
        consultation_id=consultation_id,
        payload=payload,
        request=request,
        db=db,
        current_admin=current_admin,
    )


@router.patch("/consultations/{consultation_id}", response_model=ConsultationOut)
async def patch_admin_consultation(
    consultation_id: int,
    payload: ConsultationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("consultation.update", "service_request.update")
    ),
    _csrf: None = Depends(require_csrf),
) -> ConsultationOut:
    return await _update_admin_consultation_compatibility(
        consultation_id=consultation_id,
        payload=payload,
        request=request,
        db=db,
        current_admin=current_admin,
    )


@router.get("/blog/posts", response_model=list[BlogPostOut])
async def list_admin_blog_posts(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("blog_post.read")),
) -> list[BlogPostOut]:
    return await blog_crud.get_all_posts(db)


@router.post("/blog/posts", response_model=BlogPostOut, status_code=status.HTTP_201_CREATED)
async def create_blog_post(
    payload: BlogPostCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.create")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    if payload.category_id is not None and await blog_crud.get_category_by_id(
        db, payload.category_id
    ) is None:
        raise _not_found("Category not found")
    if payload.author_id is not None and await blog_crud.get_author_by_id(
        db, payload.author_id
    ) is None:
        raise _not_found("Author not found")

    payload_data = payload.model_dump(exclude_unset=True)
    next_status = normalize_content_status(
        current_status="draft",
        requested_status=payload_data.get("status"),
        requested_is_published=payload_data.get("is_published"),
    )
    _enforce_content_transition(
        current_admin,
        current_status="draft",
        next_status=next_status,
        permission_prefix="blog_post",
    )

    post = blog_crud.build_post(payload)
    set_creator(post, current_admin.id)
    apply_content_status(post, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_blog_publish_fields(
            title=post.title,
            slug=post.slug,
            excerpt=post.excerpt,
            content=post.content,
            category_id=post.category_id,
            author_id=post.author_id,
            featured_image=post.featured_image,
        )
    db.add(post)
    return await _refresh_load_and_audit(
        db,
        post,
        blog_crud.get_post_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_post.create",
        target_type="blog_post",
    )


@router.get("/blog/posts/{post_id}", response_model=BlogPostOut)
async def get_admin_blog_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("blog_post.read")),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return post


@router.put("/blog/posts/{post_id}", response_model=BlogPostOut)
async def update_blog_post(
    post_id: int,
    payload: BlogPostUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("blog_post.edit_any_draft", "blog_post.edit_own_draft")
    ),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    _enforce_content_edit_access(current_admin, post, "blog_post")

    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data and update_data["category_id"] is not None:
        if await blog_crud.get_category_by_id(db, update_data["category_id"]) is None:
            raise _not_found("Category not found")
    if "author_id" in update_data and update_data["author_id"] is not None:
        if await blog_crud.get_author_by_id(db, update_data["author_id"]) is None:
            raise _not_found("Author not found")

    next_status = normalize_content_status(
        current_status=_current_content_status(post),
        requested_status=update_data.get("status"),
        requested_is_published=update_data.get("is_published"),
    )
    _enforce_content_transition(
        current_admin,
        current_status=_current_content_status(post),
        next_status=next_status,
        permission_prefix="blog_post",
    )

    old_value = serialize_for_audit(post)
    blog_crud.apply_post_update(post, payload)
    apply_content_status(post, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_blog_publish_fields(
            title=post.title,
            slug=post.slug,
            excerpt=post.excerpt,
            content=post.content,
            category_id=post.category_id,
            author_id=post.author_id,
            featured_image=post.featured_image,
        )
    db.add(post)
    return await _refresh_load_and_audit(
        db,
        post,
        blog_crud.get_post_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_post.update",
        target_type="blog_post",
        old_value=old_value,
    )


@router.post("/blog/posts/{post_id}/submit", response_model=BlogPostOut)
async def submit_blog_post_for_review(
    post_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.submit_review")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    _enforce_content_edit_access(current_admin, post, "blog_post")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=post,
        loader=blog_crud.get_post_by_id,
        permission_prefix="blog_post",
        next_status=ContentWorkflowStatus.PENDING_REVIEW.value,
        action="blog_post.submit_review",
        target_type="blog_post",
        required_permission="blog_post.submit_review",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/blog/posts/{post_id}/approve", response_model=BlogPostOut)
async def approve_blog_post(
    post_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.approve")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=post,
        loader=blog_crud.get_post_by_id,
        permission_prefix="blog_post",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="blog_post.approve",
        target_type="blog_post",
        validator=lambda item: _validate_blog_publish_fields(
            title=item.title,
            slug=item.slug,
            excerpt=item.excerpt,
            content=item.content,
            category_id=item.category_id,
            author_id=item.author_id,
            featured_image=item.featured_image,
        ),
        required_permission="blog_post.approve",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/blog/posts/{post_id}/reject", response_model=BlogPostOut)
async def reject_blog_post(
    post_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.reject")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=post,
        loader=blog_crud.get_post_by_id,
        permission_prefix="blog_post",
        next_status=ContentWorkflowStatus.REJECTED.value,
        action="blog_post.reject",
        target_type="blog_post",
        required_permission="blog_post.reject",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/blog/posts/{post_id}/publish", response_model=BlogPostOut)
async def publish_blog_post(
    post_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.publish")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=post,
        loader=blog_crud.get_post_by_id,
        permission_prefix="blog_post",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="blog_post.publish",
        target_type="blog_post",
        validator=lambda item: _validate_blog_publish_fields(
            title=item.title,
            slug=item.slug,
            excerpt=item.excerpt,
            content=item.content,
            category_id=item.category_id,
            author_id=item.author_id,
            featured_image=item.featured_image,
        ),
        required_permission="blog_post.publish",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/blog/posts/{post_id}/archive", response_model=BlogPostOut)
async def archive_blog_post(
    post_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.archive")),
    _csrf: None = Depends(require_csrf),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=post,
        loader=blog_crud.get_post_by_id,
        permission_prefix="blog_post",
        next_status=ContentWorkflowStatus.ARCHIVED.value,
        action="blog_post.archive",
        target_type="blog_post",
        required_permission="blog_post.archive",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.PUBLISHED.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.delete("/blog/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_post.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _delete_and_audit(
        db,
        post,
        request=request,
        current_admin=current_admin,
        action="blog_post.delete",
        target_type="blog_post",
    )


@router.get("/blog/categories", response_model=list[BlogCategoryOut])
async def list_admin_blog_categories(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("blog_category.read")),
) -> list[BlogCategoryOut]:
    return await blog_crud.get_all_categories(db)


@router.post(
    "/blog/categories",
    response_model=BlogCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_blog_category(
    payload: BlogCategoryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_category.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> BlogCategoryOut:
    category = blog_crud.build_category(payload)
    db.add(category)
    return await _refresh_load_and_audit(
        db,
        category,
        blog_crud.get_category_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_category.create",
        target_type="blog_category",
    )


@router.put("/blog/categories/{category_id}", response_model=BlogCategoryOut)
async def update_blog_category(
    category_id: int,
    payload: BlogCategoryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_category.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> BlogCategoryOut:
    category = await blog_crud.get_category_by_id(db, category_id)
    if category is None:
        raise _not_found("Category not found")
    old_value = serialize_for_audit(category)
    blog_crud.apply_category_update(category, payload)
    db.add(category)
    return await _refresh_load_and_audit(
        db,
        category,
        blog_crud.get_category_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_category.update",
        target_type="blog_category",
        old_value=old_value,
    )


@router.delete("/blog/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_category(
    category_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_category.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    category = await blog_crud.get_category_by_id(db, category_id)
    if category is None:
        raise _not_found("Category not found")
    return await _delete_and_audit(
        db,
        category,
        request=request,
        current_admin=current_admin,
        action="blog_category.delete",
        target_type="blog_category",
    )


@router.get("/blog/authors", response_model=list[BlogAuthorOut])
async def list_admin_blog_authors(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("blog_author.read")),
) -> list[BlogAuthorOut]:
    return await blog_crud.get_all_authors(db)


@router.post(
    "/blog/authors",
    response_model=BlogAuthorOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_blog_author(
    payload: BlogAuthorCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_author.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> BlogAuthorOut:
    author = blog_crud.build_author(payload)
    db.add(author)
    return await _refresh_load_and_audit(
        db,
        author,
        blog_crud.get_author_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_author.create",
        target_type="blog_author",
    )


@router.put("/blog/authors/{author_id}", response_model=BlogAuthorOut)
async def update_blog_author(
    author_id: int,
    payload: BlogAuthorUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_author.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> BlogAuthorOut:
    author = await blog_crud.get_author_by_id(db, author_id)
    if author is None:
        raise _not_found("Author not found")
    old_value = serialize_for_audit(author)
    blog_crud.apply_author_update(author, payload)
    db.add(author)
    return await _refresh_load_and_audit(
        db,
        author,
        blog_crud.get_author_by_id,
        request=request,
        current_admin=current_admin,
        action="blog_author.update",
        target_type="blog_author",
        old_value=old_value,
    )


@router.delete("/blog/authors/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_author(
    author_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("blog_author.manage")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    author = await blog_crud.get_author_by_id(db, author_id)
    if author is None:
        raise _not_found("Author not found")
    return await _delete_and_audit(
        db,
        author,
        request=request,
        current_admin=current_admin,
        action="blog_author.delete",
        target_type="blog_author",
    )


@router.get("/pages", response_model=list[PageOut])
async def list_admin_pages(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("page.read")),
) -> list[PageOut]:
    return await page_crud.get_all_pages(db)


@router.post("/pages", response_model=PageOut, status_code=status.HTTP_201_CREATED)
async def create_page(
    payload: PageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.create")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = page_crud.build_page(payload)
    payload_data = payload.model_dump(exclude_unset=True)
    next_status = normalize_content_status(
        current_status="draft",
        requested_status=payload_data.get("status"),
        requested_is_published=payload_data.get("is_published"),
    )
    _enforce_content_transition(
        current_admin,
        current_status="draft",
        next_status=next_status,
        permission_prefix="page",
    )
    set_creator(page, current_admin.id)
    apply_content_status(page, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_page_publish_fields(page)
    db.add(page)
    return await _refresh_load_and_audit(
        db,
        page,
        page_crud.get_page_by_id,
        request=request,
        current_admin=current_admin,
        action="page.create",
        target_type="page",
    )


@router.get("/pages/{page_id}", response_model=PageOut)
async def get_admin_page(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("page.read")),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return page


@router.put("/pages/{page_id}", response_model=PageOut)
async def update_page(
    page_id: int,
    payload: PageUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("page.edit_any_draft", "page.edit_own_draft")
    ),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    _enforce_content_edit_access(current_admin, page, "page")
    old_value = serialize_for_audit(page)
    update_data = payload.model_dump(exclude_unset=True)
    next_status = normalize_content_status(
        current_status=_current_content_status(page),
        requested_status=update_data.get("status"),
        requested_is_published=update_data.get("is_published"),
    )
    _enforce_content_transition(
        current_admin,
        current_status=_current_content_status(page),
        next_status=next_status,
        permission_prefix="page",
    )
    page_crud.apply_page_update(page, payload)
    apply_content_status(page, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_page_publish_fields(page)
    db.add(page)
    return await _refresh_load_and_audit(
        db,
        page,
        page_crud.get_page_by_id,
        request=request,
        current_admin=current_admin,
        action="page.update",
        target_type="page",
        old_value=old_value,
    )


@router.post("/pages/{page_id}/submit", response_model=PageOut)
async def submit_page_for_review(
    page_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.submit_review")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    _enforce_content_edit_access(current_admin, page, "page")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=page,
        loader=page_crud.get_page_by_id,
        permission_prefix="page",
        next_status=ContentWorkflowStatus.PENDING_REVIEW.value,
        action="page.submit_review",
        target_type="page",
        required_permission="page.submit_review",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/pages/{page_id}/approve", response_model=PageOut)
async def approve_page(
    page_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.approve")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=page,
        loader=page_crud.get_page_by_id,
        permission_prefix="page",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="page.approve",
        target_type="page",
        validator=_validate_page_publish_fields,
        required_permission="page.approve",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/pages/{page_id}/reject", response_model=PageOut)
async def reject_page(
    page_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.reject")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=page,
        loader=page_crud.get_page_by_id,
        permission_prefix="page",
        next_status=ContentWorkflowStatus.REJECTED.value,
        action="page.reject",
        target_type="page",
        required_permission="page.reject",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/pages/{page_id}/publish", response_model=PageOut)
async def publish_page(
    page_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.publish")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=page,
        loader=page_crud.get_page_by_id,
        permission_prefix="page",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="page.publish",
        target_type="page",
        validator=_validate_page_publish_fields,
        required_permission="page.publish",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/pages/{page_id}/archive", response_model=PageOut)
async def archive_page(
    page_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.archive")),
    _csrf: None = Depends(require_csrf),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=page,
        loader=page_crud.get_page_by_id,
        permission_prefix="page",
        next_status=ContentWorkflowStatus.ARCHIVED.value,
        action="page.archive",
        target_type="page",
        required_permission="page.archive",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.PUBLISHED.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    page_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("page.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _delete_and_audit(
        db,
        page,
        request=request,
        current_admin=current_admin,
        action="page.delete",
        target_type="page",
    )


@router.get("/navigation", response_model=list[NavigationItemOut])
async def list_admin_navigation(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("navigation.read")),
) -> list[NavigationItemOut]:
    return await navigation_crud.get_navigation_tree(db, active_only=None)


@router.post(
    "/navigation",
    response_model=NavigationItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_navigation_item(
    payload: NavigationItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("navigation.create")),
    _write_guard: None = Depends(require_admin_api_key),
) -> NavigationItemOut:
    if payload.parent_id is not None and await navigation_crud.get_navigation_item_by_id(
        db, payload.parent_id
    ) is None:
        raise _not_found("Parent navigation item not found")

    item = navigation_crud.build_navigation_item(payload)
    db.add(item)
    await db.flush()
    await _commit_with_conflict(db)
    await db.refresh(item)
    serialized = navigation_crud.serialize_navigation_item(item, {})
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="navigation.create",
        target_type="navigation_item",
        target_id=item.id,
        old_value=None,
        new_value=serialized,
    )
    return serialized


@router.get("/navigation/{item_id}", response_model=NavigationItemOut)
async def get_admin_navigation_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("navigation.read")),
) -> NavigationItemOut:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")
    return navigation_crud.serialize_navigation_item(item, {})


@router.put("/navigation/{item_id}", response_model=NavigationItemOut)
async def update_navigation_item(
    item_id: int,
    payload: NavigationItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("navigation.update")),
    _write_guard: None = Depends(require_admin_api_key),
) -> NavigationItemOut:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")
    old_value = serialize_for_audit(item)

    update_data = payload.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        parent_id = update_data["parent_id"]
        if parent_id == item_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A navigation item cannot be its own parent",
            )
        if parent_id is not None and await navigation_crud.get_navigation_item_by_id(
            db, parent_id
        ) is None:
            raise _not_found("Parent navigation item not found")

    navigation_crud.apply_navigation_item_update(item, payload)
    db.add(item)
    await _commit_with_conflict(db)
    await db.refresh(item)
    serialized = navigation_crud.serialize_navigation_item(item, {})
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="navigation.update",
        target_type="navigation_item",
        target_id=item.id,
        old_value=old_value,
        new_value=serialized,
    )
    return serialized


@router.delete("/navigation/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_navigation_item(
    item_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("navigation.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")
    return await _delete_and_audit(
        db,
        item,
        request=request,
        current_admin=current_admin,
        action="navigation.delete",
        target_type="navigation_item",
    )


@router.get("/pricing/plans", response_model=list[PricingPlanOut])
async def list_admin_pricing_plans(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("pricing.read")),
) -> list[PricingPlanOut]:
    return await pricing_crud.get_all_pricing_plans(db)


@router.post(
    "/pricing/plans",
    response_model=PricingPlanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pricing_plan(
    payload: PricingPlanCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("pricing.create")),
    _write_guard: None = Depends(require_admin_api_key),
) -> PricingPlanOut:
    plan = pricing_crud.build_pricing_plan(payload)
    db.add(plan)
    return await _refresh_load_and_audit(
        db,
        plan,
        pricing_crud.get_pricing_plan_by_id,
        request=request,
        current_admin=current_admin,
        action="pricing.create",
        target_type="pricing_plan",
    )


@router.get("/pricing/plans/{plan_id}", response_model=PricingPlanOut)
async def get_admin_pricing_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("pricing.read")),
) -> PricingPlanOut:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    return plan


@router.put("/pricing/plans/{plan_id}", response_model=PricingPlanOut)
async def update_pricing_plan(
    plan_id: int,
    payload: PricingPlanUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("pricing.update")),
    _write_guard: None = Depends(require_admin_api_key),
) -> PricingPlanOut:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    old_value = serialize_for_audit(plan)
    pricing_crud.apply_pricing_plan_update(plan, payload)
    db.add(plan)
    return await _refresh_load_and_audit(
        db,
        plan,
        pricing_crud.get_pricing_plan_by_id,
        request=request,
        current_admin=current_admin,
        action="pricing.update",
        target_type="pricing_plan",
        old_value=old_value,
    )


@router.delete("/pricing/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing_plan(
    plan_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("pricing.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    return await _delete_and_audit(
        db,
        plan,
        request=request,
        current_admin=current_admin,
        action="pricing.delete",
        target_type="pricing_plan",
    )


@router.get("/testimonials", response_model=list[TestimonialOut])
async def list_admin_testimonials(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("testimonial.read")),
) -> list[TestimonialOut]:
    return await testimonial_crud.get_all_testimonials(db)


@router.post(
    "/testimonials",
    response_model=TestimonialOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_testimonial(
    payload: TestimonialCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.create")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = testimonial_crud.build_testimonial(payload)
    payload_data = payload.model_dump(exclude_unset=True)
    next_status = normalize_content_status(
        current_status="draft",
        requested_status=payload_data.get("status"),
        requested_is_published=payload_data.get("is_active"),
    )
    _enforce_content_transition(
        current_admin,
        current_status="draft",
        next_status=next_status,
        permission_prefix="testimonial",
    )
    set_creator(testimonial, current_admin.id)
    apply_content_status(testimonial, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_testimonial_publish_fields(testimonial)
    db.add(testimonial)
    return await _refresh_load_and_audit(
        db,
        testimonial,
        testimonial_crud.get_testimonial_by_id,
        request=request,
        current_admin=current_admin,
        action="testimonial.create",
        target_type="testimonial",
    )


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialOut)
async def get_admin_testimonial(
    testimonial_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("testimonial.read")),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return testimonial


@router.put("/testimonials/{testimonial_id}", response_model=TestimonialOut)
async def update_testimonial(
    testimonial_id: int,
    payload: TestimonialUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(
        require_any_permission("testimonial.edit_any_draft", "testimonial.edit_own_draft")
    ),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    _enforce_content_edit_access(current_admin, testimonial, "testimonial")
    old_value = serialize_for_audit(testimonial)
    update_data = payload.model_dump(exclude_unset=True)
    next_status = normalize_content_status(
        current_status=_current_content_status(testimonial),
        requested_status=update_data.get("status"),
        requested_is_published=update_data.get("is_active"),
    )
    _enforce_content_transition(
        current_admin,
        current_status=_current_content_status(testimonial),
        next_status=next_status,
        permission_prefix="testimonial",
    )
    testimonial_crud.apply_testimonial_update(testimonial, payload)
    apply_content_status(testimonial, next_status=next_status, actor_id=current_admin.id)
    if next_status == "published":
        _validate_testimonial_publish_fields(testimonial)
    db.add(testimonial)
    return await _refresh_load_and_audit(
        db,
        testimonial,
        testimonial_crud.get_testimonial_by_id,
        request=request,
        current_admin=current_admin,
        action="testimonial.update",
        target_type="testimonial",
        old_value=old_value,
    )


@router.post("/testimonials/{testimonial_id}/submit", response_model=TestimonialOut)
async def submit_testimonial_for_review(
    testimonial_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.submit_review")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    _enforce_content_edit_access(current_admin, testimonial, "testimonial")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=testimonial,
        loader=testimonial_crud.get_testimonial_by_id,
        permission_prefix="testimonial",
        next_status=ContentWorkflowStatus.PENDING_REVIEW.value,
        action="testimonial.submit_review",
        target_type="testimonial",
        required_permission="testimonial.submit_review",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/testimonials/{testimonial_id}/approve", response_model=TestimonialOut)
async def approve_testimonial(
    testimonial_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.approve")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=testimonial,
        loader=testimonial_crud.get_testimonial_by_id,
        permission_prefix="testimonial",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="testimonial.approve",
        target_type="testimonial",
        validator=_validate_testimonial_publish_fields,
        required_permission="testimonial.approve",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/testimonials/{testimonial_id}/reject", response_model=TestimonialOut)
async def reject_testimonial(
    testimonial_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.reject")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=testimonial,
        loader=testimonial_crud.get_testimonial_by_id,
        permission_prefix="testimonial",
        next_status=ContentWorkflowStatus.REJECTED.value,
        action="testimonial.reject",
        target_type="testimonial",
        required_permission="testimonial.reject",
        allowed_current_statuses={ContentWorkflowStatus.PENDING_REVIEW.value},
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/testimonials/{testimonial_id}/publish", response_model=TestimonialOut)
async def publish_testimonial(
    testimonial_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.publish")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=testimonial,
        loader=testimonial_crud.get_testimonial_by_id,
        permission_prefix="testimonial",
        next_status=ContentWorkflowStatus.PUBLISHED.value,
        action="testimonial.publish",
        target_type="testimonial",
        validator=_validate_testimonial_publish_fields,
        required_permission="testimonial.publish",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.post("/testimonials/{testimonial_id}/archive", response_model=TestimonialOut)
async def archive_testimonial(
    testimonial_id: int,
    request: Request,
    payload: ContentWorkflowActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.archive")),
    _csrf: None = Depends(require_csrf),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _transition_content_status(
        db,
        request=request,
        current_admin=current_admin,
        instance=testimonial,
        loader=testimonial_crud.get_testimonial_by_id,
        permission_prefix="testimonial",
        next_status=ContentWorkflowStatus.ARCHIVED.value,
        action="testimonial.archive",
        target_type="testimonial",
        required_permission="testimonial.archive",
        allowed_current_statuses={
            ContentWorkflowStatus.DRAFT.value,
            ContentWorkflowStatus.PENDING_REVIEW.value,
            ContentWorkflowStatus.PUBLISHED.value,
            ContentWorkflowStatus.REJECTED.value,
        },
        audit_context={"reason": payload.reason} if payload and payload.reason else None,
    )


@router.delete("/testimonials/{testimonial_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_testimonial(
    testimonial_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("testimonial.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _delete_and_audit(
        db,
        testimonial,
        request=request,
        current_admin=current_admin,
        action="testimonial.delete",
        target_type="testimonial",
    )


@router.get("/site-settings", response_model=list[SiteSettingOut])
async def list_admin_site_settings(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("site_setting.read")),
) -> list[SiteSettingOut]:
    return await site_settings_crud.get_site_settings(db)


@router.post("/site-settings", response_model=SiteSettingOut, status_code=status.HTTP_201_CREATED)
async def create_site_setting(
    payload: SiteSettingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("site_setting.create")),
    _write_guard: None = Depends(require_admin_api_key),
) -> SiteSettingOut:
    setting = site_settings_crud.build_site_setting(payload)
    db.add(setting)
    await _commit_with_conflict(db)
    refreshed = await site_settings_crud.get_site_setting_by_key(db, setting.key)
    if refreshed is None:
      raise _not_found("Site setting not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="site_setting.create",
        target_type="site_setting",
        target_id=refreshed.key,
        old_value=None,
        new_value=refreshed,
    )
    return refreshed


@router.get("/site-settings/{setting_key}", response_model=SiteSettingOut)
async def get_admin_site_setting(
    setting_key: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("site_setting.read")),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    return setting


@router.put("/site-settings/{setting_key}", response_model=SiteSettingOut)
async def update_site_setting(
    setting_key: str,
    payload: SiteSettingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("site_setting.update")),
    _write_guard: None = Depends(require_admin_api_key),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    old_value = serialize_for_audit(setting)
    site_settings_crud.apply_site_setting_update(setting, payload)
    db.add(setting)
    await _commit_with_conflict(db)
    next_key = payload.key if isinstance(payload.key, str) and payload.key.strip() else setting.key
    refreshed = await site_settings_crud.get_site_setting_by_key(db, next_key)
    if refreshed is None:
        raise _not_found("Site setting not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="site_setting.update",
        target_type="site_setting",
        target_id=refreshed.key,
        old_value=old_value,
        new_value=refreshed,
    )
    return refreshed


@router.delete("/site-settings/{setting_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site_setting(
    setting_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("site_setting.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    return await _delete_and_audit(
        db,
        setting,
        request=request,
        current_admin=current_admin,
        action="site_setting.delete",
        target_type="site_setting",
    )


@router.get("/media", response_model=list[MediaOut])
async def list_admin_media(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("media.read")),
) -> list[MediaOut]:
    return await media_crud.get_media_items(db)


@router.post("/media/upload", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("media.create")),
    _csrf: None = Depends(require_csrf),
) -> MediaOut:
    content, mime_type, extension = await _sanitize_uploaded_image(file)
    stored_name = f"{uuid4().hex}.{extension}"
    stored_path = uploads_dir / stored_name
    stored_path.write_bytes(content)

    media = media_crud.build_media_item(
        MediaCreate(
            url=_build_media_url(request, stored_name),
            alt_text=alt_text,
            storage_key=stored_name,
            file_size=len(content),
            mime_type=mime_type,
        )
    )
    db.add(media)
    return await _refresh_load_and_audit(
        db,
        media,
        media_crud.get_media_item_by_id,
        request=request,
        current_admin=current_admin,
        action="media.create",
        target_type="media",
    )


@router.post("/media", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def create_media(
    payload: MediaCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("media.create")),
    _write_guard: None = Depends(require_admin_api_key),
) -> MediaOut:
    media = media_crud.build_media_item(payload)
    db.add(media)
    return await _refresh_load_and_audit(
        db,
        media,
        media_crud.get_media_item_by_id,
        request=request,
        current_admin=current_admin,
        action="media.create",
        target_type="media",
    )


@router.get("/media/{media_id}", response_model=MediaOut)
async def get_admin_media(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("media.read")),
) -> MediaOut:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    return media


@router.put("/media/{media_id}", response_model=MediaOut)
async def update_media(
    media_id: int,
    payload: MediaUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("media.update")),
    _write_guard: None = Depends(require_admin_api_key),
) -> MediaOut:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    old_value = serialize_for_audit(media)
    media_crud.apply_media_item_update(media, payload)
    db.add(media)
    return await _refresh_load_and_audit(
        db,
        media,
        media_crud.get_media_item_by_id,
        request=request,
        current_admin=current_admin,
        action="media.update",
        target_type="media",
        old_value=old_value,
    )


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("media.delete")),
    _write_guard: None = Depends(require_admin_api_key),
) -> Response:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    return await _delete_and_audit(
        db,
        media,
        request=request,
        current_admin=current_admin,
        action="media.delete",
        target_type="media",
    )
