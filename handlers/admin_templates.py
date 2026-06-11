# handlers/admin_templates.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Section, Template, ModelCatalog
from app.permissions import get_or_create_user
from app.model_store import list_models

router = Router()


class TemplateEditState(StatesGroup):
    adding_name = State()
    editing_name = State()
    editing_prompt = State()


# العمليات المتاحة
OPERATION_CHOICES = [
    ("text_generate", "📝 توليد نص"),
    ("image_generate", "🖼️ توليد صورة"),
    ("image_edit", "✏️ تعديل صورة"),
    ("video_generate", "🎥 توليد فيديو"),
    ("video_edit", "✏️ تعديل فيديو"),
    ("audio_generate", "🎧 توليد صوت"),
]

# نوع الموديل المطلوب لكل عملية
OPERATION_KIND = {
    "text_generate": "text",
    "image_generate": "image",
    "image_edit": "image",
    "video_generate": "video",
    "video_edit": "video",
    "audio_generate": "audio",
}

# متطلبات الملفات
FILE_REQUIREMENT_CHOICES = [
    ("none", "بدون ملفات"),
    ("image_single", "📷 صورة واحدة"),
    ("image_multi", "📷 عدة صور"),
    ("video_single", "🎥 فيديو واحد"),
]


# ============ مساعدات ============

def _templates_list_kb(section_id: int, templates: list[Template]):
    kb = InlineKeyboardBuilder()

    kb.button(
        text="➕ إضافة نموذج جديد",
        callback_data=f"admin_template_add:{section_id}",
    )

    for t in templates:
        status = "✅" if t.is_active else "❌"
        kb.button(
            text=f"{status} {t.name}",
            callback_data=f"admin_template_view:{t.id}",
        )

    kb.button(
        text="⬅️ رجوع للأقسام",
        callback_data="admin_sections_menu",
    )

    kb.adjust(1)
    return kb.as_markup()


