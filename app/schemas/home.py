from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional
from app.schemas.blog import BlogPostOut

class HomeResponse(BaseModel):
    blogPosts: List[BlogPostOut]
    # Add other homepage fields as needed
