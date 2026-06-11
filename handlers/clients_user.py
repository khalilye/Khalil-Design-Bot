# handlers/clients_user.py
from __future__ import annotations

from io import BytesIO
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    BufferedInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    User,
    Client,
    Section,
    Template,
    ModelCatalog,
    StaffClient,
)
from app.permissions import get_or_create_user
from app.config import DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL
from app.openrouter import chat, image_generate
from app.overlay import apply_overlay_png

router = Router()


class ClientGenState(StatesGroup):
    waiting_input = State()


# نوع العملية -> نوع الموديل المطلوب
OPERATION_KIND = {
    "text_generate": "text",
    "image_generate": "image",
    "image_edit": "image",
    "video_generate": "video",
    "video_edit": "video",
    "audio_generate": "audio",
}


# ============ مساعدات عامة ============

async def _get_accessible_clients(user: User) -> list[Client]:
    """
    يرجع قائمة العملاء التي يمكن للمستخدم الوصول إليها.
    حالياً:
      - المالك أو من لديه allow_all_clients أو can_manage_clients → كل العملاء.
      - غير ذلك: (مستقبلاً يمكن ربط StaffClient، الآن نعيد كل العملاء أيضاً لتبسيط الاستخدام).
    """
    async with SessionLocal() as s:
        # يمكنك لاحقاً تفعيل الربط مع StaffClient هنا
        res = await s.execute(select(Client).order_by(Client.name.asc()))
        clients = list(res.scalars().all())
    return clients


def _clients_kb(clients: list[Client]):
    kb = InlineKeyboardBuilder()
    for cl in clients:
        kb.button(text=cl.name, callback_data=f"user_client_pick:{cl.id}")
    kb.button(text="🏠 الرئيسية", callback_data="nav_home")
    kb.adjust(1)
    return kb.as_markup()


def _user_section_kb(
    client_id: int,
    parent_section: Optional[Section],
    sections: list[Section],
    templates: list[Template],
):
    kb = InlineKeyboardBuilder()

    for sec in sections:
        kb.button(
            text=f"📂 {sec.name}",
            callback_data=f"user_section_open:{client_id}:{sec.id}",
        )

    for t in templates:
        kb.button(
            text=f"🧩 {t.name}",
            callback_data=f"user_template_pick:{client_id}:{t.id}",
        )

    if parent_section is None:
        # نحن في الجذر
        kb.button(text="⬅️ رجوع لاختيار عميل", callback_data="clients_menu")
    else:
        if parent_section.parent_id is None:
            kb.button(
                text="⬅️ رجوع للأقسام الرئيسية",
                callback_data=f"user_client_root:{client_id}",
            )
        else:
            kb.button(
                text="⬅️ رجوع للأعلى",
                callback_data=f"user_section_open:{client_id}:{parent_section.parent_id}",
            )
        kb.button(text="👤 تغيير العميل", callback_data="clients_menu")

    kb.button(text="🏠 الرئيسية", callback_data="nav_home")

    kb.adjust(1)
    return kb.as_markup()


async def _download_file_bytes(message: Message, file_id: str) -> bytes:
    """
    تنزيل ملف (صورة/فيديو) من تيليجرام وإرجاعه كـ bytes.
    """
    file = await message.bot.get_file(file_id)
    buf = BytesIO()
    await message.bot.download(file, buf)
    buf.seek(0)
    return buf.read()


async def _resolve_model(
    t: Template,
    client: Client,
) -> tuple[str, Optional[str]]:
    """
    يحدد model_id المناسب للنموذج والعميل بناءً على نوع العملية.
    يرجع (model_id, kind)
    """
    op = t.operation
    kind = OPERATION_KIND.get(op)

    # نوع الموديل حسب العملية
    if kind == "text":
        fallback = client.default_text_model or DEFAULT_TEXT_MODEL
    elif kind == "image":
        fallback = client.default_image_model or DEFAULT_IMAGE_MODEL
    elif kind == "video":
        fallback = None  # لم ننفذ حالياً
    elif kind == "audio":
        fallback = None  # لم ننفذ حالياً
    else:
        fallback = None

    model_id = fallback

    # نحاول قراءة الموديل من ModelCatalog
    async with SessionLocal() as s:
        res = await s.execute(
            select(ModelCatalog).where(ModelCatalog.id == t.model_catalog_id)
        )
        mrow = res.scalar_one_or_none()
        if mrow and mrow.enabled and mrow.kind == kind:
            model_id = mrow.model_id

    return model_id, kind


# ============ 1) منيو اختيار العميل ============

@router.callback_query(F.data == "clients_menu")
async def clients_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(c.from_user.id)

    if not (user.can_generate or user.role == "owner"):
        await c.answer("صلاحيتك لا تسمح بالتوليد للعملاء.", show_alert=True)
        return

    clients = await _get_accessible_clients(user)
    text = "اختر العميل الذي تريد العمل عليه:"
    try:
        await c.message.edit_text(text, reply_markup=_clients_kb(clients))
    except Exception:
        await c.message.answer(text, reply_markup=_clients_kb(clients))
    await c.answer()


