from __future__ import annotations

from pydantic import BaseModel


class ContentWorkflowActionRequest(BaseModel):
    reason: str | None = None
