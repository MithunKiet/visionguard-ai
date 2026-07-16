"""
public_id <-> internal integer id resolution helpers.

Every table now has an internal auto-increment `id` (never exposed) and a
`public_id` (UUID string, used for all API/JWT/cross-module communication).
Entities and services deal exclusively in public_id strings; only repository
code at the literal SQL boundary needs the internal integer to read/write FK
columns. These helpers keep that translation a one-liner instead of a
hand-rolled `select(...).where(...)` at every call site.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def to_pk(db: AsyncSession, model, public_id: str | None) -> int | None:
    """Resolve a public_id to the internal integer id. None in, None out."""
    if public_id is None:
        return None
    return await db.scalar(select(model.id).where(model.public_id == public_id))


async def to_public_id(db: AsyncSession, model, internal_id: int | None) -> str | None:
    """Resolve an internal integer id to its public_id. None in, None out."""
    if internal_id is None:
        return None
    return await db.scalar(select(model.public_id).where(model.id == internal_id))


async def to_pks(db: AsyncSession, model, public_ids: list[str]) -> list[int]:
    if not public_ids:
        return []
    rows = await db.execute(select(model.id).where(model.public_id.in_(public_ids)))
    return [r[0] for r in rows.all()]
