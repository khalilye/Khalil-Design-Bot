# handlers/admin_staff.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.permissions import get_or_create_user
from app.db import SessionLocal
from app.models import User

router = Router()


class AddStaff(StatesGroup):
    waiting_tg_id = State()


PERMS = [
    ("can_generate", "📝 توليد (حسب النماذج)"),
    ("can_edit", "✏️ تعديل الصور/الفيديو"),
    ("can_sandbox", "🎲 القسم الحر"),
    ("can_manage_clients", "🗂️ إدارة العملاء"),
    ("can_manage_settings", "⚙️ الإعدادات"),
]


def _staff_list_kb(staff: list[User]):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ إضافة موظف", callback_data="admin_staff_add")
    for u in staff:
        kb.button(text=f"موظف: {u.tg_id}", callback_data=f"admin_staff_view:{u.id}")
    kb.button(text="⬅️ رجوع", callback_data="settings_menu")
    kb.adjust(1)
    return kb.as_markup()


def _staff_manage_kb(u: User):
    kb = InlineKeyboardBuilder()
    for perm_key, label in PERMS:
        status = "✅" if getattr(u, perm_key) else "❌"
        kb.button(
            text=f"{status} {label}",
            callback_data=f"admin_staff_toggle:{u.id}:{perm_key}",
        )
    kb.button(text="🗑️ حذف الموظف", callback_data=f"admin_staff_delete:{u.id}")
    kb.button(text="⬅️ رجوع لقائمة الموظفين", callback_data="admin_staff_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "admin_staff_menu")
async def admin_staff_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if user.role != "owner":
        await c.answer("فقط المالك يمكنه إدارة الموظفين.", show_alert=True)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.role == "staff"))
        staff = list(res.scalars().all())

    text = "إدارة الموظفين:\n\n"
    if not staff:
        text += "لا يوجد موظفون بعد."

    try:
        await c.message.edit_text(text, reply_markup=_staff_list_kb(staff))
    except Exception:
        await c.message.answer(text, reply_markup=_staff_list_kb(staff))
    await c.answer()


@router.callback_query(F.data == "admin_staff_add")
async def admin_staff_add(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if user.role != "owner":
        await c.answer("فقط المالك يمكنه إضافة موظفين.", show_alert=True)
        return
    await state.set_state(AddStaff.waiting_tg_id)
    await c.message.answer(
        "أرسل الآن رقم الآيدي (Telegram ID) للموظف الجديد.\n"
        "يمكنك الحصول عليه من البوتات مثل @userinfobot.",
    )
    await c.answer()


@router.message(AddStaff.waiting_tg_id)
async def admin_staff_add_tg_id(m: Message, state: FSMContext):
    owner = await get_or_create_user(m.from_user.id)
    if owner.role != "owner":
        await m.answer("فقط المالك يمكنه إضافة موظفين.")
        await state.clear()
        return

    val = (m.text or "").strip()
    if not val.isdigit():
        await m.answer("الرجاء إرسال رقم آيدي صالح (أرقام فقط). حاول مرة أخرى أو /start للإلغاء.")
        return

    tg_id = int(val)
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.tg_id == tg_id))
        existing = res.scalar_one_or_none()
        if existing:
            await m.answer("هذا المستخدم موجود مسبقاً كموظف.")
            await state.clear()
            return

        u = User(tg_id=tg_id, role="staff")
        s.add(u)
        await s.commit()

    await m.answer(f"تمت إضافة الموظف بالآيدي: {tg_id}")
    await state.clear()


@router.callback_query(F.data.startswith("admin_staff_view:"))
async def admin_staff_view(c: CallbackQuery):
    owner = await get_or_create_user(c.from_user.id)
    if owner.role != "owner":
        await c.answer("فقط المالك يمكنه إدارة الموظفين.", show_alert=True)
        return

    user_id = int(c.data.split(":")[1])
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.id == user_id))
        u = res.scalar_one_or_none()

    if not u:
        await c.answer("الموظف غير موجود.", show_alert=True)
        return

    text = f"إدارة صلاحيات الموظف:\n\nID الداخلي: {u.id}\nTelegram ID: {u.tg_id}"
    try:
        await c.message.edit_text(text, reply_markup=_staff_manage_kb(u))
    except Exception:
        await c.message.answer(text, reply_markup=_staff_manage_kb(u))
    await c.answer()


@router.callback_query(F.data.startswith("admin_staff_toggle:"))
async def admin_staff_toggle(c: CallbackQuery):
    owner = await get_or_create_user(c.from_user.id)
    if owner.role != "owner":
        await c.answer("فقط المالك يمكنه إدارة الموظفين.", show_alert=True)
        return

    _, user_id_s, perm_key = c.data.split(":")
    user_id = int(user_id_s)

    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.id == user_id))
        u = res.scalar_one_or_none()
        if not u:
            await c.answer("الموظف غير موجود.", show_alert=True)
            return

        if not hasattr(u, perm_key):
            await c.answer("صلاحية غير معروفة.", show_alert=True)
            return

        current = bool(getattr(u, perm_key))
        setattr(u, perm_key, not current)
        await s.commit()
        await s.refresh(u)

    text = f"إدارة صلاحيات الموظف:\n\nID الداخلي: {u.id}\nTelegram ID: {u.tg_id}"
    try:
        await c.message.edit_text(text, reply_markup=_staff_manage_kb(u))
    except Exception:
        await c.message.answer(text, reply_markup=_staff_manage_kb(u))
    await c.answer("تم تحديث الصلاحية.")


@router.callback_query(F.data.startswith("admin_staff_delete:"))
async def admin_staff_delete(c: CallbackQuery):
    owner = await get_or_create_user(c.from_user.id)
    if owner.role != "owner":
        await c.answer("فقط المالك يمكنه حذف الموظفين.", show_alert=True)
        return

    user_id = int(c.data.split(":")[1])
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.id == user_id))
        u = res.scalar_one_or_none()
        if not u:
            await c.answer("الموظف غير موجود.", show_alert=True)
            return
        await s.delete(u)
        await s.commit()

    await c.answer("تم حذف الموظف.")
    await admin_staff_menu(c)