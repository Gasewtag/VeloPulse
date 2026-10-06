"""Telegram bot handlers for bike management, creation wizard, and component telemetry."""

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_bike_manage_keyboard,
    get_bike_type_keyboard,
    get_bikes_list_keyboard,
    get_brake_type_keyboard,
    get_component_details_keyboard,
    get_delete_bike_confirm_keyboard,
    get_lube_preset_keyboard,
    get_mileage_preset_keyboard,
    get_replace_confirm_keyboard,
)
from velopulse.bot.states import BikeCreationStates
from velopulse.bot.utils.formatters import get_component_icon, render_progress_bar
from velopulse.bot.utils.helpers import get_user_by_chat_id, get_user_language
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType, MaintenanceType
from velopulse.db.models.maintenance import MaintenanceLog
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.bikes")
router = Router(name="bikes")


def parse_mileage_input(raw: str) -> float | None:
    """Parse numeric mileage from user message (e.g. '1250', '1250 km', '1,250')."""
    clean = (
        raw.lower().replace("km", "").replace("км", "").replace(",", ".").replace(" ", "").strip()
    )
    try:
        val = float(clean)
        return val if val >= 0.0 else None
    except ValueError:
        return None


def calculate_status(current_km: float, lifespan_km: float) -> ComponentStatus:
    """Determine component health status based on wear percentage."""
    if lifespan_km <= 0 or current_km <= 0:
        return ComponentStatus.NEW
    pct = (current_km / lifespan_km) * 100.0
    if pct < 75.0:
        return ComponentStatus.OPTIMAL
    elif pct < 90.0:
        return ComponentStatus.ATTENTION_NEEDED
    return ComponentStatus.REPLACE_RECOMMENDED


def get_event_chat_id(event: CallbackQuery | Message) -> int:
    """Safely extract chat_id from either CallbackQuery or Message."""
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            return event.message.chat.id
        return event.from_user.id if event.from_user else 0
    return event.chat.id


@router.callback_query(F.data == "open:bikes")
async def handle_list_bikes(event: CallbackQuery | Message, state: FSMContext) -> None:
    """List registered bikes up to 3-bike limit."""
    await state.clear()
    chat_id = get_event_chat_id(event)

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if not user:
            return

        bikes_stmt = (
            select(Bike)
            .where(Bike.user_id == user.id, Bike.is_active.is_(True))
            .order_by(Bike.created_at.asc())
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

    intro = t("bikes_intro", lang)
    kb = get_bikes_list_keyboard(bikes, lang)

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        try:
            await event.message.edit_text(intro, reply_markup=kb)
        except Exception:
            await event.message.answer(intro, reply_markup=kb)
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(intro, reply_markup=kb)


@router.callback_query(F.data == "bike:create")
async def handle_start_bike_creation(query: CallbackQuery, state: FSMContext) -> None:
    """Start multi-step bike creation wizard."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if not user:
            return

        # Check limit (max 3 bikes)
        count_stmt = select(Bike).where(Bike.user_id == user.id, Bike.is_active.is_(True))
        bikes = list((await session.execute(count_stmt)).scalars().all())
        if len(bikes) >= 3:
            await query.answer("You already have 3 bikes.", show_alert=True)
            return

    await state.set_state(BikeCreationStates.selecting_bike_type)
    await state.update_data(language=lang)

    await query.message.edit_text(
        t("step_bike_type", lang),
        reply_markup=get_bike_type_keyboard(lang),
    )
    await query.answer()


@router.callback_query(BikeCreationStates.selecting_bike_type, F.data.startswith("bike_type:"))
async def handle_bike_type_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Handle bike type selection and ask for bike model."""
    if not query.data or not isinstance(query.message, Message):
        return

    b_type = query.data.split(":", 1)[1]
    data = await state.get_data()
    lang = data.get("language", "en")

    await state.update_data(bike_type=b_type)
    await state.set_state(BikeCreationStates.entering_model)

    prompt_key = f"step_bike_model_{b_type}"
    text = t(prompt_key, lang)
    if text == prompt_key:
        text = t("step_bike_model", lang)
    await query.message.edit_text(text)
    await query.answer()


@router.message(BikeCreationStates.entering_model)
async def handle_bike_model_entered(message: Message, state: FSMContext) -> None:
    """Validate model name and ask for rear cassette mileage."""
    data = await state.get_data()
    lang = data.get("language", "en")

    model_text = message.text.strip() if message.text else ""
    if not model_text:
        await message.answer(t("err_invalid_model", lang))
        return

    await state.update_data(model=model_text)
    await state.set_state(BikeCreationStates.entering_cassette_mileage)

    await message.answer(
        t("step_cassette_mileage", lang),
        reply_markup=get_mileage_preset_keyboard(lang),
    )


# --- Mileage Input Step Helpers ---


async def advance_mileage_step(
    event: CallbackQuery | Message,
    state: FSMContext,
    mileage_val: float,
    current_key: str,
    next_state: Any,
    next_prompt_key: str,
    next_keyboard_factory: Any,
) -> None:
    """Helper to store mileage and transition to next creation wizard state."""
    await state.update_data({current_key: mileage_val})
    await state.set_state(next_state)

    data = await state.get_data()
    lang = data.get("language", "en")
    prompt = t(next_prompt_key, lang)
    kb = next_keyboard_factory(lang)

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        await event.message.edit_text(prompt, reply_markup=kb)
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(prompt, reply_markup=kb)


# --- Step 10: Cassette Mileage ---


@router.callback_query(
    BikeCreationStates.entering_cassette_mileage, F.data.startswith("preset_km:")
)
async def handle_cassette_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "cassette_km",
        BikeCreationStates.entering_chain_mileage,
        "step_chain_mileage",
        get_mileage_preset_keyboard,
    )


