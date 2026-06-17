# handlers/admin_settings.py
from io import BytesIO

from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.permissions import get_or_create_user
from app.openrouter import fetch_available_models

router = Router()


def _settings_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍💼 إدارة الموظفين", callback_data="admin_staff_menu")
    kb.button(text="🧠 إدارة الموديلات", callback_data="admin_models_menu")
    kb.button(text="🗂️ إدارة العملاء", callback_data="admin_clients_menu")
    kb.button(text="📂 إدارة الأقسام والنماذج", callback_data="admin_sections_menu")
    kb.button(text="⚙️ إعدادات القسم الحر", callback_data="free_settings_menu")
    kb.button(text="🔍 استعلام موديلات OpenRouter", callback_data="admin_openrouter_models")
    kb.button(text="🏠 الرئيسية", callback_data="nav_home")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "settings_menu")
async def settings_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية الدخول إلى الإعدادات.", show_alert=True)
        return

    text = "إعدادات النظام (لوحة الإدارة):"
    try:
        await c.message.edit_text(text, reply_markup=_settings_menu_kb())
    except Exception:
        await c.message.answer(text, reply_markup=_settings_menu_kb())
    await c.answer()


@router.callback_query(F.data == "admin_openrouter_models")
async def admin_openrouter_models(c: CallbackQuery):
    """
    يستعلم عن قائمة الموديلات من OpenRouter ويرسلها في ملف نصي.
    لا يتم حفظ أي موديل في قاعدة البيانات، الهدف فقط الاطلاع والاختيار اليدوي.
    """
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية استعلام الموديلات.", show_alert=True)
        return

    try:
        models = await fetch_available_models()
    except Exception as e:
        await c.message.answer(f"فشل استعلام الموديلات من OpenRouter:\n{e}")
        await c.answer()
        return

    if not models:
        await c.message.answer("لم يتم العثور على موديلات من OpenRouter.")
        await c.answer()
        return

    # نبني ملف نصي يحتوي سطر لكل موديل: فقط الـ id (كما تحتاجه لإضافته في إدارة الموديلات)
    lines = []
    for m in models:
        mid = m.get("id", "")
        if mid:
            lines.append(mid)

    txt = "\n".join(lines)
    buf = BytesIO(txt.encode("utf-8"))
    doc = BufferedInputFile(buf.getvalue(), filename="openrouter_models.txt")

    await c.message.answer_document(
        document=doc,
        caption=(
            "هذه قائمة الموديلات المتاحة حالياً من OpenRouter (id لكل موديل في سطر).\n\n"
            "يمكنك اختيار الموديلات المناسبة (نسخ الاسم كما هو) ثم إضافتها يدوياً في:\n"
            "🧠 إدارة الموديلات."
        ),
    )
    await c.answer()