def _template_manage_kb(t: Template):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ إعادة تسمية النموذج", callback_data=f"admin_template_rename:{t.id}")
    kb.button(text="🧾 تعديل البرومبت الأساسي", callback_data=f"admin_template_prompt:{t.id}")
    kb.button(text="⚙️ نوع العملية", callback_data=f"admin_template_operation:{t.id}")
    kb.button(text="🧠 اختيار الموديل", callback_data=f"admin_template_model:{t.id}")
    kb.button(text="📎 نوع الملفات المطلوبة", callback_data=f"admin_template_files:{t.id}")
    kb.button(
        text=("🔴 تعطيل النموذج" if t.is_active else "🟢 تفعيل النموذج"),
        callback_data=f"admin_template_toggle:{t.id}",
    )
    kb.button(text="🗑️ حذف النموذج", callback_data=f"admin_template_delete:{t.id}")
    kb.button(
        text="⬅️ رجوع لقائمة النماذج",
        callback_data=f"admin_templates_menu:{t.section_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


async def _render_templates_for_section(c: CallbackQuery, section_id: int):
    async with SessionLocal() as s:
        res_sec = await s.execute(select(Section).where(Section.id == section_id))
        sec = res_sec.scalar_one_or_none()

        res_t = await s.execute(
            select(Template)
            .where(Template.section_id == section_id)
            .order_by(Template.name.asc())
        )
        templates = list(res_t.scalars().all())

    if not sec:
        await c.answer("القسم غير موجود.", show_alert=True)
        return

    text = f"النماذج داخل القسم: {sec.name}\n\n"
    if not templates:
        text += "لا توجد نماذج بعد. أضف نموذجاً جديداً."

    try:
        await c.message.edit_text(text, reply_markup=_templates_list_kb(section_id, templates))
    except Exception:
        await c.message.answer(text, reply_markup=_templates_list_kb(section_id, templates))
    await c.answer()


# ============ عرض قائمة النماذج لقسم معيّن ============

@router.callback_query(F.data.startswith("admin_templates_menu:"))
async def admin_templates_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإدارة النماذج.", show_alert=True)
        return

    section_id = int(c.data.split(":")[1])
    await _render_templates_for_section(c, section_id)


# ============ إضافة نموذج جديد ============

@router.callback_query(F.data.startswith("admin_template_add:"))
async def admin_template_add(c: CallbackQuery, state: FSMContext):
    section_id = int(c.data.split(":")[1])
    await state.update_data(section_id=section_id)
    await state.set_state(TemplateEditState.adding_name)
    await c.message.answer("أرسل الآن اسم النموذج الجديد:")
    await c.answer()


@router.message(TemplateEditState.adding_name)
async def admin_template_add_name(m: Message, state: FSMContext):
    data = await state.get_data()
    section_id = data.get("section_id")
    name = (m.text or "").strip()

    if not name:
        await m.answer("الرجاء إرسال اسم صالح.")
        return

    # ننشئ نموذج بمعلومات افتراضية (سيعدلها لاحقاً من لوحة الإدارة)
    async with SessionLocal() as s:
        # نحتاج موديل افتراضي (أي موديل مفعّل من أي نوع)، إن لم يوجد نتركه 0 (غير صالح)
        res_model = await s.execute(select(ModelCatalog).limit(1))
        model = res_model.scalar_one_or_none()
        model_id = model.id if model else 0

        t = Template(
            name=name,
            section_id=section_id,
            base_prompt="",
            operation="image_generate",  # افتراضي
            model_catalog_id=model_id or 1,  # إن لم يوجد موديلات يجب تعديلها لاحقاً
            file_requirement="none",
            is_active=True,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)

    await m.answer(f"تمت إضافة النموذج: {name}\n"
                   f"الرجاء ضبط نوع العملية والموديل والبرومبت من لوحة إدارة النموذج.")
    await state.clear()


# ============ عرض نموذج واحد ============

@router.callback_query(F.data.startswith("admin_template_view:"))
async def admin_template_view(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])

    async with SessionLocal() as s:
        res = await s.execute(
            select(Template)
            .where(Template.id == template_id)
            .options()
        )
        t = res.scalar_one_or_none()
        if t:
            # نجلب أيضاً الموديل
            res_m = await s.execute(select(ModelCatalog).where(ModelCatalog.id == t.model_catalog_id))
            mrow = res_m.scalar_one_or_none()
        else:
            mrow = None

    if not t:
        await c.answer("النموذج غير موجود.", show_alert=True)
        return

    kind = OPERATION_KIND.get(t.operation, "?")
    model_name = mrow.model_id if (mrow and mrow.model_id) else f"ID={t.model_catalog_id}"

    text = (
        f"إدارة النموذج:\n\n"
        f"ID: {t.id}\n"
        f"الاسم: {t.name}\n"
        f"العملية: {t.operation} (نوع الموديل: {kind})\n"
        f"الموديل: {model_name}\n"
        f"نوع الملفات المطلوبة: {t.file_requirement}\n"
        f"الحالة: {'✅ مفعل' if t.is_active else '❌ غير مفعل'}\n"
        f"\n"
        f"برومبت أساسي (مختصر):\n"
        f"{(t.base_prompt[:200] + '...') if len(t.base_prompt) > 200 else (t.base_prompt or 'غير محدد')}\n"
    )

    try:
        await c.message.edit_text(text, reply_markup=_template_manage_kb(t))
    except Exception:
        await c.message.answer(text, reply_markup=_template_manage_kb(t))
    await c.answer()


# ============ إعادة تسمية نموذج ============

@router.callback_query(F.data.startswith("admin_template_rename:"))
async def admin_template_rename(c: CallbackQuery, state: FSMContext):
    template_id = int(c.data.split(":")[1])
    await state.update_data(template_id=template_id)
    await state.set_state(TemplateEditState.editing_name)
    await c.message.answer("أرسل الاسم الجديد للنموذج:")
    await c.answer()


