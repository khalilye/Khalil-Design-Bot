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
from handlers.clients_user import router as clients_user_router
from handlers.admin_clients import router as admin_clients_router

from app.webserver import start_web_server  # <- مهم


async def main():
    logging.basicConfig(level=logging.INFO)

    # تهيئة قاعدة البيانات (إنشاء الجداول إن لم تكن موجودة)
    await init_db()

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # روترات البوت
    dp.include_router(start_router)
    dp.include_router(nav_router)

    # لوحات الإدارة
    dp.include_router(admin_settings_router)
    dp.include_router(admin_staff_router)
    dp.include_router(admin_models_router)
    dp.include_router(admin_clients_router)

    # قسم العملاء (واجهة المستخدم - حالياً Placeholder)
    dp.include_router(clients_user_router)

    # نشغّل السيرفر الصغير + البوت معاً
    bot_task = asyncio.create_task(dp.start_polling(bot))
    web_task = asyncio.create_task(start_web_server())

    # ننتظر المهمتين معاً
    await asyncio.gather(bot_task, web_task)


if __name__ == "__main__":
    asyncio.run(main())
