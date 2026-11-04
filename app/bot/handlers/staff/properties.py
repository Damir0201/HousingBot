from functools import partial
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.callbacks import AdminCb, AdmPropCb
from app.bot.keyboards import staff as kb
from app.bot.middlewares import AfterCommit
from app.bot.states import StaffStates
from app.bot.utils import safe_edit
from app.modules.bookings import tasks as booking_tasks
from app.modules.properties.models import Property, PropertyStatus
from app.modules.properties.service import PropertyService
from app.modules.properties.workflows import change_property_status, dispatch_status_side_effects
from app.shared.i18n import Translator

router = Router(name="staff.properties")

PAGE_SIZE = 8


def _property_view(prop: Property, t: Translator) -> str:
    status = f"{kb.STATUS_ICONS[prop.status]} {t(f'property.status.{prop.status}')}"
    return (
        f"<code>{escape(prop.code)}</code>\n"
        + texts.property_card(prop, t)
        + "\n\n"
        + t("admin.prop_status", status=status)
        + "\n"
        + t("admin.prop_photos", count=len(prop.photos or []))
    )


@router.callback_query(AdminCb.filter(F.section == "props"))
async def list_properties(
    callback: CallbackQuery,
    callback_data: AdminCb,
    state: FSMContext,
    session: AsyncSession,
    t: Translator,
) -> None:
    await state.clear()
    page = max(callback_data.page, 0)
    props = await PropertyService(session).list(offset=page * PAGE_SIZE, limit=PAGE_SIZE + 1)
    await safe_edit(
        callback,
        t("admin.props_title") if props else t("admin.props_empty"),
        kb.properties_list(props[:PAGE_SIZE], page, t, has_next=len(props) > PAGE_SIZE),
    )
    await callback.answer()


@router.callback_query(AdmPropCb.filter(F.action == "view"))
async def view_property(
    callback: CallbackQuery,
    callback_data: AdmPropCb,
    state: FSMContext,
    session: AsyncSession,
    t: Translator,
) -> None:
    await state.clear()
    prop = await PropertyService(session).get(callback_data.id)
    await safe_edit(callback, _property_view(prop, t), kb.property_actions(prop, t))
    await callback.answer()


@router.callback_query(AdmPropCb.filter(F.action == "status"))
async def set_status(
    callback: CallbackQuery,
    callback_data: AdmPropCb,
    session: AsyncSession,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    result = await change_property_status(session, callback_data.id, PropertyStatus(callback_data.value))
    after_commit.append(partial(dispatch_status_side_effects, result))
    if result.became_available:
        after_commit.append(partial(booking_tasks.process_waitlist.delay, result.property.id))
    await safe_edit(callback, _property_view(result.property, t), kb.property_actions(result.property, t))
    await callback.answer(
        t("admin.status_changed", cancelled=len(result.cancelled_booking_ids)), show_alert=True
    )


@router.callback_query(AdmPropCb.filter(F.action == "photo_add"))
async def prompt_add_photo(
    callback: CallbackQuery,
    callback_data: AdmPropCb,
    state: FSMContext,
    session: AsyncSession,
    t: Translator,
) -> None:
    prop = await PropertyService(session).get(callback_data.id)
    await state.set_state(StaffStates.property_photo)
    await state.update_data(property_id=prop.id)
    await safe_edit(
        callback,
        t("admin.photo_send_prompt", code=escape(prop.code), count=len(prop.photos or [])),
        kb.property_back(prop.id, t),
    )
    await callback.answer()


@router.message(StaffStates.property_photo, F.photo)
async def receive_property_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    t: Translator,
) -> None:
    data = await state.get_data()
    property_id = data.get("property_id")
    if not property_id or not message.photo:
        await state.clear()
        return
    file_id = message.photo[-1].file_id
    prop = await PropertyService(session).add_photo(int(property_id), file_id)
    await message.answer(
        t("admin.photo_added", code=escape(prop.code), count=len(prop.photos or [])),
        reply_markup=kb.property_back(prop.id, t),
    )


@router.callback_query(AdmPropCb.filter(F.action == "photo_clear"))
async def clear_property_photos(
    callback: CallbackQuery,
    callback_data: AdmPropCb,
    session: AsyncSession,
    t: Translator,
) -> None:
    prop = await PropertyService(session).clear_photos(callback_data.id)
    await safe_edit(callback, _property_view(prop, t), kb.property_actions(prop, t))
    await callback.answer(t("admin.photos_cleared"))
