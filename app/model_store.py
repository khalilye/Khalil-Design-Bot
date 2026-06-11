# app/model_store.py
from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ModelCatalog


async def list_models(kind: str, enabled_only: bool = True) -> list[ModelCatalog]:
    async with SessionLocal() as s:
        q = select(ModelCatalog).where(ModelCatalog.kind == kind)
        if enabled_only:
            q = q.where(ModelCatalog.enabled == True)  # noqa
        q = q.order_by(ModelCatalog.enabled.desc(), ModelCatalog.model_id.asc())
        res = await s.execute(q)
        return list(res.scalars().all())


async def get_model_by_id(row_id: int) -> ModelCatalog | None:
    async with SessionLocal() as s:
        res = await s.execute(select(ModelCatalog).where(ModelCatalog.id == row_id))
        return res.scalar_one_or_none()


async def add_model(kind: str, model_id: str, enabled: bool = True) -> ModelCatalog:
    model_id = (model_id or "").strip()
    async with SessionLocal() as s:
        m = ModelCatalog(kind=kind, model_id=model_id, enabled=enabled)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def toggle_model(row_id: int) -> ModelCatalog | None:
    async with SessionLocal() as s:
        res = await s.execute(select(ModelCatalog).where(ModelCatalog.id == row_id))
        m = res.scalar_one_or_none()
        if not m:
            return None
        m.enabled = not bool(m.enabled)
        await s.commit()
        await s.refresh(m)
        return m


async def delete_model(row_id: int) -> bool:
    async with SessionLocal() as s:
        res = await s.execute(select(ModelCatalog).where(ModelCatalog.id == row_id))
        m = res.scalar_one_or_none()
        if not m:
            return False
        await s.delete(m)
        await s.commit()
        return True