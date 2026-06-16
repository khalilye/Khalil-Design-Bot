# handlers/admin_clients.py
from __future__ import annotations

from pathlib import Path
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client
from app.permissions import get_or_create_user
from app.config import STORAGE_DIR

router = Router()

OVERLAYS_DIR = Path(STORAGE_DIR) / "overlays"
OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)


class ClientEditState(StatesGroup):
    adding_name = State()
    editing_name = State()
    editing_size = State()
    editing_brand_prompt = State()
    editing_layout_prompt = State()
    uploading_overlay = State()


# ============ مساعدات للكيبورد والنصوص ============

def _clients_admin_list_kb(clients: list[Client]):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ إضافة عميل", callback_data="admin_client_add")
    for c in clients:
        kb.button(text=c.name, callback_data=f"admin_client_view:{c.id}")
    kb.button(text="⬅️ رجوع", callback_data="settings_menu")
    kb.adjust(1)
    return kb.as_markup()


def _client_actions_kb(client_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ تعديل الاسم", callback_data=f"admin_client_edit_name:{client_id}")
    kb.button(text="📏 تعديل المقاس", callback_data=f"admin_client_edit_size:{client_id}")
    kb.button(text="🧾 برومبت الهوية", callback_data=f"admin_client_edit_brand:{client_id}")
    kb.button(text="🧾 برومبت اللَّياوت", callback_data=f"admin_client_edit_layout:{client_id}")
    kb.button(text="🖼️ رفع/تغيير الكليشة (PNG)", callback_data=f"admin_client_overlay:{client_id}")
    kb.button(text="⬆️ تحريك لأعلى", callback_data=f"admin_client_move:{client_id}:up")
    kb.button(text="⬇️ تحريك لأسفل", callback_data=f"admin_client_move:{client_id}:down")
    kb.button(text="🗑️ حذف العميل", callback_data=f"admin_client_delete:{client_id}")
    kb.button(text="⬅️ رجوع لقائمة العملاء", callback_data="admin_clients_menu")
    kb.adjust(1)
    return kb.as_markup()


async def _format_client_text(client: Client) -> str:
    has_overlay = "✅" if client.overlay_path else "❌"
    txt = (
        f"إدارة العميل:\n\n"
        f"ID: {client.id}\n"
        f"الاسم: {client.name}\n"
        f"المقاس الافتراضي: {client.design_width}x{client.design_height}\n"
        f"كليشة (Overlay): {has_overlay}\n"
        f"\n"
        f"برومبت الهوية (مختصر):\n"
        f"{(client.brand_prompt[:200] + '...') if len(client.brand_prompt) > 200 else (client.brand_prompt or 'غير محدد')}\n"
    )
    return txt


async def _reload_client_view(c: CallbackQuery, client_id: int):
    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
    if not client:
        await c.answer("العميل غير موجود.", show_alert=True)
        return

    text = await _format_client_text(client)
    try:
        await c.message.edit_text(text, reply_markup=_client_actions_kb(client.id))
    except Exception:
        await c.message.answer(text, reply_markup=_client_actions_kb(client.id))
    await c.answer()


# ============ القائمة الرئيسية لإدارة العملاء ============

@router.callback_query(F.data == "admin_clients_menu")
async def admin_clients_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_clients or user.can_manage_settings):
        await c.answer("ليست لديك صلاحية لإدارة العملاء.", show_alert=True)
        return

    async with SessionLocal() as s:
        res = await s.execute(
            select(Client).order_by(Client.sort_order.asc(), Client.name.asc())
        )
        clients = list(res.scalars().all())

    text = "إدارة العملاء:\n\n"
    if not clients:
        text += "لا يوجد عملاء بعد."

    try:
        await c.message.edit_text(text, reply_markup=_clients_admin_list_kb(clients))
    except Exception:
        await c.message.answer(text, reply_markup=_clients_admin_list_kb(clients))
    await c.answer()


# ============ إضافة عميل ============

@router.callback_query(F.data == "admin_client_add")
async def admin_client_add(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.role == "owner" or user.can_manage_clients):
        await c.answer("فقط المالك أو من لديه صلاحية إدارة العملاء يمكنه الإضافة.", show_alert=True)
        return

    await state.set_state(ClientEditState.adding_name)
    await c.message.answer(
        "أرسل الآن اسم العميل الجديد.\n"
        "مثال: مطعم الشيف",
    )
    await c.answer()


