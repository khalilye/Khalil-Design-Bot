# app/keyboards.py
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_owner: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 العملاء", callback_data="clients_menu")          # سنبنيها لاحقاً
    kb.button(text="📂 الأقسام الديناميكية", callback_data="sections_user_root")  # لاحقاً
    kb.button(text="🎲 القسم الحر", callback_data="free_menu")         # لاحقاً

    if is_owner:
        kb.button(text="⚙️ الإعدادات (إدارة)", callback_data="settings_menu")

    kb.adjust(1)
    return kb.as_markup()