from fastapi import APIRouter

from app.routers.admin_consultations import (
    router as admin_consultations_router,
    staff_router,
)
from app.routers.admin import router as admin_router
from app.routers.blog import router as blog_router
from app.routers.health import router as health_router
from app.routers.home import router as home_router
from app.routers.media import router as media_router
from app.routers.navigation import router as navigation_router
from app.routers.pages import router as pages_router
from app.routers.pricing import router as pricing_router
from app.routers.public_consultations import router as public_consultations_router
from app.routers.site_settings import router as site_settings_router
from app.routers.testimonials import router as testimonials_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(admin_router)
api_router.include_router(admin_consultations_router)
api_router.include_router(staff_router)
api_router.include_router(blog_router)
api_router.include_router(pages_router)
api_router.include_router(navigation_router)
api_router.include_router(pricing_router)
api_router.include_router(public_consultations_router)
api_router.include_router(testimonials_router)
api_router.include_router(site_settings_router)
api_router.include_router(media_router)

api_router.include_router(home_router)