@router.message(BikeCreationStates.entering_cassette_mileage)
async def handle_cassette_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "cassette_km",
        BikeCreationStates.entering_chain_mileage,
        "step_chain_mileage",
        get_mileage_preset_keyboard,
    )


# --- Step 11: Chain Mileage ---


@router.callback_query(BikeCreationStates.entering_chain_mileage, F.data.startswith("preset_km:"))
async def handle_chain_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "chain_km",
        BikeCreationStates.entering_chain_lube_mileage,
        "step_chain_lube_mileage",
        get_lube_preset_keyboard,
    )


@router.message(BikeCreationStates.entering_chain_mileage)
async def handle_chain_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "chain_km",
        BikeCreationStates.entering_chain_lube_mileage,
        "step_chain_lube_mileage",
        get_lube_preset_keyboard,
    )


# --- Step 11b: Chain Lubrication History ---


@router.callback_query(
    BikeCreationStates.entering_chain_lube_mileage, F.data.startswith("preset_lube:")
)
async def handle_chain_lube_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "chain_lube_ago_km",
        BikeCreationStates.entering_front_tire_mileage,
        "step_front_tire_mileage",
        get_mileage_preset_keyboard,
    )


@router.message(BikeCreationStates.entering_chain_lube_mileage)
async def handle_chain_lube_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_lube_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "chain_lube_ago_km",
        BikeCreationStates.entering_front_tire_mileage,
        "step_front_tire_mileage",
        get_mileage_preset_keyboard,
    )


# --- Step 12: Front Tire Mileage ---


@router.callback_query(
    BikeCreationStates.entering_front_tire_mileage, F.data.startswith("preset_km:")
)
async def handle_front_tire_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "front_tire_km",
        BikeCreationStates.entering_rear_tire_mileage,
        "step_rear_tire_mileage",
        get_mileage_preset_keyboard,
    )


@router.message(BikeCreationStates.entering_front_tire_mileage)
async def handle_front_tire_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "front_tire_km",
        BikeCreationStates.entering_rear_tire_mileage,
        "step_rear_tire_mileage",
        get_mileage_preset_keyboard,
    )


# --- Step 13: Rear Tire Mileage ---


@router.callback_query(
    BikeCreationStates.entering_rear_tire_mileage, F.data.startswith("preset_km:")
)
async def handle_rear_tire_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "rear_tire_km",
        BikeCreationStates.selecting_front_brake_type,
        "step_front_brake_type",
        get_brake_type_keyboard,
    )


@router.message(BikeCreationStates.entering_rear_tire_mileage)
async def handle_rear_tire_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "rear_tire_km",
        BikeCreationStates.selecting_front_brake_type,
        "step_front_brake_type",
        get_brake_type_keyboard,
    )


# --- Step 14: Front Brake Setup ---


@router.callback_query(
    BikeCreationStates.selecting_front_brake_type, F.data.startswith("brake_type:")
)
async def handle_front_brake_type(query: CallbackQuery, state: FSMContext) -> None:
    b_type = query.data.split(":", 1)[1] if query.data else "disc"
    await advance_mileage_step(
        query,
        state,
        0.0,
        "dummy",
        BikeCreationStates.entering_front_brake_mileage,
        "step_front_brake_mileage",
        get_mileage_preset_keyboard,
    )
    await state.update_data(front_brake_type=b_type)


