from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, Awaitable, Callable

from jose import JWTError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import admin as admin_crud
from app.crud import blog as blog_crud
from app.crud import consultation as consultation_crud
from app.crud import job as job_crud
from app.crud import media as media_crud
from app.crud import navigation as navigation_crud
from app.crud import page as page_crud
from app.crud import pricing as pricing_crud
from app.crud import site_settings as site_settings_crud
from app.crud import testimonial as testimonial_crud
from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import AdminUser, BlogPost, Page, SiteSetting
from app.schemas import (
    AdminAccessTokenResponse,
    AdminDashboardSummary,
    AdminLoginRequest,
    AdminRefreshRequest,
    AdminTokenResponse,
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
    TestimonialCreate,
    TestimonialOut,
    TestimonialUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])
uploads_dir = Path(__file__).resolve().parents[2] / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)


def _conflict(detail: str = "Resource conflict") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


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
    if hasattr(instance, "url") and isinstance(instance.url, str):
        filename = instance.url.rsplit("/", 1)[-1]
        local_file = uploads_dir / filename
        if "/uploads/" in instance.url and local_file.exists():
            local_file.unlink()
    await db.delete(instance)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _refresh_and_load(
    db: AsyncSession,
    instance: Any,
    loader: Callable[[AsyncSession, int], Awaitable[Any]],
) -> Any:
    await db.flush()
    identifier = instance.id
    await _commit_with_conflict(db)
    return await loader(db, identifier)


def _build_token_response(admin: AdminUser) -> AdminTokenResponse:
    access_token = create_access_token(
        subject=str(admin.id),
        extra_claims={"token_type": "access", "email": admin.email},
    )
    refresh_token = create_refresh_token(
        subject=str(admin.id),
        extra_claims={"token_type": "refresh", "email": admin.email},
    )
    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        admin=admin,
    )


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


def _dashboard_status_for_post(post: BlogPost) -> str:
    if post.is_published:
        return "published"

    if post.published_at is not None:
        comparison_now = datetime.now(post.published_at.tzinfo or timezone.utc)
        if post.published_at > comparison_now:
            return "scheduled"

    return "draft"


def _dashboard_status_for_page(page: Page) -> str:
    return "published" if page.is_published else "draft"


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
    if status == "draft":
        return 0
    if status == "scheduled":
        return 1
    return 2


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
                "title": "Consultations waiting for follow-up",
                "message": f"{len(pending_consultations)} consultation requests are still pending review.",
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


