from fastapi import APIRouter

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.blog import router as blog_router
from app.routers.consultations import router as consultations_router
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.media import router as media_router
from app.routers.navigation import router as navigation_router
from app.routers.notifications import router as notifications_router
from app.routers.operations import router as operations_router
from app.routers.pages import router as pages_router
from app.routers.privacy import router as privacy_router
from app.routers.pricing import router as pricing_router
from app.routers.reports import router as reports_router
from app.routers.site_settings import router as site_settings_router
from app.routers.testimonials import router as testimonials_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(operations_router)
api_router.include_router(notifications_router)
api_router.include_router(reports_router)
api_router.include_router(privacy_router)
api_router.include_router(blog_router)
api_router.include_router(consultations_router)
api_router.include_router(jobs_router)
api_router.include_router(pages_router)
api_router.include_router(navigation_router)
api_router.include_router(pricing_router)
api_router.include_router(testimonials_router)
api_router.include_router(site_settings_router)
api_router.include_router(media_router)
