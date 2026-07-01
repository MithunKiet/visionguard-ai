"""
Seed the first SUPER_ADMIN user and a default Enterprise.

Usage (run from backend/ directory):
    python -m scripts.seed_super_admin

Or with Docker:
    docker compose exec backend python -m scripts.seed_super_admin

Environment variables read from .env:
    SEED_ENTERPRISE_NAME  (default: "VisionGuard Demo")
    SEED_ENTERPRISE_CODE  (default: "VGD")
    SEED_ADMIN_NAME       (default: "Super Admin")
    SEED_ADMIN_EMAIL      (default: "admin@visionguard.ai")
    SEED_ADMIN_PASSWORD   (default: "Admin@1234")
"""
import asyncio
import os
import sys
import uuid

# Ensure src/ is on path when run as a module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.settings import settings
from src.shared.database.models import Enterprise, User
from src.shared.security.password import hash_password


ENTERPRISE_NAME = os.getenv("SEED_ENTERPRISE_NAME", "VisionGuard Demo")
ENTERPRISE_CODE = os.getenv("SEED_ENTERPRISE_CODE", "VGD")
ADMIN_NAME      = os.getenv("SEED_ADMIN_NAME", "Super Admin")
ADMIN_EMAIL     = os.getenv("SEED_ADMIN_EMAIL", "admin@visionguard.ai")
ADMIN_PASSWORD  = os.getenv("SEED_ADMIN_PASSWORD", "Admin@1234")


async def seed() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Idempotent — skip if enterprise already exists
        existing = await db.execute(
            select(Enterprise).where(Enterprise.code == ENTERPRISE_CODE)
        )
        enterprise = existing.scalar_one_or_none()

        if not enterprise:
            enterprise = Enterprise(
                id=uuid.uuid4(),
                name=ENTERPRISE_NAME,
                code=ENTERPRISE_CODE,
                status="Active",
            )
            db.add(enterprise)
            await db.flush()
            print(f"[seed] Enterprise created: {ENTERPRISE_NAME} ({ENTERPRISE_CODE})")
        else:
            print(f"[seed] Enterprise already exists: {enterprise.name}")

        # Check if admin already exists
        existing_user = await db.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        user = existing_user.scalar_one_or_none()

        if not user:
            user = User(
                id=uuid.uuid4(),
                enterprise_id=enterprise.id,
                name=ADMIN_NAME,
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="SUPER_ADMIN",
                status="Active",
                is_first_login=True,
                setup_completed=False,
            )
            db.add(user)
            await db.commit()
            print(f"[seed] SUPER_ADMIN created: {ADMIN_EMAIL}")
            print(f"[seed] Password: {ADMIN_PASSWORD}  ← change this immediately!")
        else:
            print(f"[seed] Admin already exists: {user.email}")

    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(seed())