@router.callback_query(
    BikeCreationStates.entering_front_brake_mileage, F.data.startswith("preset_km:")
)
async def handle_front_brake_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await advance_mileage_step(
        query,
        state,
        val,
        "front_brake_km",
        BikeCreationStates.selecting_rear_brake_type,
        "step_rear_brake_type",
        get_brake_type_keyboard,
    )


@router.message(BikeCreationStates.entering_front_brake_mileage)
async def handle_front_brake_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await advance_mileage_step(
        message,
        state,
        val,
        "front_brake_km",
        BikeCreationStates.selecting_rear_brake_type,
        "step_rear_brake_type",
        get_brake_type_keyboard,
    )


# --- Step 14: Rear Brake Setup ---


@router.callback_query(
    BikeCreationStates.selecting_rear_brake_type, F.data.startswith("brake_type:")
)
async def handle_rear_brake_type(query: CallbackQuery, state: FSMContext) -> None:
    b_type = query.data.split(":", 1)[1] if query.data else "disc"
    await advance_mileage_step(
        query,
        state,
        0.0,
        "dummy",
        BikeCreationStates.entering_rear_brake_mileage,
        "step_rear_brake_mileage",
        get_mileage_preset_keyboard,
    )
    await state.update_data(rear_brake_type=b_type)


@router.callback_query(
    BikeCreationStates.entering_rear_brake_mileage, F.data.startswith("preset_km:")
)
async def handle_rear_brake_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await handle_rear_brake_completed(query, state, val)


@router.message(BikeCreationStates.entering_rear_brake_mileage)
async def handle_rear_brake_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await handle_rear_brake_completed(message, state, val)


async def handle_rear_brake_completed(
    event: CallbackQuery | Message,
    state: FSMContext,
    val: float,
) -> None:
    """Route to MTB suspension step or finalize bike creation."""
    await state.update_data(rear_brake_km=val)
    data = await state.get_data()
    lang = data.get("language", "en")
    bike_type = data.get("bike_type", "road")

    if bike_type == "mtb":
        # Step 15: Ask MTB suspension mileage
        await state.set_state(BikeCreationStates.entering_suspension_mileage)
        prompt = t("step_suspension_mileage", lang)
        kb = get_mileage_preset_keyboard(lang)
        if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            await event.message.edit_text(prompt, reply_markup=kb)
            await event.answer()
        elif isinstance(event, Message):
            await event.answer(prompt, reply_markup=kb)
    else:
        # Step 16: Finalize creation
        await finalize_bike_creation(event, state)


# --- Step 15: MTB Suspension Mileage ---


@router.callback_query(
    BikeCreationStates.entering_suspension_mileage, F.data.startswith("preset_km:")
)
async def handle_suspension_preset(query: CallbackQuery, state: FSMContext) -> None:
    val = float(query.data.split(":", 1)[1]) if query.data else 0.0
    await state.update_data(suspension_km=val)
    await finalize_bike_creation(query, state)


@router.message(BikeCreationStates.entering_suspension_mileage)
async def handle_suspension_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    val = parse_mileage_input(message.text or "")
    if val is None:
        await message.answer(
            t("err_invalid_mileage", lang),
            reply_markup=get_mileage_preset_keyboard(lang),
        )
        return
    await state.update_data(suspension_km=val)
    await finalize_bike_creation(message, state)


# --- Step 16: Persist Bike and Components ---


