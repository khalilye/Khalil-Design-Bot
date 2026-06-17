# handlers/free_mode.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.permissions import get_or_create_user
from app.config import DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL
from app.openrouter import chat, image_generate, image_edit, audio_generate, video_generate
from app.model_store import list_models

router = Router()


class FreeState(StatesGroup):
    waiting_text = State()
    waiting_image_generate = State()
    waiting_image_edit = State()
    waiting_audio_generate = State()
    waiting_video_generate = State()


def _free_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 توليد نص", callback_data="free_text_gen")
    kb.button(text="🖼️ توليد صورة", callback_data="free_image_gen")
    kb.button(text="✏️ تعديل صورة", callback_data="free_image_edit")
    kb.button(text="🎧 توليد صوت", callback_data="free_audio_gen")
    kb.button(text="🎥 توليد فيديو", callback_data="free_video_gen")
    kb.button(text="🏠 الرئيسية", callback_data="nav_home")
    kb.adjust(1)
    return kb.as_markup()


async def _download_file_bytes(message: Message, file_id: str) -> bytes:
    file = await message.bot.get_file(file_id)
    buf = BytesIO()
    await message.bot.download(file, buf)
    buf.seek(0)
    return buf.read()


def _get_user_text_model(user) -> str:
    return user.text_model or DEFAULT_TEXT_MODEL


def _get_user_image_model(user) -> str:
    return user.image_model or DEFAULT_IMAGE_MODEL


async def _get_free_audio_model() -> Optional[str]:
    rows = await list_models("audio", enabled_only=True)
    if rows:
        return rows[0].model_id
    return None


async def _get_free_video_model() -> Optional[str]:
    rows = await list_models("video", enabled_only=True)
    if rows:
        return rows[0].model_id
    return None


# ============ منيو القسم الحر ============

@router.callback_query(F.data == "free_menu")
async def free_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(c.from_user.id)

    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام القسم الحر.", show_alert=True)
        return

    text = "القسم الحر:\nاختر نوع العملية:"
    try:
        await c.message.edit_text(text, reply_markup=_free_menu_kb())
    except Exception:
        await c.message.answer(text, reply_markup=_free_menu_kb())
    await c.answer()


# ============ 1) توليد النصوص ============

