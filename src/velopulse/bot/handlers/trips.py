"""Telegram bot handlers for manual trip creation and component wear updates."""

import logging
import uuid
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.bot.handlers.bikes import get_event_chat_id, parse_mileage_input
from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_elevation_preset_keyboard,
    get_trip_bikes_keyboard,
)
from velopulse.bot.states import TripStates
from velopulse.bot.utils.helpers import get_user_by_chat_id, get_user_language
from velopulse.db.models.bike import Bike
from velopulse.db.session import get_session_context
from velopulse.services.wear.service import WearCalculationService

logger = logging.getLogger("velopulse.bot.trips")
router = Router(name="trips")


@router.callback_query(F.data == "trip:new")
@router.message(Command("newtrip"))
async def handle_start_new_trip(event: CallbackQuery | Message, state: FSMContext) -> None:
    """Start manual trip entry flow."""
    await state.clear()
    chat_id = get_event_chat_id(event)

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        if not user:
            return
        lang = get_user_language(user)

        bikes_stmt = (
            select(Bike)
            .where(Bike.user_id == user.id, Bike.is_active.is_(True))
            .order_by(Bike.created_at.asc())
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

    if not bikes:
        no_bikes_text = t("trip_no_bikes", lang)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("btn_create_bike", lang), callback_data="bike:create"
                    )
                ],
                [InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:profile")],
            ]
        )
        if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            await event.message.edit_text(no_bikes_text, reply_markup=kb)
            await event.answer()
        elif isinstance(event, Message):
            await event.answer(no_bikes_text, reply_markup=kb)
        return

    await state.set_state(TripStates.selecting_bike)
    await state.update_data(language=lang)

    select_text = t("trip_select_bike", lang)
    kb = get_trip_bikes_keyboard(bikes, lang)

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        await event.message.edit_text(select_text, reply_markup=kb)
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(select_text, reply_markup=kb)


@router.callback_query(TripStates.selecting_bike, F.data.startswith("trip:bike:"))
async def handle_trip_bike_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Handle bike selection for manual trip."""
    if not query.data or not isinstance(query.message, Message):
        return

    bike_id_str = query.data.split(":", 2)[2]
    try:
        bike_id = uuid.UUID(bike_id_str)
    except ValueError:
        await query.answer("Invalid bike ID", show_alert=True)
        return

    data = await state.get_data()
    lang = data.get("language", "en")

    await state.update_data(bike_id=str(bike_id))
    await state.set_state(TripStates.entering_distance)

    msg_text = t("trip_enter_distance", lang)
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:profile")]
        ]
    )
    await query.message.edit_text(msg_text, reply_markup=cancel_kb)
    await query.answer()


@router.message(TripStates.entering_distance)
async def handle_trip_distance_entered(message: Message, state: FSMContext) -> None:
    """Validate distance and ask for elevation gain."""
    data = await state.get_data()
    lang = data.get("language", "en")

    val = parse_mileage_input(message.text or "")
    if val is None or val <= 0.0:
        await message.answer(t("trip_invalid_distance", lang))
        return

    await state.update_data(distance_km=val)
    await state.set_state(TripStates.entering_elevation)

    elev_text = t("trip_enter_elevation", lang)
    kb = get_elevation_preset_keyboard(lang)
    await message.answer(elev_text, reply_markup=kb)


@router.callback_query(TripStates.entering_elevation, F.data.startswith("preset_elev:"))
async def handle_trip_elevation_preset(query: CallbackQuery, state: FSMContext) -> None:
    """Handle elevation preset selection and complete trip recording."""
    if not query.data or not isinstance(query.message, Message):
        return

    elev_val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await complete_trip_entry(query, state, elev_val)


@router.message(TripStates.entering_elevation)
async def handle_trip_elevation_text(message: Message, state: FSMContext) -> None:
    """Handle free-form elevation text entry and complete trip recording."""
    data = await state.get_data()
    lang = data.get("language", "en")

    val = parse_mileage_input(message.text or "")
    if val is None or val < 0.0:
        await message.answer(
            t("trip_invalid_elevation", lang),
            reply_markup=get_elevation_preset_keyboard(lang),
        )
        return

    await complete_trip_entry(message, state, val)


async def complete_trip_entry(
    event: CallbackQuery | Message,
    state: FSMContext,
    elevation_m: float,
) -> None:
    """Apply distance & elevation wear to bike and components, and show confirmation."""
    data = await state.get_data()
    lang = data.get("language", "en")
    bike_id_str = data.get("bike_id")
    dist_km = float(data.get("distance_km", 0.0))

    if not bike_id_str:
        return

    bike_id = uuid.UUID(bike_id_str)
    chat_id = get_event_chat_id(event)
    first_name = (
        event.from_user.first_name if event.from_user and event.from_user.first_name else "Cyclist"
    )

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        if not user:
            return

        stmt = select(Bike).where(Bike.id == bike_id).options(selectinload(Bike.components))
        bike = (await session.execute(stmt)).scalar_one_or_none()
        if not bike:
            return

        # 1. Update bike odometer
        dist_m = int(dist_km * 1000)
        bike.total_distance_m = (bike.total_distance_m or 0) + dist_m

        # 2. Physics-based wear calculation
        ef = WearCalculationService.calculate_elevation_factor(dist_km, elevation_m, bike.bike_type)
        wear_engine = WearCalculationService()

        for comp in bike.components:
            if comp.retired_at is None:
                cm = WearCalculationService.calculate_component_coefficient(
                    comp.component_type, comp.brand_model, 1.0, ef
                )
                delta_wp = wear_engine.calculate_wear_delta(dist_km, ef, 1.0, cm)
                comp.current_wear_points = Decimal(
                    str(round(float(comp.current_wear_points) + delta_wp, 2))
                )
                comp.status = WearCalculationService.evaluate_component_status(
                    float(comp.current_wear_points),
                    float(comp.lifespan_wear_points),
                    comp.status,
                )

        await session.commit()
        bike_name = bike.name

    await state.clear()

    # Success summary message
    success_text = t(
        "trip_success",
        lang,
        first_name=first_name,
        bike_name=bike_name,
        dist=dist_km,
        elev=elevation_m,
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🚲 {bike_name}",
                    callback_data=f"bike:manage:{bike_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_profile", lang),
                    callback_data="open:profile",
                )
            ],
        ]
    )

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        try:
            await event.message.edit_text(success_text, reply_markup=kb)
        except Exception:
            await event.message.answer(success_text, reply_markup=kb)
        await event.answer("🎉 Trip recorded!", show_alert=False)
    elif isinstance(event, Message):
        await event.answer(success_text, reply_markup=kb)