@router.message(TemplateEditState.editing_name)
async def admin_template_rename_name(m: Message, state: FSMContext):
    data = await state.get_data()
    template_id = data.get("template_id")
    new_name = (m.text or "").strip()

    if not new_name:
        await m.answer("الرجاء إرسال اسم صالح.")
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await m.answer("النموذج غير موجود.")
            await state.clear()
            return

        t.name = new_name
        await s.commit()

    await m.answer("تم تحديث اسم النموذج.")
    await state.clear()


# ============ تعديل البرومبت الأساسي ============

@router.callback_query(F.data.startswith("admin_template_prompt:"))
async def admin_template_prompt(c: CallbackQuery, state: FSMContext):
    template_id = int(c.data.split(":")[1])
    await state.update_data(template_id=template_id)
    await state.set_state(TemplateEditState.editing_prompt)
    await c.message.answer(
        "أرسل الآن البرومبت الأساسي لهذا النموذج.\n"
        "سيتم دمجه لاحقاً مع برومبت العميل ومدخلات المستخدم."
    )
    await c.answer()


@router.message(TemplateEditState.editing_prompt)
async def admin_template_prompt_input(m: Message, state: FSMContext):
    data = await state.get_data()
    template_id = data.get("template_id")
    prompt = (m.text or "").strip()

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await m.answer("النموذج غير موجود.")
            await state.clear()
            return

        t.base_prompt = prompt
        await s.commit()

    await m.answer("تم تحديث البرومبت الأساسي للنموذج.")
    await state.clear()


# ============ تغيير نوع العملية ============

def _template_operation_kb(template_id: int):
    kb = InlineKeyboardBuilder()
    for op_val, label in OPERATION_CHOICES:
        kb.button(
            text=label,
            callback_data=f"admin_template_set_operation:{template_id}:{op_val}",
        )
    kb.button(text="⬅️ رجوع للنموذج", callback_data=f"admin_template_view:{template_id}")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("admin_template_operation:"))
async def admin_template_operation(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])
    text = "اختر نوع العملية لهذا النموذج:"
    try:
        await c.message.edit_text(text, reply_markup=_template_operation_kb(template_id))
    except Exception:
        await c.message.answer(text, reply_markup=_template_operation_kb(template_id))
    await c.answer()


@router.callback_query(F.data.startswith("admin_template_set_operation:"))
async def admin_template_set_operation(c: CallbackQuery):
    _, template_id_s, op_val = c.data.split(":")
    template_id = int(template_id_s)

    if op_val not in dict(OPERATION_CHOICES):
        await c.answer("نوع عملية غير معروف.", show_alert=True)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await c.answer("النموذج غير موجود.", show_alert=True)
            return

        t.operation = op_val
        await s.commit()
        await s.refresh(t)

    await c.answer("تم تحديث نوع العملية.")
    await admin_template_view(c)


# ============ اختيار الموديل المناسب للنموذج ============

def _template_models_kb(template_id: int, kind: str, rows):
    kb = InlineKeyboardBuilder()
    for m in rows:
        status = "✅" if m.enabled else "❌"
        kb.button(
            text=f"{status} {m.model_id}",
            callback_data=f"admin_template_set_model:{template_id}:{m.id}",
        )
    kb.button(text="⬅️ رجوع للنموذج", callback_data=f"admin_template_view:{template_id}")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("admin_template_model:"))
