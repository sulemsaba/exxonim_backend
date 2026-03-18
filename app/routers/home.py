from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.home import HomeResponse
from app.crud import blog as blog_crud

router = APIRouter()

@router.get("/home", response_model=HomeResponse)
async def get_home_data(db: AsyncSession = Depends(get_db)):
    featured_posts = await blog_crud.get_featured_posts(db)
    return {"blogPosts": featured_posts}
