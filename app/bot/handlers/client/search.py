from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.callbacks import PropCb, SearchCb
from app.bot.filters import TextKey, menu_button
from app.bot.keyboards import client as kb
from app.bot.states import SearchStates
from app.bot.utils import callback_message, safe_edit, send_photos, send_property_cards
from app.modules.crm.service import LeadService
from app.modules.properties.schemas import PropertySearchCriteria
from app.modules.properties.service import PropertyService
from app.modules.users.models import User
from app.shared.i18n import Translator

router = Router(name="client.search")


# ------------------------------------------------------------------ scripted wizard
@router.message(Command("search"))
@router.message(TextKey("menu.search"))
async def start_search(message: Message, state: FSMContext, t: Translator) -> None:
    await state.clear()
    await state.set_state(SearchStates.district)
    await message.answer(t("search.ask_district"), reply_markup=kb.search_any(t, "district"))


async def _ask_budget(message: Message, state: FSMContext, t: Translator) -> None:
    await state.set_state(SearchStates.budget)
    await message.answer(t("search.ask_budget"), reply_markup=kb.search_budget(t))


@router.message(SearchStates.district, F.text, ~menu_button())
async def district_text(message: Message, state: FSMContext, t: Translator) -> None:
    await state.update_data(districts=[message.text.strip()[:64]] if message.text else [])
    await _ask_budget(message, state, t)


@router.callback_query(SearchStates.district, SearchCb.filter(F.field == "district"))
async def district_any(callback: CallbackQuery, state: FSMContext, t: Translator) -> None:
    await state.update_data(districts=[])
    await callback.answer()
    if message := callback_message(callback):
        await _ask_budget(message, state, t)


@router.callback_query(SearchStates.budget, SearchCb.filter(F.field == "budget"))
async def budget(callback: CallbackQuery, callback_data: SearchCb, state: FSMContext, t: Translator) -> None:
    if callback_data.value != "any":
        low, high = callback_data.value.split("-")
        await state.update_data(budget_min=low or None, budget_max=high or None)
    await state.set_state(SearchStates.rooms)
    await safe_edit(callback, t("search.ask_rooms"), kb.search_rooms(t))
    await callback.answer()


@router.callback_query(SearchStates.rooms, SearchCb.filter(F.field == "rooms"))
async def rooms(callback: CallbackQuery, callback_data: SearchCb, state: FSMContext, t: Translator) -> None:
    if callback_data.value != "any":
        value = int(callback_data.value)
        is_last = callback_data.value == kb.ROOMS_OPTIONS[-1]
        await state.update_data(rooms_min=value, rooms_max=None if is_last else value)
    await state.set_state(SearchStates.term)
    await safe_edit(callback, t("search.ask_term"), kb.search_term(t))
    await callback.answer()


@router.callback_query(SearchStates.term, SearchCb.filter(F.field == "term"))
async def term(
    callback: CallbackQuery,
    callback_data: SearchCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    t: Translator,
) -> None:
    if callback_data.value in ("short", "long"):
        await state.update_data(rental_period=callback_data.value)
    elif callback_data.value.isdigit():
        await state.update_data(term_months=int(callback_data.value))
    data = await state.get_data()
    await state.clear()
    await callback.answer()

    criteria = PropertySearchCriteria.model_validate(data)
    saved = criteria.model_dump(mode="json", exclude_defaults=True, exclude={"limit", "exclude_ids"})
    await LeadService(session).update_criteria(user, saved)
    props = await PropertyService(session).search(criteria)

    message = callback_message(callback)
    if message is None:
        return
    if not props:
        await safe_edit(callback, t("search.nothing_found"))
        return
    await safe_edit(callback, t("search.found", count=len(props)))
    await send_property_cards(message, props, t)


# ------------------------------------------------------------------ property details
@router.callback_query(PropCb.filter(F.action == "details"))
async def details(
    callback: CallbackQuery, callback_data: PropCb, session: AsyncSession, t: Translator
) -> None:
    prop = await PropertyService(session).get(callback_data.id)
    await callback.answer()
    message = callback_message(callback)
    if message is None:
        return
    await send_photos(message, prop)
    text = texts.property_card(prop, t)
    if prop.address:
        text += "\n📍 " + escape(prop.address)
    if prop.description:
        text += "\n\n" + escape(prop.description[:3000])
    await message.answer(text, reply_markup=kb.property_card(prop.id, t) if prop.is_bookable else None)