async def finalize_bike_creation(
    event: CallbackQuery | Message,
    state: FSMContext,
) -> None:
    """Persist new Bike and attached Components in database, then show bike management menu."""
    data = await state.get_data()
    lang = data.get("language", "en")
    chat_id = get_event_chat_id(event)

    b_type_str = data.get("bike_type", "road")
    b_type = (
        BikeType.MTB
        if b_type_str == "mtb"
        else BikeType.GRAVEL
        if b_type_str == "gravel"
        else BikeType.ROAD
    )
    model = data.get("model", "Bike")
    cassette_km = float(data.get("cassette_km", 0.0))
    chain_km = float(data.get("chain_km", 0.0))
    front_tire_km = float(data.get("front_tire_km", 0.0))
    rear_tire_km = float(data.get("rear_tire_km", 0.0))
    front_brake_type = data.get("front_brake_type", "disc")
    front_brake_km = float(data.get("front_brake_km", 0.0))
    rear_brake_type = data.get("rear_brake_type", "disc")
    rear_brake_km = float(data.get("rear_brake_km", 0.0))
    suspension_km = float(data.get("suspension_km", 0.0))

    # Base bike distance: approximate as highest component distance
    total_dist_km = max(cassette_km, chain_km, front_tire_km, rear_tire_km)
    total_dist_m = int(total_dist_km * 1000)

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        if not user:
            return

        gear_id = f"tg_{uuid.uuid4().hex[:12]}"
        bike = Bike(
            user_id=user.id,
            strava_gear_id=gear_id,
            name=model,
            model=model,
            bike_type=b_type,
            total_distance_m=total_dist_m,
            is_active=True,
        )
        session.add(bike)
        await session.flush()

        # Build component specs
        components_to_add: list[Component] = [
            Component(
                bike_id=bike.id,
                component_type=ComponentType.CASSETTE,
                brand_model=f"{model} Cassette",
                lifespan_wear_points=Decimal("10000.00"),
                current_wear_points=Decimal(str(round(cassette_km, 2))),
                status=calculate_status(cassette_km, 10000.0),
            ),
            Component(
                bike_id=bike.id,
                component_type=ComponentType.CHAIN,
                brand_model=f"{model} Chain",
                lifespan_wear_points=Decimal("4000.00"),
                current_wear_points=Decimal(str(round(chain_km, 2))),
                status=calculate_status(chain_km, 4000.0),
            ),
            Component(
                bike_id=bike.id,
                component_type=ComponentType.FRONT_TIRE,
                brand_model=f"{model} Front Tire",
                lifespan_wear_points=Decimal("4000.00"),
                current_wear_points=Decimal(str(round(front_tire_km, 2))),
                status=calculate_status(front_tire_km, 4000.0),
            ),
            Component(
                bike_id=bike.id,
                component_type=ComponentType.REAR_TIRE,
                brand_model=f"{model} Rear Tire",
                lifespan_wear_points=Decimal("3000.00"),
                current_wear_points=Decimal(str(round(rear_tire_km, 2))),
                status=calculate_status(rear_tire_km, 3000.0),
            ),
            Component(
                bike_id=bike.id,
                component_type=ComponentType.FRONT_BRAKE_PAD,
                brand_model=f"{model} Front {'Disc' if front_brake_type == 'disc' else 'Rim'} Brake",
                lifespan_wear_points=Decimal("2500.00"),
                current_wear_points=Decimal(str(round(front_brake_km, 2))),
                status=calculate_status(front_brake_km, 2500.0),
            ),
            Component(
                bike_id=bike.id,
                component_type=ComponentType.REAR_BRAKE_PAD,
                brand_model=f"{model} Rear {'Disc' if rear_brake_type == 'disc' else 'Rim'} Brake",
                lifespan_wear_points=Decimal("2500.00"),
                current_wear_points=Decimal(str(round(rear_brake_km, 2))),
                status=calculate_status(rear_brake_km, 2500.0),
            ),
        ]

        if b_type == BikeType.MTB:
            components_to_add.append(
                Component(
                    bike_id=bike.id,
                    component_type=ComponentType.SUSPENSION_FORK,
                    brand_model=f"{model} Suspension Fork",
                    lifespan_wear_points=Decimal("2500.00"),
                    current_wear_points=Decimal(str(round(suspension_km, 2))),
                    status=calculate_status(suspension_km, 2500.0),
                )
            )

        session.add_all(components_to_add)
        await session.flush()

        # Initial chain lubrication log
        chain_comp = next(
            (c for c in components_to_add if c.component_type == ComponentType.CHAIN), None
        )
        if chain_comp:
            chain_lube_ago = float(data.get("chain_lube_ago_km", 0.0))
            chain_odo = max(0.0, chain_km - chain_lube_ago)
            lube_log = MaintenanceLog(
                component_id=chain_comp.id,
                user_id=user.id,
                log_type=MaintenanceType.CLEAN_AND_LUBE,
                description="Initial chain lubrication",
                odometer_km=Decimal(str(round(chain_odo, 2))),
            )
            session.add(lube_log)

        await session.commit()

        # Reload with components
        bike_query = select(Bike).where(Bike.id == bike.id).options(selectinload(Bike.components))
        saved_bike = (await session.execute(bike_query)).scalar_one()

    await state.clear()

    # Step 16 confirmation
    conf_msg = t("bike_created_success", lang)
    manage_title = t(
        "bike_manage_title",
        lang,
        name=saved_bike.name,
        bike_type=b_type_str.upper(),
    )
    full_text = f"{conf_msg}\n\n{manage_title}"
    active_comps = [c for c in saved_bike.components if c.retired_at is None]
    kb = get_bike_manage_keyboard(saved_bike, active_comps, lang)

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        await event.message.edit_text(full_text, reply_markup=kb)
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(full_text, reply_markup=kb)


