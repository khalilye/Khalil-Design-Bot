# handlers/start.py
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.permissions import get_or_create_user
from app.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(m: Message):
    user = await get_or_create_user(m.from_user.id)

    if user.role != "owner" and not any([
        user.can_generate,
        user.can_edit,
        user.can_sandbox,
        user.can_manage_clients,
        user.can_manage_settings,
    ]):
        await m.answer("حسابك غير مُفعّل بعد. تواصل مع الإدارة لتفعيل صلاحياتك.")
        return

    await m.answer(
        "مرحباً، اختر من القائمة:",
        reply_markup=main_menu(is_owner=(user.role == "owner")),
    )