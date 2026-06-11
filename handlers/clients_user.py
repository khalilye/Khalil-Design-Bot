# handlers/clients_user.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


@router.callback_query(F.data == "clients_menu")
async def clients_menu(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 الرئيسية", callback_data="nav_home")
    kb.adjust(1)

    try:
        await c.message.edit_text(
            "قسم العملاء (لتوليد الأعمال حسب كل عميل) سيتم استكماله في الخطوات القادمة.\n"
            "حالياً يمكنك إضافة وتعديل العملاء من لوحة الإدارة: ⚙️ الإعدادات → 🗂️ إدارة العملاء.",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        await c.message.answer(
            "قسم العملاء (لتوليد الأعمال حسب كل عميل) سيتم استكماله في الخطوات القادمة.\n"
            "حالياً يمكنك إضافة وتعديل العملاء من لوحة الإدارة: ⚙️ الإعدادات → 🗂️ إدارة العملاء.",
            reply_markup=kb.as_markup(),
        )
    await c.answer()