# --- Step 17: Bike Management Menu ---


@router.callback_query(F.data.startswith("bike:manage:"))
async def handle_bike_manage_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Display bike components and management options."""
    if not query.data or not isinstance(query.message, Message):
        return

    await state.clear()
    bike_id_str = query.data.split(":", 2)[2]
    try:
        bike_id = uuid.UUID(bike_id_str)
    except ValueError:
        await query.answer("Invalid bike ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = select(Bike).where(Bike.id == bike_id).options(selectinload(Bike.components))
        bike = (await session.execute(stmt)).scalar_one_or_none()
        if not bike:
            await query.answer("Bike not found", show_alert=True)
            return

        b_type_str = (
            bike.bike_type.value if hasattr(bike.bike_type, "value") else str(bike.bike_type)
        )
        title = t("bike_manage_title", lang, name=bike.name, bike_type=b_type_str.upper())
        active_components = [c for c in bike.components if c.retired_at is None]
        kb = get_bike_manage_keyboard(bike, active_components, lang)

    try:
        await query.message.edit_text(title, reply_markup=kb)
    except Exception:
        await query.message.answer(title, reply_markup=kb)
    await query.answer()


# --- Step 18, 19, 20: Component Details Screen ---


@router.callback_query(F.data.startswith("comp:view:"))
async def handle_component_view(query: CallbackQuery, state: FSMContext) -> None:
    """Display component status, usage progress bar, lubrication status, and replacement action."""
    if not query.data or not isinstance(query.message, Message):
        return

    await state.clear()
    comp_id_str = query.data.split(":", 2)[2]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = (
            select(Component).where(Component.id == comp_id).options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if not comp or not comp.bike:
            await query.answer("Component not found", show_alert=True)
            return

        current_km = float(comp.current_wear_points)
        lifespan_km = float(comp.lifespan_wear_points)
        pct = (current_km / lifespan_km) * 100.0 if lifespan_km > 0 else 100.0

        # Step 20: Visual progress bar (10 chars, no brackets)
        bar = render_progress_bar(pct, length=10, with_brackets=False)

        # Step 19: Maintenance status badge
        if pct < 75.0:
            status_badge = t("status_good", lang)
        elif pct < 90.0:
            status_badge = t("status_soon", lang)
        else:
            status_badge = t("status_replace", lang)

        # Step 18: Lubrication line (only for chain)
        lube_line = ""
        if comp.component_type == ComponentType.CHAIN:
            last_lube_stmt = (
                select(MaintenanceLog)
                .where(
                    MaintenanceLog.component_id == comp.id,
                    MaintenanceLog.log_type == MaintenanceType.CLEAN_AND_LUBE,
                )
                .order_by(MaintenanceLog.performed_at.desc(), MaintenanceLog.created_at.desc())
                .limit(1)
            )
            last_lube = (await session.execute(last_lube_stmt)).scalars().first()
            if last_lube and last_lube.odometer_km is not None:
                km_since_lube = max(0.0, current_km - float(last_lube.odometer_km))
            else:
                km_since_lube = current_km % 200.0

            due_km = round(200.0 - km_since_lube)
            if due_km <= 20:
                lube_line = t("lube_due_now", lang)
            else:
                lube_line = t("lube_due_in", lang, due_km=due_km)

        icon = get_component_icon(comp.component_type)
        body = t(
            "comp_details_template",
            lang,
            icon=icon,
            comp_name=comp.brand_model,
            current_km=current_km,
            lifespan_km=lifespan_km,
            pct=pct,
            bar=bar,
            lube_line=lube_line,
            status_badge=status_badge,
        )

        kb = get_component_details_keyboard(comp.id, comp.bike_id, lang)

    try:
        await query.message.edit_text(body, reply_markup=kb)
    except Exception:
        await query.message.answer(body, reply_markup=kb)
    await query.answer()


# --- Step 21: Component Replacement ---


@router.callback_query(F.data.startswith("comp:replace_prompt:"))
async def handle_replace_prompt(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt user for confirmation before resetting component mileage."""
    if not query.data or not isinstance(query.message, Message):
        return

    comp_id_str = query.data.split(":", 2)[2]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = select(Component).where(Component.id == comp_id)
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if not comp:
            await query.answer("Component not found", show_alert=True)
            return

        kb = get_replace_confirm_keyboard(comp.id, comp.bike_id, lang)
        msg_text = t("replace_comp_prompt", lang)

    await query.message.edit_text(msg_text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("comp:replace_confirm:"))
