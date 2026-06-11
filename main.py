# main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import TELEGRAM_BOT_TOKEN
from app.db import init_db

from handlers.start import router as start_router
from handlers.nav import router as nav_router
from handlers.admin_settings import router as admin_settings_router
from handlers.admin_staff import router as admin_staff_router
from handlers.admin_models import router as admin_models_router


async def main():
    logging.basicConfig(level=logging.INFO)

    await init_db()

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(nav_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_staff_router)
    dp.include_router(admin_models_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())