# handlers/free_settings.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.permissions import get_or_create_user
from app.db import SessionLocal
from app.models import User, ModelCatalog
from app.model_store import list_models, get_model_by_id

router = Router()


def _free_settings_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🧠 موديل النص (القسم الحر)", callback_data="free_settings_text")
    kb.button(text="🖼️ موديل الصور (القسم الحر)", callback_data="free_settings_image")
    kb.button(text="⬅️ رجوع للإعدادات (إدارة)", callback_data="settings_menu")
    kb.adjust(1)
    return kb.as_markup()


def _free_models_kb(kind: str, rows):
    kb = InlineKeyboardBuilder()
    for m in rows:
        kb.button(
            text=m.model_id,
            callback_data=f"free_set_model:{kind}:{m.id}",
        )
    kb.button(text="⬅️ رجوع لإعدادات القسم الحر", callback_data="free_settings_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "free_settings_menu")
async def free_settings_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)

    # إعدادات القسم الحر تعتبر جزءاً من الإدارة
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإعدادات القسم الحر.", show_alert=True)
        return

    text = (
        "⚙️ إعدادات القسم الحر:\n\n"
        "يمكنك هنا اختيار:\n"
        "- موديل النص الذي يُستخدم في توليد النصوص الحرّة.\n"
        "- موديل الصور الذي يُستخدم في توليد/تعديل الصور الحرّة.\n\n"
        "الإعدادات تُحفظ لحسابك أنت."
    )
    try:
        await c.message.edit_text(text, reply_markup=_free_settings_menu_kb())
    except Exception:
        await c.message.answer(text, reply_markup=_free_settings_menu_kb())
    await c.answer()


@router.callback_query(F.data == "free_settings_text")
async def free_settings_text(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإعدادات القسم الحر.", show_alert=True)
        return

    rows = await list_models("text", enabled_only=True)
    text = "اختر موديل النص الذي تريد استخدامه في القسم الحر:"
    if not rows:
        text += "\n\nلا توجد موديلات نص مفعّلة حالياً. أضفها من '🧠 إدارة الموديلات'."

    try:
        await c.message.edit_text(text, reply_markup=_free_models_kb("text", rows))
    except Exception:
        await c.message.answer(text, reply_markup=_free_models_kb("text", rows))
    await c.answer()


@router.callback_query(F.data == "free_settings_image")
async def free_settings_image(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإعدادات القسم الحر.", show_alert=True)
        return

    rows = await list_models("image", enabled_only=True)
    text = "اختر موديل الصور الذي تريد استخدامه في القسم الحر:"
    if not rows:
        text += "\n\nلا توجد موديلات صور مفعّلة حالياً. أضفها من '🧠 إدارة الموديلات'."

    try:
        await c.message.edit_text(text, reply_markup=_free_models_kb("image", rows))
    except Exception:
        await c.message.answer(text, reply_markup=_free_models_kb("image", rows))
    await c.answer()


@router.callback_query(F.data.startswith("free_set_model:"))
async def free_set_model(c: CallbackQuery):
    _, kind, row_id_s = c.data.split(":")
    row_id = int(row_id_s)

    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإعدادات القسم الحر.", show_alert=True)
        return

    row = await get_model_by_id(row_id)
    if not row or not row.enabled or row.kind != kind:
        await c.answer("هذا الموديل غير متاح.", show_alert=True)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.id == user.id))
        db_user = res.scalar_one_or_none()
        if not db_user:
            await c.answer("لم يتم العثور على المستخدم في قاعدة البيانات.", show_alert=True)
            return

        if kind == "text":
            db_user.text_model = row.model_id
        else:
            db_user.image_model = row.model_id

        await s.commit()

    await c.answer("تم حفظ إعدادات القسم الحر لحسابك.")
    await free_settings_menu(c)