@router.callback_query(F.data == "free_text_gen")
async def free_text_gen(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام هذا القسم.", show_alert=True)
        return

    await state.set_state(FreeState.waiting_text)
    await c.message.answer(
        "📝 توليد نص حر.\n"
        "أرسل الآن وصفاً أو نصاً تريد أن يصيغه لك الذكاء الاصطناعي."
    )
    await c.answer()


@router.message(FreeState.waiting_text)
async def free_text_gen_input(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)
    model_id = _get_user_text_model(user)

    user_text = (m.text or m.caption or "").strip()
    if not user_text:
        await m.answer("لم أستلم أي نص. الرجاء إرسال النص المطلوب.")
        return

    system = (
        "أنت مساعد ذكي لكتابة وتعديل النصوص باللغة العربية.\n"
        "حافظ على وضوح الأسلوب وصحّة اللغة، ويمكنك التنويع في الأساليب حسب نوع الطلب."
    )

    msg = await m.answer("⌛ جاري توليد النص...")
    try:
        result = await chat(model_id, system, user_text)
        await msg.delete()
        await m.answer(result)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد النص:\n{e}")
    await state.clear()


# ============ 2) توليد الصور ============

@router.callback_query(F.data == "free_image_gen")
async def free_image_gen(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام هذا القسم.", show_alert=True)
        return

    await state.set_state(FreeState.waiting_image_generate)
    await c.message.answer(
        "🖼️ توليد صورة حر.\n"
        "أرسل وصفاً للصورة التي تريدها.\n"
        "يمكنك أيضاً إرفاق صورة واحدة كمرجع (اختياري) مع كتابة الوصف في الـ Caption.\n"
        "لو كتبت مقاساً مثل 1080x1350 في الوصف، سيتم استخدامه."
    )
    await c.answer()


@router.message(FreeState.waiting_image_generate)
async def free_image_gen_input(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)
    model_id = _get_user_image_model(user)

    user_text = (m.text or "") if m.text else (m.caption or "")
    user_text = user_text.strip()

    input_images: list[bytes] = []

    if m.photo:
        file_id = m.photo[-1].file_id
        img_bytes = await _download_file_bytes(m, file_id)
        input_images.append(img_bytes)
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id
        img_bytes = await _download_file_bytes(m, file_id)
        input_images.append(img_bytes)

    if not user_text and not input_images:
        await m.answer(
            "لم أستلم لا نصاً ولا صورة.\n"
            "أرسل وصفاً للصورة، ويمكنك إرفاق صورة واحدة كمرجع إن شئت."
        )
        return

    prompt = user_text or "أنشئ صورة إبداعية مناسبة للوصف السابق (إن وجد)."

    # استخراج مقاس من الوصف إن وجد (مثل 1080x1350)
    size: Optional[str] = None
    m_size = re.search(r"(\d+)\s*[x×]\s*(\d+)", prompt)
    if m_size:
        w, h = m_size.group(1), m_size.group(2)
        size = f"{w}x{h}"

    msg = await m.answer("🖼️ جاري توليد الصورة...")
    try:
        img_bytes = await image_generate(
            model=model_id,
            prompt=prompt,
            size=size,  # None لو لم يُذكر مقاس
            input_images=input_images or None,
        )

        await msg.delete()

        photo_input = BufferedInputFile(img_bytes, filename="free_result.png")
        doc_input = BufferedInputFile(img_bytes, filename="free_result.png")

        await m.bot.send_photo(m.chat.id, photo_input)
        await m.bot.send_document(m.chat.id, doc_input)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد الصورة:\n{e}")
    await state.clear()


# ============ 3) تعديل الصور ============

@router.callback_query(F.data == "free_image_edit")
async def free_image_edit(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام هذا القسم.", show_alert=True)
        return

    await state.set_state(FreeState.waiting_image_edit)
    await c.message.answer(
        "✏️ تعديل صورة حر.\n"
        "أرسل صورة واحدة مع كتابة ما تريد تعديله في الوصف (Caption).\n"
        "لن يتم تغيير المقاس إلا إذا طلبت ذلك صراحة في الوصف."
    )
    await c.answer()


@router.message(FreeState.waiting_image_edit)
async def free_image_edit_input(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)
    model_id = _get_user_image_model(user)

    user_text = (m.caption or m.text or "").strip()

    base_img: Optional[bytes] = None
    if m.photo:
        file_id = m.photo[-1].file_id
        base_img = await _download_file_bytes(m, file_id)
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id
        base_img = await _download_file_bytes(m, file_id)

    if not base_img:
        await m.answer(
            "لم أستلم صورة صالحة.\n"
            "أرسل صورة واحدة كصورة أو ملف (Document) مع كتابة التعديلات في الوصف."
        )
        return

    if not user_text:
        await m.answer("يرجى كتابة ما تريد تعديله في الوصف (Caption).")
        return

    msg = await m.answer("✏️ جاري تعديل الصورة...")
    try:
        edited_bytes = await image_edit(
            model=model_id,
            image_bytes=base_img,
            prompt=user_text,
            strength=0.3,
            size=None,  # لن نرسل مقاس → لا تغيّر الدقة
        )
        await msg.delete()

        photo_input = BufferedInputFile(edited_bytes, filename="free_edited.png")
        doc_input = BufferedInputFile(edited_bytes, filename="free_edited.png")

        await m.bot.send_photo(m.chat.id, photo_input)
        await m.bot.send_document(m.chat.id, doc_input)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل تعديل الصورة:\n{e}")
    await state.clear()


# ============ 4) توليد الصوت ============

@router.callback_query(F.data == "free_audio_gen")
async def free_audio_gen(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام هذا القسم.", show_alert=True)
        return

    await state.set_state(FreeState.waiting_audio_generate)
    await c.message.answer(
        "🎧 توليد صوت حر.\n"
        "أرسل النص الذي تريد تحويله إلى ملف صوتي.\n"
        "تأكد أنك اخترت موديل صوت مناسب في '🧠 إدارة الموديلات' نوع audio، وفعّل واحداً منها."
    )
    await c.answer()


@router.message(FreeState.waiting_audio_generate)
async def free_audio_gen_input(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)

    text = (m.text or m.caption or "").strip()
    if not text:
        await m.answer("يرجى إرسال نص لتحويله إلى صوت.")
        return

    model_id = await _get_free_audio_model()
    if not model_id:
        await m.answer(
            "لا يوجد موديل صوت (audio) مفعّل حالياً.\n"
            "أضف موديل صوت في '🧠 إدارة الموديلات' بنوع audio وفعّله."
        )
        await state.clear()
        return

    msg = await m.answer("🎧 جاري توليد الصوت...")
    try:
        audio_bytes = await audio_generate(model_id, text)
        await msg.delete()

        audio_input = BufferedInputFile(audio_bytes, filename="free_audio.mp3")
        await m.bot.send_audio(m.chat.id, audio_input)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد الصوت:\n{e}")
    await state.clear()


# ============ 5) توليد الفيديو ============

@router.callback_query(F.data == "free_video_gen")
async def free_video_gen(c: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(c.from_user.id)
    if not (user.can_sandbox or user.role == "owner"):
        await c.answer("ليست لديك صلاحية استخدام هذا القسم.", show_alert=True)
        return

    await state.set_state(FreeState.waiting_video_generate)
    await c.message.answer(
        "🎥 توليد فيديو حر.\n"
        "أرسل وصفاً للفيديو القصير الذي تريد إنتاجه.\n"
        "تأكد أنك اخترت موديل فيديو مناسب في '🧠 إدارة الموديلات' بنوع video، وفعّلت واحداً منها.\n"
        "تنبيه: توليد الفيديو قد يستغرق وقتاً أطول، وقد يكون حجم الملف كبيراً."
    )
    await c.answer()


@router.message(FreeState.waiting_video_generate)
async def free_video_gen_input(m: Message, state: FSMContext):
    user = await get_or_create_user(m.from_user.id)

    text = (m.text or m.caption or "").strip()
    if not text:
        await m.answer("يرجى إرسال وصف للفيديو المطلوب.")
        return

    model_id = await _get_free_video_model()
    if not model_id:
        await m.answer(
            "لا يوجد موديل فيديو (video) مفعّل حالياً.\n"
            "أضف موديل فيديو في '🧠 إدارة الموديلات' بنوع video وفعّله."
        )
        await state.clear()
        return

    msg = await m.answer("🎥 جاري توليد الفيديو...\nقد يستغرق هذا بعض الوقت.")
    try:
        video_bytes = await video_generate(model_id, text)
        await msg.delete()

        video_input = BufferedInputFile(video_bytes, filename="free_video.mp4")
        await m.bot.send_video(m.chat.id, video_input)
    except Exception as e:
        await msg.delete()
        await m.answer(f"فشل توليد الفيديو:\n{e}")
    await state.clear()
