# app/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url
from app.config import DATABASE_URL
from app.models import Base

# تحليل نوع قاعدة البيانات من DATABASE_URL
url = make_url(DATABASE_URL)

if url.get_backend_name().startswith("postgresql"):
    # Supabase + PgBouncer → إلغاء كاش الـ prepared statements
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"statement_cache_size": 0},
    )
else:
    # للـ SQLite محلياً أو أي شيء آخر
    engine = create_async_engine(DATABASE_URL, echo=False)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