async def admin_template_model(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()

    if not t:
        await c.answer("النموذج غير موجود.", show_alert=True)
        return

    kind = OPERATION_KIND.get(t.operation)
    if not kind:
        await c.answer("نوع العملية غير معروف، حدّد نوع العملية أولاً.", show_alert=True)
        return

    rows = await list_models(kind, enabled_only=True)

    text = f"اختر الموديل المناسب لنوع العملية ({t.operation}) من نوع: {kind}\n"
    if not rows:
        text += "لا توجد موديلات مفعّلة لهذا النوع. أضفها أولاً من 'إدارة الموديلات'."

    try:
        await c.message.edit_text(text, reply_markup=_template_models_kb(template_id, kind, rows))
    except Exception:
        await c.message.answer(text, reply_markup=_template_models_kb(template_id, kind, rows))
    await c.answer()


@router.callback_query(F.data.startswith("admin_template_set_model:"))
async def admin_template_set_model(c: CallbackQuery):
    _, template_id_s, model_id_s = c.data.split(":")
    template_id = int(template_id_s)
    row_id = int(model_id_s)

    async with SessionLocal() as s:
        res_t = await s.execute(select(Template).where(Template.id == template_id))
        t = res_t.scalar_one_or_none()
        if not t:
            await c.answer("النموذج غير موجود.", show_alert=True)
            return

        res_m = await s.execute(select(ModelCatalog).where(ModelCatalog.id == row_id))
        mrow = res_m.scalar_one_or_none()
        if not mrow or not mrow.enabled:
            await c.answer("هذا الموديل غير متاح.", show_alert=True)
            return

        t.model_catalog_id = mrow.id
        await s.commit()

    await c.answer("تم تعيين الموديل لهذا النموذج.")
    await admin_template_view(c)


# ============ تغيير نوع الملفات المطلوبة ============

def _template_files_kb(template_id: int):
    kb = InlineKeyboardBuilder()
    for val, label in FILE_REQUIREMENT_CHOICES:
        kb.button(
            text=label,
            callback_data=f"admin_template_set_files:{template_id}:{val}",
        )
    kb.button(text="⬅️ رجوع للنموذج", callback_data=f"admin_template_view:{template_id}")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("admin_template_files:"))
async def admin_template_files(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])

    text = "اختر نوع الملفات التي سيطلبها هذا النموذج من المستخدم:"
    try:
        await c.message.edit_text(text, reply_markup=_template_files_kb(template_id))
    except Exception:
        await c.message.answer(text, reply_markup=_template_files_kb(template_id))
    await c.answer()


@router.callback_query(F.data.startswith("admin_template_set_files:"))
async def admin_template_set_files(c: CallbackQuery):
    _, template_id_s, val = c.data.split(":")
    template_id = int(template_id_s)

    if val not in dict(FILE_REQUIREMENT_CHOICES):
        await c.answer("قيمة غير معروفة.", show_alert=True)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await c.answer("النموذج غير موجود.", show_alert=True)
            return

        t.file_requirement = val
        await s.commit()

    await c.answer("تم تحديث نوع الملفات المطلوبة.")
    await admin_template_view(c)


# ============ تفعيل/تعطيل نموذج ============

@router.callback_query(F.data.startswith("admin_template_toggle:"))
async def admin_template_toggle(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await c.answer("النموذج غير موجود.", show_alert=True)
            return

        t.is_active = not bool(t.is_active)
        await s.commit()
        await s.refresh(t)

    await c.answer("تم تحديث حالة النموذج.")
    await admin_template_view(c)


# ============ حذف نموذج ============

@router.callback_query(F.data.startswith("admin_template_delete:"))
async def admin_template_delete(c: CallbackQuery):
    template_id = int(c.data.split(":")[1])

    # تأكيد بسيط
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ نعم، احذف",
        callback_data=f"admin_template_delete_confirm:{template_id}:yes",
    )
    kb.button(text="❌ لا", callback_data=f"admin_template_view:{template_id}")
    kb.adjust(1)

    await c.message.answer("هل أنت متأكد من حذف هذا النموذج؟", reply_markup=kb.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith("admin_template_delete_confirm:"))
async def admin_template_delete_confirm(c: CallbackQuery):
    _, template_id_s, decision = c.data.split(":")
    template_id = int(template_id_s)

    if decision != "yes":
        await admin_template_view(c)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Template).where(Template.id == template_id))
        t = res.scalar_one_or_none()
        if not t:
            await c.answer("النموذج غير موجود.", show_alert=True)
            return

        section_id = t.section_id
        await s.delete(t)
        await s.commit()

    await c.answer("تم حذف النموذج.")
    await admin_templates_menu(
        CallbackQuery(
            id=c.id,
            from_user=c.from_user,
            chat_instance=c.chat_instance,
            message=c.message,
            data=f"admin_templates_menu:{section_id}",
        )
    )
