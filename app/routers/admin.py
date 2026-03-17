from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from typing import Any, Awaitable, Callable

from jose import JWTError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import admin as admin_crud
from app.crud import blog as blog_crud
from app.crud import media as media_crud
from app.crud import navigation as navigation_crud
from app.crud import page as page_crud
from app.crud import pricing as pricing_crud
from app.crud import site_settings as site_settings_crud
from app.crud import testimonial as testimonial_crud
from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import AdminUser
from app.schemas import (
    AdminAccessTokenResponse,
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


@router.post("/login", response_model=AdminTokenResponse)
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


@router.post("/refresh", response_model=AdminAccessTokenResponse)
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


@router.get("/me", response_model=AdminUserOut)
async def get_admin_me(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminUserOut:
    return current_admin


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


@router.post(
    "/site-settings",
    response_model=SiteSettingOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_site_setting(
    payload: SiteSettingCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = site_settings_crud.build_site_setting(payload)
    db.add(setting)
    return await _refresh_and_load(db, setting, site_settings_crud.get_site_setting_by_id)


@router.get("/site-settings/{setting_id}", response_model=SiteSettingOut)
async def get_admin_site_setting(
    setting_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_id(db, setting_id)
    if setting is None:
        raise _not_found("Site setting not found")
    return setting


@router.put("/site-settings/{setting_id}", response_model=SiteSettingOut)
async def update_site_setting(
    setting_id: int,
    payload: SiteSettingUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> SiteSettingOut:
    setting = await site_settings_crud.get_site_setting_by_id(db, setting_id)
    if setting is None:
        raise _not_found("Site setting not found")
    site_settings_crud.apply_site_setting_update(setting, payload)
    db.add(setting)
    return await _refresh_and_load(db, setting, site_settings_crud.get_site_setting_by_id)


@router.delete("/site-settings/{setting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site_setting(
    setting_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Response:
    setting = await site_settings_crud.get_site_setting_by_id(db, setting_id)
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
