# app/webserver.py
import os
import asyncio

from aiohttp import web


async def handle_root(request: web.Request):
    """
    مسار بسيط للـ health check من Render.
    يرجع 200 OK.
    """
    return web.Response(text="OK", status=200)


async def start_web_server():
    """
    تشغيل سيرفر HTTP بسيط على البورت الذي يحدده Render في المتغير PORT.
    هذا يخلي Web Service "راضية" عن الخدمة وما توقفها.
    """
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "8000"))  # لو ما في PORT (محلياً) نستخدم 8000
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    # حلقة تبقي السيرفر شغال
    while True:
        await asyncio.sleep(3600)
