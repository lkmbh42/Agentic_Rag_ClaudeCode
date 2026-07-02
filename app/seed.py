"""Idempotent dev seed: a default department, an admin user, and a sample
collection so the running stack is immediately usable.

    docker compose -f docker-compose.dev.yml exec backend python -m app.seed

Admin credentials come from SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD (env), with
safe dev defaults. Never run with default credentials in production.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.collection import Collection
from app.models.department import Department
from app.models.enums import Role
from app.models.user import User

ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "admin-pass-123")


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        dept = (
            await db.execute(select(Department).where(Department.name == "General"))
        ).scalar_one_or_none()
        if dept is None:
            dept = Department(name="General")
            db.add(dept)
            await db.flush()

        admin = (
            await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one_or_none()
        if admin is None:
            db.add(
                User(
                    email=ADMIN_EMAIL,
                    hashed_password=hash_password(ADMIN_PASSWORD),
                    role=Role.ADMIN,
                    department_id=dept.id,
                )
            )

        exists = (
            await db.execute(select(Collection).where(Collection.name == "Sample"))
        ).scalar_one_or_none()
        if exists is None:
            db.add(Collection(name="Sample", description="Seed collection",
                              department_id=dept.id))

        await db.commit()
    print(f"seed complete: admin={ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(seed())