async def handle_replace_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """Execute component replacement, reset mileage to 0 km, log maintenance, and update UI."""
    if not query.data or not isinstance(query.message, Message):
        return

    comp_id_str = query.data.split(":", 2)[2]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = (
            select(Component).where(Component.id == comp_id).options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if not comp or not comp.bike:
            await query.answer("Component not found", show_alert=True)
            return

        # 1. Reset wear baseline to 0
        old_wear = comp.current_wear_points
        comp.current_wear_points = Decimal("0.00")
        comp.status = ComponentStatus.NEW

        # 2. Record maintenance log
        log_entry = MaintenanceLog(
            user_id=comp.bike.user_id,
            component_id=comp.id,
            log_type=MaintenanceType.REPLACE,
            performed_at=datetime.now(UTC),
            description=f"Component replaced via Telegram bot. Previous mileage was {old_wear:.1f} km.",
            odometer_km=Decimal("0.00"),
        )
        session.add(log_entry)

        # 3. If chain, also record fresh lubrication
        if comp.component_type == ComponentType.CHAIN:
            lube_entry = MaintenanceLog(
                user_id=comp.bike.user_id,
                component_id=comp.id,
                log_type=MaintenanceType.CLEAN_AND_LUBE,
                performed_at=datetime.now(UTC),
                description="New chain installed and lubricated",
                odometer_km=Decimal("0.00"),
            )
            session.add(lube_entry)

        await session.commit()

        # Format updated 0 km component view directly
        current_km = 0.0
        lifespan_km = float(comp.lifespan_wear_points)
        pct = 0.0
        bar = render_progress_bar(pct, length=10, with_brackets=False)
        status_badge = t("status_good", lang)
        lube_line = ""
        if comp.component_type == ComponentType.CHAIN:
            lube_line = t("lube_due_in", lang, due_km=200)

        icon = get_component_icon(comp.component_type)
        body = t(
            "comp_details_template",
            lang,
            icon=icon,
            comp_name=comp.brand_model,
            current_km=current_km,
            lifespan_km=lifespan_km,
            pct=pct,
            bar=bar,
            lube_line=lube_line,
            status_badge=status_badge,
        )
        kb = get_component_details_keyboard(comp.id, comp.bike_id, lang)

    try:
        await query.message.edit_text(body, reply_markup=kb)
    except Exception:
        await query.message.answer(body, reply_markup=kb)

    with contextlib.suppress(Exception):
        await query.answer(t("comp_replaced_success", lang), show_alert=True)


# --- Delete Bike Flow ---


@router.callback_query(F.data.startswith("bike:delete_prompt:"))
async def handle_delete_bike_prompt(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt user for confirmation before deleting bike."""
    if not query.data or not isinstance(query.message, Message):
        return

    bike_id_str = query.data.split(":", 2)[2]
    try:
        bike_id = uuid.UUID(bike_id_str)
    except ValueError:
        await query.answer("Invalid bike ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = select(Bike).where(Bike.id == bike_id)
        bike = (await session.execute(stmt)).scalar_one_or_none()
        if not bike:
            await query.answer("Bike not found", show_alert=True)
            return

        msg_text = t("delete_bike_prompt", lang, bike_name=bike.name)
        kb = get_delete_bike_confirm_keyboard(bike.id, lang)

    await query.message.edit_text(msg_text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("bike:delete_confirm:"))
async def handle_delete_bike_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """Delete bike entity from database and return to bikes list."""
    if not query.data or not isinstance(query.message, Message):
        return

    bike_id_str = query.data.split(":", 2)[2]
    try:
        bike_id = uuid.UUID(bike_id_str)
    except ValueError:
        await query.answer("Invalid bike ID", show_alert=True)
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        stmt = select(Bike).where(Bike.id == bike_id)
        bike = (await session.execute(stmt)).scalar_one_or_none()
        if bike:
            await session.delete(bike)
            await session.commit()

        await query.answer(t("bike_deleted_success", lang), show_alert=True)

    # Return to bikes list
    await handle_list_bikes(query, state)
