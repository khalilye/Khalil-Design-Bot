# handlers/admin_settings.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.permissions import get_or_create_user

router = Router()


def _settings_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍💼 إدارة الموظفين", callback_data="admin_staff_menu")
    kb.button(text="🧠 إدارة الموديلات", callback_data="admin_models_menu")
    kb.button(text="🗂️ إدارة العملاء", callback_data="admin_clients_menu")
    kb.button(text="📂 إدارة الأقسام والنماذج", callback_data="admin_sections_menu")
    kb.button(text="🏠 الرئيسية", callback_data="nav_home")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "settings_menu")
async def settings_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية الدخول إلى الإعدادات.", show_alert=True)
        return

    try:
        await c.message.edit_text(
            "إعدادات النظام (لوحة الإدارة):",
            reply_markup=_settings_menu_kb(),
        )
    except Exception:
        await c.message.answer(
            "إعدادات النظام (لوحة الإدارة):",
            reply_markup=_settings_menu_kb(),
        )
    await c.answer()