# ============ 2) عرض الأقسام للجذر (root) للعميل ============

async def _render_user_sections_root(c: CallbackQuery, client_id: int):
    async with SessionLocal() as s:
        res_sec = await s.execute(
            select(Section)
            .where(Section.parent_id.is_(None), Section.is_active == True)  # noqa
            .order_by(Section.sort_order.asc(), Section.name.asc())
        )
        sections = list(res_sec.scalars().all())

        # النماذج في الأقسام الجذرية (نعتبر أن النموذج يعود لقسم رئيسي بلا أب)
        res_tpl = await s.execute(
            select(Template)
            .join(Section, Section.id == Template.section_id)
            .where(
                Section.parent_id.is_(None),
                Section.is_active == True,  # noqa
                Template.is_active == True,  # noqa
            )
            .order_by(Template.name.asc())
        )
        templates = list(res_tpl.scalars().all())

    text = "اختر القسم أو النموذج:\n(أنت الآن في الجذر)"
    kb = _user_section_kb(client_id, None, sections, templates)
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except Exception:
        await c.message.answer(text, reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("user_client_pick:"))
async def user_client_pick(c: CallbackQuery, state: FSMContext):
    client_id = int(c.data.split(":")[1])
    await state.update_data(client_id=client_id)
    await _render_user_sections_root(c, client_id)


@router.callback_query(F.data.startswith("user_client_root:"))
async def user_client_root(c: CallbackQuery):
    client_id = int(c.data.split(":")[1])
    await _render_user_sections_root(c, client_id)


# ============ 3) عرض الأقسام الفرعية والنماذج لقسم معيّن ============

async def _render_user_section(c: CallbackQuery, client_id: int, section_id: int):
    async with SessionLocal() as s:
        res_sec = await s.execute(select(Section).where(Section.id == section_id))
        sec = res_sec.scalar_one_or_none()
        if not sec or not sec.is_active:
            await _render_user_sections_root(c, client_id)
            return

        res_children = await s.execute(
            select(Section)
            .where(Section.parent_id == section_id, Section.is_active == True)  # noqa
            .order_by(Section.sort_order.asc(), Section.name.asc())
        )
        children = list(res_children.scalars().all())

        res_tpl = await s.execute(
            select(Template)
            .where(
                Template.section_id == section_id,
                Template.is_active == True,  # noqa
            )
            .order_by(Template.name.asc())
        )
        templates = list(res_tpl.scalars().all())

    text = f"القسم: {sec.name}\nاختر قسماً فرعياً أو نموذجاً:"
    kb = _user_section_kb(client_id, sec, children, templates)
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except Exception:
        await c.message.answer(text, reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("user_section_open:"))
async def user_section_open(c: CallbackQuery):
    _, client_id_s, section_id_s = c.data.split(":")
    client_id = int(client_id_s)
    section_id = int(section_id_s)
    await _render_user_section(c, client_id, section_id)


# ============ 4) اختيار نموذج وطلب المدخلات من المستخدم ============

@router.callback_query(F.data.startswith("user_template_pick:"))
async def user_template_pick(c: CallbackQuery, state: FSMContext):
    _, client_id_s, template_id_s = c.data.split(":")
    client_id = int(client_id_s)
    template_id = int(template_id_s)

    async with SessionLocal() as s:
        res_t = await s.execute(select(Template).where(Template.id == template_id))
        t = res_t.scalar_one_or_none()

    if not t or not t.is_active:
        await c.answer("النموذج غير متاح حالياً.", show_alert=True)
        return

    # نحفظ في الحالة
    await state.update_data(client_id=client_id, template_id=template_id)
    await state.set_state(ClientGenState.waiting_input)

    # نص التعليمات حسب نوع الملفات المطلوبة
    fr = t.file_requirement

    if fr == "none":
        msg = (
            f"النموذج: {t.name}\n\n"
            "أرسل الآن نص الطلب (الوصف/المحتوى) ليتم التوليد بناءً عليه."
        )
    elif fr == "image_single":
        msg = (
            f"النموذج: {t.name}\n\n"
            "أرسل الآن صورة واحدة مع كتابة التعليمات في الوصف (Caption).\n"
            "ستُستخدم الصورة كمرجع، والنص لتوضيح المطلوب."
        )
    elif fr == "image_multi":
        msg = (
            f"النموذج: {t.name}\n\n"
            "أرسل الآن صورة واحدة مع التعليمات في الوصف.\n"
            "حالياً ندعم صورة واحدة فقط، وسيتم تحسين دعم عدة صور لاحقاً."
        )
    elif fr == "video_single":
        msg = (
            f"النموذج: {t.name}\n\n"
            "أرسل الآن فيديو واحد مع التعليمات في الوصف.\n"
            "تنبيه: عمليات الفيديو لم تُنفّذ بعد في البوت، سنعرض رسالة بذلك."
        )
    else:
        msg = (
            f"النموذج: {t.name}\n\n"
            "أرسل الآن البيانات المطلوبة (نص / وسائط) حسب هذا النموذج."
        )

    await c.message.answer(msg)
    await c.answer()


