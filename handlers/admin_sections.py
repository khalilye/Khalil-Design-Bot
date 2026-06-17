# handlers/admin_sections.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Section, Template
from app.permissions import get_or_create_user

router = Router()


class SectionEditState(StatesGroup):
    adding_name = State()
    renaming = State()


# ============ مساعدات ============

def _sections_kb(current_parent_id: int | None, sections: list[Section]):
    kb = InlineKeyboardBuilder()

    parent_id_str = "none" if current_parent_id is None else str(current_parent_id)
    kb.button(
        text="➕ إضافة قسم جديد",
        callback_data=f"admin_section_add:{parent_id_str}",
    )

    for sec in sections:
        kb.button(
            text=f"📁 {sec.name}",
            callback_data=f"admin_section_open:{sec.id}",
        )

    if current_parent_id is None:
        kb.button(text="⬅️ رجوع", callback_data="settings_menu")
    else:
        kb.button(
            text="⬅️ رجوع للأعلى",
            callback_data=f"admin_section_up:{current_parent_id}",
        )

    kb.adjust(1)
    return kb.as_markup()


def _section_manage_kb(sec: Section):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ إعادة تسمية القسم", callback_data=f"admin_section_rename:{sec.id}")
    kb.button(text="⬆️ تحريك لأعلى", callback_data=f"admin_section_move:{sec.id}:up")
    kb.button(text="⬇️ تحريك لأسفل", callback_data=f"admin_section_move:{sec.id}:down")
    kb.button(text="🗑️ حذف القسم", callback_data=f"admin_section_delete:{sec.id}")
    kb.button(text="🧩 إدارة النماذج في هذا القسم", callback_data=f"admin_templates_menu:{sec.id}")
    kb.button(text="📂 فتح هذا القسم", callback_data=f"admin_section_open:{sec.id}")
    kb.button(text="⬅️ رجوع للأقسام", callback_data="admin_sections_menu")
    kb.adjust(1)
    return kb.as_markup()


async def _render_sections_root(c: CallbackQuery):
    async with SessionLocal() as s:
        res = await s.execute(
            select(Section)
            .where(Section.parent_id.is_(None))
            .order_by(Section.sort_order.asc(), Section.name.asc())
        )
        sections = list(res.scalars().all())

    text = "إدارة الأقسام (الجذر):\n\n"
    if not sections:
        text += "لا توجد أقسام بعد. أضف قسماً جديداً."

    try:
        await c.message.edit_text(
            text,
            reply_markup=_sections_kb(None, sections),
        )
    except Exception:
        await c.message.answer(
            text,
            reply_markup=_sections_kb(None, sections),
        )
    await c.answer()


async def _render_sections_for_parent(c: CallbackQuery, parent_id: int):
    async with SessionLocal() as s:
        res_parent = await s.execute(select(Section).where(Section.id == parent_id))
        parent = res_parent.scalar_one_or_none()

        res = await s.execute(
            select(Section)
            .where(Section.parent_id == parent_id)
            .order_by(Section.sort_order.asc(), Section.name.asc())
        )
        sections = list(res.scalars().all())

    if not parent:
        await _render_sections_root(c)
        return

    text = f"إدارة الأقسام تحت: {parent.name}\n\n"
    if not sections:
        text += "لا توجد أقسام فرعية بعد. أضف قسماً جديداً."

    try:
        await c.message.edit_text(
            text,
            reply_markup=_sections_kb(parent_id, sections),
        )
    except Exception:
        await c.message.answer(
            text,
            reply_markup=_sections_kb(parent_id, sections),
        )
    await c.answer()


# ============ نقاط الدخول ============

@router.callback_query(F.data == "admin_sections_menu")
async def admin_sections_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإدارة الأقسام.", show_alert=True)
        return

    await _render_sections_root(c)


@router.callback_query(F.data.startswith("admin_section_open:"))
async def admin_section_open(c: CallbackQuery):
    section_id = int(c.data.split(":")[1])
    async with SessionLocal() as s:
        res = await s.execute(select(Section).where(Section.id == section_id))
        sec = res.scalar_one_or_none()

    if not sec:
        await c.answer("القسم غير موجود.", show_alert=True)
        return

    text = f"القسم: {sec.name}\n\n"
    text += "اختر أحد الخيارات التالية لإدارة هذا القسم أو استعراض ما تحته."

    try:
        await c.message.edit_text(text, reply_markup=_section_manage_kb(sec))
    except Exception:
        await c.message.answer(text, reply_markup=_section_manage_kb(sec))
    await c.answer()


@router.callback_query(F.data.startswith("admin_section_up:"))
async def admin_section_up(c: CallbackQuery):
    section_id = int(c.data.split(":")[1])
    async with SessionLocal() as s:
        res = await s.execute(select(Section).where(Section.id == section_id))
        sec = res.scalar_one_or_none()

    if not sec:
        await _render_sections_root(c)
        return

    if sec.parent_id is None:
        await _render_sections_root(c)
    else:
        await _render_sections_for_parent(c, sec.parent_id)


# ============ إضافة قسم جديد ============

