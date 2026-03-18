from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud import blog as blog_crud
import logging
import random

logger = logging.getLogger(__name__)

async def list_home_posts(db: AsyncSession, skip: int, limit: int, featured_on_home: bool):
    try:
        if featured_on_home:
            posts = await blog_crud.get_featured_posts(db, limit=limit)
            return {"posts": posts, "used_fallback": False}
        posts = await blog_crud.get_published_posts(db, skip=skip, limit=limit)
        return {"posts": posts, "used_fallback": False}
    except Exception as exc:
        logger.warning("Primary blog query failed, attempting fallback: %s", exc)
        fallback = await blog_crud.get_featured_posts(db, limit=limit)
        if random.random() < 0.1:
            logger.warning("homepage_fallback_used")
        return {"posts": fallback, "used_fallback": True}