# ============ 5) استقبال المدخلات وتنفيذ التوليد ============

@router.message(ClientGenState.waiting_input)
async def user_template_input(m: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("client_id")
    template_id = data.get("template_id")

    if not client_id or not template_id:
        await m.answer("حدث خطأ في الحالة، جرّب اختيار العميل والنموذج من جديد.")
        await state.clear()
        return

    async with SessionLocal() as s:
        res_c = await s.execute(select(Client).where(Client.id == client_id))
        client = res_c.scalar_one_or_none()

        res_t = await s.execute(select(Template).where(Template.id == template_id))
        t = res_t.scalar_one_or_none()

    if not client or not t or not t.is_active:
        await m.answer("العميل أو النموذج غير متاح حالياً.")
        await state.clear()
        return

    model_id, kind = await _resolve_model(t, client)
    if not model_id or not kind:
        await m.answer("لا يوجد موديل مناسب مضبوط لهذا النموذج. تواصل مع الإدارة لضبطه.")
        await state.clear()
        return

    op = t.operation
    fr = t.file_requirement

    # جمع نص المستخدم
    user_text = (m.text or "") if m.text else (m.caption or "")

    # صور/فيديو إن وجدت
    input_images: list[bytes] = []
    input_video: Optional[bytes] = None

    if fr in ("image_single", "image_multi"):
        file_id = None
        if m.photo:
            file_id = m.photo[-1].file_id
        elif m.document and (m.document.mime_type or "").startswith("image/"):
            file_id = m.document.file_id

        if not file_id:
            await m.answer("هذا النموذج يحتاج صورة واحدة. الرجاء إرسال صورة مع الوصف.")
            return

        img_bytes = await _download_file_bytes(m, file_id)
        input_images.append(img_bytes)

    elif fr == "video_single":
        if m.video:
            vid_id = m.video.file_id
            input_video = await _download_file_bytes(m, vid_id)
        else:
            await m.answer("هذا النموذج يحتاج فيديو واحد. الرجاء إرسال فيديو مع الوصف.")
            return

    # معالجة حسب نوع العملية
    try:
        if op == "text_generate":
            await _handle_text_generate(m, client, t, model_id, user_text)
        elif op == "image_generate":
            await _handle_image_generate(m, client, t, model_id, user_text, input_images)
        else:
            await m.answer(
                f"هذا النموذج مضبوط على عملية: {op}\n"
                "لكن هذه العملية لم تُنفّذ بعد في البوت الحالي.\n"
                "يمكنك طلب من الإدارة تفعيل دعم هذا النوع مستقبلاً."
            )
    except Exception as e:
        await m.answer(f"حدث خطأ أثناء التوليد:\n{e}")

    await state.clear()


# ============ 6) دوال المعالجة الفعلية ============

async def _handle_text_generate(
    m: Message,
    client: Client,
    t: Template,
    model_id: str,
    user_text: str,
):
    if not user_text:
        await m.answer("لم أستلم أي نص. الرجاء إرسال النص المطلوب.")
        return

    system = (
        f"أنت كاتب محتوى محترف تعمل لصالح عميل اسمه: {client.name}.\n"
        f"تعليمات هوية العميل:\n{client.brand_prompt}\n\n"
        f"تعليمات اللَّياوت إن وجدت:\n{client.layout_prompt}\n\n"
        f"تعليمات هذا النموذج:\n{t.base_prompt}\n\n"
        f"اتبع هذه التعليمات بدقة في كتابة النص."
    )

    msg = await m.answer("⌛ جاري توليد النص...")
    try:
        result = await chat(model_id, system, user_text)
        await msg.delete()
        await m.answer(result)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد النص:\n{e}")


async def _handle_image_generate(
    m: Message,
    client: Client,
    t: Template,
    model_id: str,
    user_text: str,
    input_images: list[bytes],
):
    # نجمع البرومبت النهائي
    prompt_parts = []

    if client.brand_prompt:
        prompt_parts.append(f"تعليمات هوية العميل:\n{client.brand_prompt}")
    if client.layout_prompt:
        prompt_parts.append(f"تعليمات اللَّياوت:\n{client.layout_prompt}")
    if t.base_prompt:
        prompt_parts.append(f"تعليمات النموذج:\n{t.base_prompt}")
    if user_text:
        prompt_parts.append(f"مدخلات المستخدم:\n{user_text}")

    full_prompt = "\n\n".join(prompt_parts) or "صمم صورة تناسب هذا العميل."

    size = f"{client.design_width}x{client.design_height}"

    msg = await m.answer("🖼️ جاري توليد الصورة...")
    try:
        img_bytes = await image_generate(
            model=model_id,
            prompt=full_prompt,
            size=size,
            input_images=input_images or None,
        )

        # تركيب الكليشة إن وجدت
        if client.overlay_path:
            img_bytes = apply_overlay_png(img_bytes, client.overlay_path)

        await msg.delete()
        await m.bot.send_photo(
            m.chat.id,
            BufferedInputFile(img_bytes, filename="result.png"),
        )
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد الصورة:\n{e}")
