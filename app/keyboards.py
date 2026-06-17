# app/keyboards.py
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_owner: bool, has_free: bool):
    kb = InlineKeyboardBuilder()

    # قسم العملاء
    kb.button(text="👥 العملاء", callback_data="clients_menu")

    # القسم الحر (الاستخدام) - يظهر فقط إذا كان للمستخدم صلاحية sandbox
    if has_free:
        kb.button(text="🎲 القسم الحر", callback_data="free_menu")

    # لوحة الإدارة
    if is_owner:
        kb.button(text="⚙️ الإعدادات (إدارة)", callback_data="settings_menu")

    kb.adjust(1)
    return kb.as_markup()
