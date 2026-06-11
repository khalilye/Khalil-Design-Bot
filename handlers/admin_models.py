# handlers/admin_models.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.permissions import get_or_create_user
from app.model_store import list_models, add_model, toggle_model, delete_model

router = Router()


class AddModelState(StatesGroup):
    waiting_model_id = State()


def _models_kinds_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🧠 موديلات النصوص", callback_data="admin_models_kind:text")
    kb.button(text="🖼️ موديلات الصور", callback_data="admin_models_kind:image")
    kb.button(text="🎥 موديلات الفيديو", callback_data="admin_models_kind:video")
    kb.button(text="🎧 موديلات الصوت", callback_data="admin_models_kind:audio")
    kb.button(text="⬅️ رجوع", callback_data="settings_menu")
    kb.adjust(1)
    return kb.as_markup()


def _models_list_kb(kind: str, rows):
    kb = InlineKeyboardBuilder()
    for m in rows:
        status = "✅" if m.enabled else "❌"
        kb.button(
            text=f"{status} {m.model_id}",
            callback_data=f"admin_models_toggle:{kind}:{m.id}",
        )
        kb.button(
            text="🗑️ حذف",
            callback_data=f"admin_models_delete:{kind}:{m.id}",
        )
    kb.button(text="➕ إضافة موديل", callback_data=f"admin_models_add:{kind}")
    kb.button(text="⬅️ الأنواع", callback_data="admin_models_menu")
    kb.adjust(2)
    return kb.as_markup()


@router.callback_query(F.data == "admin_models_menu")
async def admin_models_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليس لديك صلاحية إدارة الموديلات.", show_alert=True)
        return

    text = "إدارة موديلات الذكاء الاصطناعي:\nاختر نوع الموديلات:"
    try:
        await c.message.edit_text(text, reply_markup=_models_kinds_kb())
    except Exception:
        await c.message.answer(text, reply_markup=_models_kinds_kb())
    await c.answer()


@router.callback_query(F.data.startswith("admin_models_kind:"))
async def admin_models_kind(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليس لديك صلاحية إدارة الموديلات.", show_alert=True)
        return

    kind = c.data.split(":")[1]
    rows = await list_models(kind, enabled_only=False)

    text = f"موديلات النوع: {kind}\n"
    if not rows:
        text += "لا يوجد موديلات بعد."

    try:
        await c.message.edit_text(text, reply_markup=_models_list_kb(kind, rows))
    except Exception:
        await c.message.answer(text, reply_markup=_models_list_kb(kind, rows))
    await c.answer()


@router.callback_query(F.data.startswith("admin_models_add:"))
async def admin_models_add(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليس لديك صلاحية إدارة الموديلات.", show_alert=True)
        return

    kind = c.data.split(":")[1]
    await state.update_data(kind=kind)
    await state.set_state(AddModelState.waiting_model_id)
    await c.message.answer(
        f"أرسل الآن اسم الموديل كما هو في OpenRouter لنوع: {kind}\n"
        "مثال: openai/gpt-4o",
    )
    await c.answer()


@router.message(AddModelState.waiting_model_id)
async def admin_models_add_model_id(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await m.answer("ليس لديك صلاحية إدارة الموديلات.")
        await state.clear()
        return

    data = await state.get_data()
    kind = data.get("kind")
    model_id = (m.text or "").strip()
    if not model_id:
        await m.answer("الرجاء إرسال اسم موديل صالح.")
        return

    await add_model(kind=kind, model_id=model_id, enabled=True)
    await m.answer(f"تمت إضافة الموديل: {model_id} لنوع: {kind}")
    await state.clear()


@router.callback_query(F.data.startswith("admin_models_toggle:"))
async def admin_models_toggle(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليس لديك صلاحية إدارة الموديلات.", show_alert=True)
        return

    _, kind, row_id_s = c.data.split(":")
    row_id = int(row_id_s)
    m = await toggle_model(row_id)
    if not m:
        await c.answer("الموديل غير موجود.", show_alert=True)
        return

    rows = await list_models(kind, enabled_only=False)
    text = f"موديلات النوع: {kind}\n"
    if not rows:
        text += "لا يوجد موديلات بعد."

    try:
        await c.message.edit_text(text, reply_markup=_models_list_kb(kind, rows))
    except Exception:
        await c.message.answer(text, reply_markup=_models_list_kb(kind, rows))
    await c.answer("تم التحديث.")


@router.callback_query(F.data.startswith("admin_models_delete:"))
async def admin_models_delete(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليس لديك صلاحية إدارة الموديلات.", show_alert=True)
        return

    _, kind, row_id_s = c.data.split(":")
    row_id = int(row_id_s)
    ok = await delete_model(row_id)
    if not ok:
        await c.answer("الموديل غير موجود.", show_alert=True)
        return

    rows = await list_models(kind, enabled_only=False)
    text = f"موديلات النوع: {kind}\n"
    if not rows:
        text += "لا يوجد موديلات بعد."

    try:
        await c.message.edit_text(text, reply_markup=_models_list_kb(kind, rows))
    except Exception:
        await c.message.answer(text, reply_markup=_models_list_kb(kind, rows))
    await c.answer("تم الحذف.")