@router.callback_query(F.data.startswith("admin_section_add:"))
async def admin_section_add(c: CallbackQuery, state: FSMContext):
    parts = c.data.split(":")
    parent_id_str = parts[1]
    parent_id = None if parent_id_str == "none" else int(parent_id_str)

    await state.update_data(parent_id=parent_id)
    await state.set_state(SectionEditState.adding_name)

    if parent_id is None:
        loc = "الجذر"
    else:
        async with SessionLocal() as s:
            res = await s.execute(select(Section).where(Section.id == parent_id))
            parent = res.scalar_one_or_none()
        loc = parent.name if parent else "قسم غير معروف"

    await c.message.answer(
        f"أرسل الآن اسم القسم الجديد الذي تريد إضافته تحت: {loc}"
    )
    await c.answer()


@router.message(SectionEditState.adding_name)
async def admin_section_add_name(m: Message, state: FSMContext):
    data = await state.get_data()
    parent_id = data.get("parent_id")
    name = (m.text or "").strip()

    if not name:
        await m.answer("الرجاء إرسال اسم صالح للقسم.")
        return

    async with SessionLocal() as s:
        if parent_id is None:
            res_order = await s.execute(
                select(Section.sort_order).where(Section.parent_id.is_(None))
            )
        else:
            res_order = await s.execute(
                select(Section.sort_order).where(Section.parent_id == parent_id)
            )
        orders = [o for (o,) in res_order.all()]
        next_order = (max(orders) + 1) if orders else 0

        sec = Section(
            name=name,
            parent_id=parent_id,
            sort_order=next_order,
        )
        s.add(sec)
        await s.commit()

    await m.answer(f"تمت إضافة القسم: {name}")
    await state.clear()


# ============ إعادة تسمية قسم ============

@router.callback_query(F.data.startswith("admin_section_rename:"))
async def admin_section_rename(c: CallbackQuery, state: FSMContext):
    section_id = int(c.data.split(":")[1])
    await state.update_data(section_id=section_id)
    await state.set_state(SectionEditState.renaming)
    await c.message.answer("أرسل الاسم الجديد لهذا القسم:")
    await c.answer()


@router.message(SectionEditState.renaming)
async def admin_section_rename_name(m: Message, state: FSMContext):
    data = await state.get_data()
    section_id = data.get("section_id")
    new_name = (m.text or "").strip()

    if not new_name:
        await m.answer("الرجاء إرسال اسم صالح.")
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Section).where(Section.id == section_id))
        sec = res.scalar_one_or_none()
        if not sec:
            await m.answer("القسم غير موجود.")
            await state.clear()
            return

        sec.name = new_name
        await s.commit()

    await m.answer("تم تحديث اسم القسم.")
    await state.clear()


# ============ تحريك ترتيب القسم ============

@router.callback_query(F.data.startswith("admin_section_move:"))
async def admin_section_move(c: CallbackQuery):
    _, section_id_s, direction = c.data.split(":")
    section_id = int(section_id_s)

    async with SessionLocal() as s:
        res = await s.execute(select(Section).where(Section.id == section_id))
        sec = res.scalar_one_or_none()
        if not sec:
            await c.answer("القسم غير موجود.", show_alert=True)
            return

        parent_id = sec.parent_id

        if direction == "up":
            res2 = await s.execute(
                select(Section)
                .where(
                    (Section.parent_id == parent_id),
                    (Section.sort_order < sec.sort_order),
                )
                .order_by(Section.sort_order.desc())
                .limit(1)
            )
        else:
            res2 = await s.execute(
                select(Section)
                .where(
                    (Section.parent_id == parent_id),
                    (Section.sort_order > sec.sort_order),
                )
                .order_by(Section.sort_order.asc())
                .limit(1)
            )

        neighbor = res2.scalar_one_or_none()
        if not neighbor:
            await c.answer("لا يمكن التحريك أكثر في هذا الاتجاه.", show_alert=True)
            return

        sec.sort_order, neighbor.sort_order = neighbor.sort_order, sec.sort_order
        await s.commit()

    await c.answer("تم تحديث ترتيب القسم.")
    await admin_section_open(c)


# ============ حذف قسم ============

@router.callback_query(F.data.startswith("admin_section_delete:"))
async def admin_section_delete(c: CallbackQuery):
    section_id = int(c.data.split(":")[1])

    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ نعم، احذف",
        callback_data=f"admin_section_delete_confirm:{section_id}:yes",
    )
    kb.button(text="❌ لا", callback_data="admin_sections_menu")
    kb.adjust(1)

    await c.message.answer(
        "تحذير: حذف القسم سيحذف النماذج تحته أيضاً (لكن لن نحذف العملاء).\n"
        "هل أنت متأكد من الحذف؟",
        reply_markup=kb.as_markup(),
    )
    await c.answer()


@router.callback_query(F.data.startswith("admin_section_delete_confirm:"))
async def admin_section_delete_confirm(c: CallbackQuery):
    _, section_id_s, decision = c.data.split(":")
    section_id = int(section_id_s)

    if decision != "yes":
        await admin_sections_menu(c)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Section).where(Section.id == section_id))
        sec = res.scalar_one_or_none()
        if not sec:
            await c.answer("القسم غير موجود.", show_alert=True)
            return

        parent_id = sec.parent_id

        res_t = await s.execute(select(Template).where(Template.section_id == section_id))
        templates = res_t.scalars().all()
        for t in templates:
            await s.delete(t)

        await s.delete(sec)
        await s.commit()

    await c.answer("تم حذف القسم.")
    if parent_id is None:
        await admin_sections_menu(c)
    else:
        await _render_sections_for_parent(c, parent_id)