@router.message(ClientEditState.adding_name)
async def admin_client_add_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if not name:
        await m.answer("الرجاء إرسال اسم صالح.")
        return

    async with SessionLocal() as s:
        # التأكد من عدم وجود اسم مكرر
        res = await s.execute(select(Client).where(Client.name == name))
        exists = res.scalar_one_or_none()
        if exists:
            await m.answer("يوجد عميل بهذا الاسم بالفعل. اختر اسماً مختلفاً.")
            return

        # حساب sort_order (أكبر قيمة + 1)
        res_order = await s.execute(select(Client.sort_order))
        orders = [o for (o,) in res_order.all()]
        next_order = (max(orders) + 1) if orders else 0

        c = Client(
            name=name,
            design_width=1080,
            design_height=1080,
            sort_order=next_order,
        )
        s.add(c)
        await s.commit()
        await s.refresh(c)

    await state.clear()
    await m.answer(f"تمت إضافة العميل: {name}")


# ============ عرض عميل واحد ============

@router.callback_query(F.data.startswith("admin_client_view:"))
async def admin_client_view(c: CallbackQuery):
    client_id = int(c.data.split(":")[1])
    await _reload_client_view(c, client_id)


# ============ تعديل الاسم ============

@router.callback_query(F.data.startswith("admin_client_edit_name:"))
async def admin_client_edit_name(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(ClientEditState.editing_name)
    await c.message.answer("أرسل الاسم الجديد للعميل:")
    await c.answer()


@router.message(ClientEditState.editing_name)
async def admin_client_edit_name_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")
    new_name = (m.text or "").strip()
    if not new_name:
        await m.answer("الرجاء إرسال اسم صالح.")
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await m.answer("العميل غير موجود.")
            await state.clear()
            return

        # تحقق من عدم تكرار الاسم
        res2 = await s.execute(
            select(Client).where(Client.name == new_name, Client.id != client_id)
        )
        exists = res2.scalar_one_or_none()
        if exists:
            await m.answer("يوجد عميل آخر بنفس الاسم. اختر اسماً مختلفاً.")
            return

        client.name = new_name
        await s.commit()

    await m.answer("تم تحديث اسم العميل.")
    await state.clear()


# ============ تعديل المقاس ============

@router.callback_query(F.data.startswith("admin_client_edit_size:"))
async def admin_client_edit_size(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(ClientEditState.editing_size)
    await c.message.answer(
        "أرسل المقاس الجديد بصيغة العرضxالارتفاع.\n"
        "مثال: 1080x1350",
    )
    await c.answer()


@router.message(ClientEditState.editing_size)
async def admin_client_edit_size_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")
    txt = (m.text or "").strip().lower()

    m2 = re.match(r"^\s*(\d+)\s*[x×]\s*(\d+)\s*$", txt)
    if not m2:
        await m.answer("الصيغة غير صحيحة. مثال صحيح: 1080x1350")
        return

    w = int(m2.group(1))
    h = int(m2.group(2))

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await m.answer("العميل غير موجود.")
            await state.clear()
            return

        client.design_width = w
        client.design_height = h
        await s.commit()

    await m.answer(f"تم تحديث المقاس إلى: {w}x{h}")
    await state.clear()


# ============ تعديل برومبت الهوية ============

@router.callback_query(F.data.startswith("admin_client_edit_brand:"))
async def admin_client_edit_brand(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(ClientEditState.editing_brand_prompt)
    await c.message.answer(
        "أرسل الآن برومبت الهوية للعميل.\n"
        "مثال: الألوان، أسلوب التصميم، نوع الخطوط، الممنوعات، ...",
    )
    await c.answer()


@router.message(ClientEditState.editing_brand_prompt)
async def admin_client_edit_brand_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")
    prompt = (m.text or "").strip()

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await m.answer("العميل غير موجود.")
            await state.clear()
            return

        client.brand_prompt = prompt
        await s.commit()

    await m.answer("تم تحديث برومبت الهوية.")
    await state.clear()


# ============ تعديل برومبت اللَّياوت ============

@router.callback_query(F.data.startswith("admin_client_edit_layout:"))
async def admin_client_edit_layout(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(ClientEditState.editing_layout_prompt)
    await c.message.answer(
        "أرسل الآن برومبت اللَّياوت (وصف المساحات الآمنة، أماكن النصوص، ...)\n"
        "يمكنك تركه فارغاً بإرسال كلمة: لا",
    )
    await c.answer()


@router.message(ClientEditState.editing_layout_prompt)
async def admin_client_edit_layout_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")
    prompt = (m.text or "").strip()

    if prompt == "لا":
        prompt = ""

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await m.answer("العميل غير موجود.")
            await state.clear()
            return

        client.layout_prompt = prompt
        await s.commit()

    await m.answer("تم تحديث برومبت اللَّياوت.")
    await state.clear()


# ============ رفع / تغيير الكليشة ============

@router.callback_query(F.data.startswith("admin_client_overlay:"))
async def admin_client_overlay(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await state.set_state(ClientEditState.uploading_overlay)
    await c.message.answer(
        "أرسل الآن صورة الكليشة (PNG شفاف) للعميل.\n"
        "يمكنك إرسالها كصورة أو كملف (Document).",
    )
    await c.answer()


@router.message(ClientEditState.uploading_overlay)
async def admin_client_overlay_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")

    file_id = None
    if m.photo:
        file_id = m.photo[-1].file_id
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id

    if not file_id:
        await m.answer("الرجاء إرسال صورة (أو ملف صورة) صالحة.")
        return

    file = await m.bot.get_file(file_id)
    overlay_path = OVERLAYS_DIR / f"client_{client_id}.png"
    await m.bot.download(file, destination=overlay_path)

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await m.answer("العميل غير موجود.")
            await state.clear()
            return

        client.overlay_path = str(overlay_path)
        await s.commit()

    await m.answer("تم حفظ الكليشة للعميل.")
    await state.clear()


# ============ تحريك ترتيب العميل ============

@router.callback_query(F.data.startswith("admin_client_move:"))
async def admin_client_move(c: CallbackQuery):
    _, client_id_s, direction = c.data.split(":")
    client_id = int(client_id_s)

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await c.answer("العميل غير موجود.", show_alert=True)
            return

        if direction == "up":
            res2 = await s.execute(
                select(Client)
                .where(Client.sort_order < client.sort_order)
                .order_by(Client.sort_order.desc())
                .limit(1)
            )
        else:  # down
            res2 = await s.execute(
                select(Client)
                .where(Client.sort_order > client.sort_order)
                .order_by(Client.sort_order.asc())
                .limit(1)
            )

        neighbor = res2.scalar_one_or_none()
        if not neighbor:
            await c.answer("لا يمكن التحريك أكثر في هذا الاتجاه.", show_alert=True)
            return

        client.sort_order, neighbor.sort_order = neighbor.sort_order, client.sort_order
        await s.commit()

    await c.answer("تم تحديث ترتيب العميل.")
    await _reload_client_view(c, client_id)


# ============ حذف العميل ============

@router.callback_query(F.data.startswith("admin_client_delete:"))
async def admin_client_delete(c: CallbackQuery):
    client_id = int(c.data.split(":")[1])

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ نعم، احذف", callback_data=f"admin_client_delete_confirm:{client_id}:yes")
    kb.button(text="❌ لا", callback_data="admin_clients_menu")
    kb.adjust(1)

    await c.message.answer("هل أنت متأكد من حذف هذا العميل؟", reply_markup=kb.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith("admin_client_delete_confirm:"))
async def admin_client_delete_confirm(c: CallbackQuery):
    _, client_id_s, decision = c.data.split(":")
    client_id = int(client_id_s)

    if decision != "yes":
        await admin_clients_menu(c)
        return

    async with SessionLocal() as s:
        res = await s.execute(select(Client).where(Client.id == client_id))
        client = res.scalar_one_or_none()
        if not client:
            await c.answer("العميل غير موجود.", show_alert=True)
            return

        await s.delete(client)
        await s.commit()

    await c.answer("تم حذف العميل.")
    await admin_clients_menu(c)