@router.post("/auth/login", response_model=AdminTokenResponse)
async def login_admin(
    payload: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminTokenResponse:
    admin = await admin_crud.authenticate_admin(
        db,
        email=payload.email,
        password=payload.password,
    )
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _build_token_response(admin)


@router.post("/auth/refresh", response_model=AdminAccessTokenResponse)
async def refresh_admin_access_token(
    payload: AdminRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminAccessTokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    if token_payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    subject = token_payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    admin = await admin_crud.get_admin_by_id(db, int(subject))
    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )

    access_token = create_access_token(
        subject=str(admin.id),
        extra_claims={"token_type": "access", "email": admin.email},
    )
    return AdminAccessTokenResponse(access_token=access_token)


@router.get("/auth/me", response_model=AdminUserOut)
async def get_admin_me(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminUserOut:
    return current_admin


@router.get("/staff", response_model=list[AdminUserOut])
async def list_admin_staff(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[AdminUserOut]:
    return await admin_crud.get_all_admins(db)


@router.get("/dashboard/summary", response_model=AdminDashboardSummary)
async def get_admin_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
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
                "label": "Pending Consultations",
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
    _: AdminUser = Depends(get_current_admin),
) -> list[JobOut]:
    return await job_crud.get_all_jobs(db)


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> JobOut:
    job = job_crud.build_job(payload)
    db.add(job)
    return await _refresh_and_load(db, job, job_crud.get_job_by_id)


@router.get("/jobs/{slug}", response_model=JobOut)
async def get_admin_job(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> JobOut:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    return job


@router.put("/jobs/{slug}", response_model=JobOut)
async def update_job(
    slug: str,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> JobOut:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    job_crud.apply_job_update(job, payload)
    db.add(job)
    return await _refresh_and_load(db, job, job_crud.get_job_by_id)


@router.delete("/jobs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    job = await job_crud.get_job_by_slug(db, slug)
    if job is None:
        raise _not_found("Job not found")
    return await _delete_and_commit(db, job)


@router.get("/consultations", response_model=ConsultationListResponse)
async def list_admin_consultations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_value: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> ConsultationListResponse:
    items, total = await consultation_crud.get_consultations(
        db,
        page=page,
        limit=limit,
        status=status_value,
        search=search,
        include_history=True,
    )
    return ConsultationListResponse.build(
        items=[ConsultationOut.model_validate(item) for item in items],
        page=page,
        limit=limit,
        total=total,
    )


@router.get("/consultations/{consultation_id}", response_model=ConsultationOut)
async def get_admin_consultation(
    consultation_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> ConsultationOut:
    consultation = await consultation_crud.get_consultation_by_id(
        db,
        consultation_id,
        include_history=True,
    )
    if consultation is None:
        raise _not_found("Consultation not found")
    return consultation


@router.put("/consultations/{consultation_id}", response_model=ConsultationOut)
async def update_admin_consultation(
    consultation_id: int,
    payload: ConsultationUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> ConsultationOut:
    consultation = await consultation_crud.get_consultation_by_id(
        db,
        consultation_id,
        include_history=True,
    )
    if consultation is None:
        raise _not_found("Consultation not found")

    if payload.assigned_to is not None and await admin_crud.get_admin_by_id(db, payload.assigned_to) is None:
        raise _not_found("Assigned admin not found")

    old_status = consultation.status
    consultation_crud.apply_consultation_update(consultation, payload)
    db.add(consultation)
    await db.flush()

    next_status = payload.status or old_status
    if next_status != old_status:
        db.add(
            consultation_crud.build_status_history(
                consultation_id=consultation.id,
                old_status=old_status,
                new_status=next_status,
                changed_by=current_admin.id,
                comment=payload.comment,
            )
        )

    await _commit_with_conflict(db)
    refreshed = await consultation_crud.get_consultation_by_id(
        db,
        consultation_id,
        include_history=True,
    )
    if refreshed is None:
        raise _not_found("Consultation not found")
    return refreshed


@router.get("/blog/posts", response_model=list[BlogPostOut])
async def list_admin_blog_posts(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[BlogPostOut]:
    return await blog_crud.get_all_posts(db)


@router.post("/blog/posts", response_model=BlogPostOut, status_code=status.HTTP_201_CREATED)
async def create_blog_post(
    payload: BlogPostCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogPostOut:
    if payload.category_id is not None and await blog_crud.get_category_by_id(
        db, payload.category_id
    ) is None:
        raise _not_found("Category not found")
    if payload.author_id is not None and await blog_crud.get_author_by_id(
        db, payload.author_id
    ) is None:
        raise _not_found("Author not found")

    if _is_publish_request(
        is_published=payload.is_published,
        published_at=payload.published_at,
    ):
        _validate_blog_publish_fields(
            title=payload.title,
            slug=payload.slug,
            excerpt=payload.excerpt,
            content=payload.content,
            category_id=payload.category_id,
            author_id=payload.author_id,
            featured_image=payload.featured_image,
        )

    post = blog_crud.build_post(payload)
    db.add(post)
    return await _refresh_and_load(db, post, blog_crud.get_post_by_id)


@router.get("/blog/posts/{post_id}", response_model=BlogPostOut)
async def get_admin_blog_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return post


@router.put("/blog/posts/{post_id}", response_model=BlogPostOut)
async def update_blog_post(
    post_id: int,
    payload: BlogPostUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogPostOut:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data and update_data["category_id"] is not None:
        if await blog_crud.get_category_by_id(db, update_data["category_id"]) is None:
            raise _not_found("Category not found")
    if "author_id" in update_data and update_data["author_id"] is not None:
        if await blog_crud.get_author_by_id(db, update_data["author_id"]) is None:
            raise _not_found("Author not found")

    next_is_published = update_data.get("is_published", post.is_published)
    next_published_at = update_data.get("published_at", post.published_at)
    if _is_publish_request(
        is_published=next_is_published,
        published_at=next_published_at,
    ):
        _validate_blog_publish_fields(
            title=update_data.get("title", post.title),
            slug=update_data.get("slug", post.slug),
            excerpt=update_data.get("excerpt", post.excerpt),
            content=update_data.get("content", post.content),
            category_id=update_data.get("category_id", post.category_id),
            author_id=update_data.get("author_id", post.author_id),
            featured_image=update_data.get("featured_image", post.featured_image),
        )

    blog_crud.apply_post_update(post, payload)
    db.add(post)
    return await _refresh_and_load(db, post, blog_crud.get_post_by_id)


@router.delete("/blog/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    post = await blog_crud.get_post_by_id(db, post_id)
    if post is None:
        raise _not_found("Post not found")
    return await _delete_and_commit(db, post)


@router.get("/blog/categories", response_model=list[BlogCategoryOut])
async def list_admin_blog_categories(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[BlogCategoryOut]:
    return await blog_crud.get_all_categories(db)


@router.post(
    "/blog/categories",
    response_model=BlogCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_blog_category(
    payload: BlogCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogCategoryOut:
    category = blog_crud.build_category(payload)
    db.add(category)
    return await _refresh_and_load(db, category, blog_crud.get_category_by_id)


@router.put("/blog/categories/{category_id}", response_model=BlogCategoryOut)
async def update_blog_category(
    category_id: int,
    payload: BlogCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogCategoryOut:
    category = await blog_crud.get_category_by_id(db, category_id)
    if category is None:
        raise _not_found("Category not found")
    blog_crud.apply_category_update(category, payload)
    db.add(category)
    return await _refresh_and_load(db, category, blog_crud.get_category_by_id)


@router.delete("/blog/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    category = await blog_crud.get_category_by_id(db, category_id)
    if category is None:
        raise _not_found("Category not found")
    return await _delete_and_commit(db, category)


@router.get("/blog/authors", response_model=list[BlogAuthorOut])
async def list_admin_blog_authors(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[BlogAuthorOut]:
    return await blog_crud.get_all_authors(db)


@router.post(
    "/blog/authors",
    response_model=BlogAuthorOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_blog_author(
    payload: BlogAuthorCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogAuthorOut:
    author = blog_crud.build_author(payload)
    db.add(author)
    return await _refresh_and_load(db, author, blog_crud.get_author_by_id)


@router.put("/blog/authors/{author_id}", response_model=BlogAuthorOut)
async def update_blog_author(
    author_id: int,
    payload: BlogAuthorUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> BlogAuthorOut:
    author = await blog_crud.get_author_by_id(db, author_id)
    if author is None:
        raise _not_found("Author not found")
    blog_crud.apply_author_update(author, payload)
    db.add(author)
    return await _refresh_and_load(db, author, blog_crud.get_author_by_id)


@router.delete("/blog/authors/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_author(
    author_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    author = await blog_crud.get_author_by_id(db, author_id)
    if author is None:
        raise _not_found("Author not found")
    return await _delete_and_commit(db, author)


@router.get("/pages", response_model=list[PageOut])
async def list_admin_pages(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[PageOut]:
    return await page_crud.get_all_pages(db)


@router.post("/pages", response_model=PageOut, status_code=status.HTTP_201_CREATED)
async def create_page(
    payload: PageCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PageOut:
    page = page_crud.build_page(payload)
    db.add(page)
    return await _refresh_and_load(db, page, page_crud.get_page_by_id)


@router.get("/pages/{page_id}", response_model=PageOut)
async def get_admin_page(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return page


@router.put("/pages/{page_id}", response_model=PageOut)
async def update_page(
    page_id: int,
    payload: PageUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PageOut:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    page_crud.apply_page_update(page, payload)
    db.add(page)
    return await _refresh_and_load(db, page, page_crud.get_page_by_id)


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    page = await page_crud.get_page_by_id(db, page_id)
    if page is None:
        raise _not_found("Page not found")
    return await _delete_and_commit(db, page)


@router.get("/navigation", response_model=list[NavigationItemOut])
async def list_admin_navigation(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[NavigationItemOut]:
    return await navigation_crud.get_navigation_tree(db, active_only=None)


@router.post(
    "/navigation",
    response_model=NavigationItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_navigation_item(
    payload: NavigationItemCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
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
    return navigation_crud.serialize_navigation_item(item, {})


@router.get("/navigation/{item_id}", response_model=NavigationItemOut)
async def get_admin_navigation_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> NavigationItemOut:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")
    return navigation_crud.serialize_navigation_item(item, {})


@router.put("/navigation/{item_id}", response_model=NavigationItemOut)
async def update_navigation_item(
    item_id: int,
    payload: NavigationItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> NavigationItemOut:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")

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
    return navigation_crud.serialize_navigation_item(item, {})


@router.delete("/navigation/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_navigation_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    item = await navigation_crud.get_navigation_item_by_id(db, item_id)
    if item is None:
        raise _not_found("Navigation item not found")
    return await _delete_and_commit(db, item)


@router.get("/pricing/plans", response_model=list[PricingPlanOut])
async def list_admin_pricing_plans(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[PricingPlanOut]:
    return await pricing_crud.get_all_pricing_plans(db)


@router.post(
    "/pricing/plans",
    response_model=PricingPlanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pricing_plan(
    payload: PricingPlanCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PricingPlanOut:
    plan = pricing_crud.build_pricing_plan(payload)
    db.add(plan)
    return await _refresh_and_load(db, plan, pricing_crud.get_pricing_plan_by_id)


@router.get("/pricing/plans/{plan_id}", response_model=PricingPlanOut)
async def get_admin_pricing_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PricingPlanOut:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    return plan


@router.put("/pricing/plans/{plan_id}", response_model=PricingPlanOut)
async def update_pricing_plan(
    plan_id: int,
    payload: PricingPlanUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> PricingPlanOut:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    pricing_crud.apply_pricing_plan_update(plan, payload)
    db.add(plan)
    return await _refresh_and_load(db, plan, pricing_crud.get_pricing_plan_by_id)


@router.delete("/pricing/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    plan = await pricing_crud.get_pricing_plan_by_id(db, plan_id)
    if plan is None:
        raise _not_found("Pricing plan not found")
    return await _delete_and_commit(db, plan)


@router.get("/testimonials", response_model=list[TestimonialOut])
async def list_admin_testimonials(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[TestimonialOut]:
    return await testimonial_crud.get_all_testimonials(db)


@router.post(
    "/testimonials",
    response_model=TestimonialOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_testimonial(
    payload: TestimonialCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> TestimonialOut:
    testimonial = testimonial_crud.build_testimonial(payload)
    db.add(testimonial)
    return await _refresh_and_load(
        db,
        testimonial,
        testimonial_crud.get_testimonial_by_id,
    )


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialOut)
async def get_admin_testimonial(
    testimonial_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return testimonial


@router.put("/testimonials/{testimonial_id}", response_model=TestimonialOut)
async def update_testimonial(
    testimonial_id: int,
    payload: TestimonialUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> TestimonialOut:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    testimonial_crud.apply_testimonial_update(testimonial, payload)
    db.add(testimonial)
    return await _refresh_and_load(
        db,
        testimonial,
        testimonial_crud.get_testimonial_by_id,
    )


@router.delete("/testimonials/{testimonial_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_testimonial(
    testimonial_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    testimonial = await testimonial_crud.get_testimonial_by_id(db, testimonial_id)
    if testimonial is None:
        raise _not_found("Testimonial not found")
    return await _delete_and_commit(db, testimonial)


@router.get("/site-settings", response_model=list[SiteSettingOut])
async def list_admin_site_settings(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[SiteSettingOut]:
    return await site_settings_crud.get_site_settings(db)


@router.post("/site-settings", response_model=SiteSettingOut, status_code=status.HTTP_201_CREATED)
async def create_site_setting(
    payload: SiteSettingCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = site_settings_crud.build_site_setting(payload)
    db.add(setting)
    await _commit_with_conflict(db)
    refreshed = await site_settings_crud.get_site_setting_by_key(db, setting.key)
    if refreshed is None:
      raise _not_found("Site setting not found")
    return refreshed


@router.get("/site-settings/{setting_key}", response_model=SiteSettingOut)
async def get_admin_site_setting(
    setting_key: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    return setting


@router.put("/site-settings/{setting_key}", response_model=SiteSettingOut)
async def update_site_setting(
    setting_key: str,
    payload: SiteSettingUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    site_settings_crud.apply_site_setting_update(setting, payload)
    db.add(setting)
    await _commit_with_conflict(db)
    next_key = payload.key if isinstance(payload.key, str) and payload.key.strip() else setting.key
    refreshed = await site_settings_crud.get_site_setting_by_key(db, next_key)
    if refreshed is None:
        raise _not_found("Site setting not found")
    return refreshed


@router.delete("/site-settings/{setting_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site_setting(
    setting_key: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    setting = await site_settings_crud.get_site_setting_by_key(db, setting_key)
    if setting is None:
        raise _not_found("Site setting not found")
    return await _delete_and_commit(db, setting)


@router.get("/media", response_model=list[MediaOut])
async def list_admin_media(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[MediaOut]:
    return await media_crud.get_media_items(db)


@router.post("/media/upload", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> MediaOut:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image uploads are supported",
        )

    suffix = Path(file.filename or "").suffix.lower() or ".bin"
    stored_name = f"{uuid4().hex}{suffix}"
    stored_path = uploads_dir / stored_name
    content = await file.read()
    stored_path.write_bytes(content)

    base_url = str(request.base_url).rstrip("/")
    media = media_crud.build_media_item(
        MediaCreate(
            url=f"{base_url}/uploads/{stored_name}",
            alt_text=alt_text,
            file_size=len(content),
            mime_type=file.content_type,
        )
    )
    db.add(media)
    return await _refresh_and_load(db, media, media_crud.get_media_item_by_id)


@router.post("/media", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def create_media(
    payload: MediaCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> MediaOut:
    media = media_crud.build_media_item(payload)
    db.add(media)
    return await _refresh_and_load(db, media, media_crud.get_media_item_by_id)


@router.get("/media/{media_id}", response_model=MediaOut)
async def get_admin_media(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> MediaOut:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    return media


@router.put("/media/{media_id}", response_model=MediaOut)
async def update_media(
    media_id: int,
    payload: MediaUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> MediaOut:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    media_crud.apply_media_item_update(media, payload)
    db.add(media)
    return await _refresh_and_load(db, media, media_crud.get_media_item_by_id)


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    media = await media_crud.get_media_item_by_id(db, media_id)
    if media is None:
        raise _not_found("Media item not found")
    return await _delete_and_commit(db, media)
