# app/permissions.py
from sqlalchemy import select

from app.config import OWNER_TELEGRAM_ID
from app.db import SessionLocal
from app.models import User


async def get_or_create_user(tg_id: int) -> User:
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.tg_id == tg_id))
        user = res.scalar_one_or_none()
        if user:
            return user

        role = "owner" if tg_id == OWNER_TELEGRAM_ID else "staff"
        user = User(tg_id=tg_id, role=role)

        if role == "owner":
            user.can_generate = True
            user.can_edit = True
            user.can_sandbox = True
            user.can_manage_clients = True
            user.can_manage_settings = True

        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user