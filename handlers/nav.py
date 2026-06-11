# handlers/nav.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from app.permissions import get_or_create_user
from app.keyboards import main_menu

router = Router()


async def _render_main_menu(c: CallbackQuery):
    user = await get_or_create_user(c.from_user.id)
    try:
        await c.message.edit_text(
            "القائمة الرئيسية:",
            reply_markup=main_menu(is_owner=(user.role == "owner")),
        )
    except Exception:
        await c.message.answer(
            "القائمة الرئيسية:",
            reply_markup=main_menu(is_owner=(user.role == "owner")),
        )
    await c.answer()


@router.callback_query(F.data == "nav_home")
async def nav_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_main_menu(c)