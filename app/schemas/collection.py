from __future__ import annotations

import uuid

from pydantic import BaseModel


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    department_id: uuid.UUID | None

    model_config = {"from_attributes": True}
