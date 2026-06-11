# app/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import DATABASE_URL
from app.models import Base

# محرك واحد بسيط - SQLAlchemy يختار الدرايفر حسب DATABASE_URL:
# - لو sqlite+aiosqlite → يستخدم aiosqlite
# - لو postgresql:// -> يستخدم psycopg2 (الذي أضفناه في requirements)
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
