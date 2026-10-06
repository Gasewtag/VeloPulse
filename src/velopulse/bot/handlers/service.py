"""Telegram bot FSM conversational wizard for /service maintenance logging."""

import logging
import uuid
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_service_bikes_keyboard,
    get_service_components_keyboard,
    get_service_skip_cost_keyboard,
    get_service_skip_notes_keyboard,
    get_service_types_keyboard,
)
from velopulse.bot.states import ServiceStates
from velopulse.bot.utils.helpers import get_user_by_chat_id, get_user_language
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import MaintenanceType
from velopulse.db.session import get_session_context
from velopulse.services.maintenance import MaintenanceService

logger = logging.getLogger("velopulse.bot.service")
router = Router(name="service")
maintenance_service = MaintenanceService()


def parse_cost_input(raw: str) -> Decimal | None:
    """Parse monetary cost from text input (e.g. '25.50', '25,50', '0', '$15')."""
    clean = (
        raw.replace("$", "")
        .replace("€", "")
        .replace("₽", "")
        .replace("rub", "")
        .replace("usd", "")
        .replace("eur", "")
        .replace(",", ".")
        .replace(" ", "")
        .strip()
    )
    try:
        val = Decimal(clean)
        return val if val >= Decimal("0.00") else None
    except (InvalidOperation, ValueError):
        return None


@router.message(Command("cancel"))
@router.callback_query(F.data == "service:cancel")
async def handle_cancel_service(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Cancel active maintenance wizard and clear conversational FSM state."""
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id  # type: ignore[union-attr]

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    msg_text = t("service_cancelled", lang)
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            await event.message.edit_text(msg_text)
        await event.answer()
    else:
        await event.answer(msg_text)


@router.message(Command("service"))
async def handle_service_command(message: Message, state: FSMContext) -> None:
    """Initiate step-by-step conversational maintenance logging wizard."""
    await state.clear()
    chat_id = message.chat.id

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if not user:
            await message.answer(t("profile_not_setup", "en"))
            return

        bikes_stmt = (
            select(Bike)
            .where(Bike.user_id == user.id, Bike.is_active.is_(True))
            .order_by(Bike.created_at.asc())
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

        if not bikes:
            await message.answer(t("service_no_bikes", lang))
            return

        await state.set_state(ServiceStates.selecting_bike)
        await state.update_data(user_id=str(user.id), language=lang)
        await message.answer(
            t("service_start", lang),
            reply_markup=get_service_bikes_keyboard(bikes, lang),
        )


@router.callback_query(ServiceStates.selecting_bike, F.data.startswith("service:bike:"))
async def handle_bike_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Handle bike selection in service wizard and prompt for component."""
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

    async with get_session_context() as session:
        bike_stmt = (
            select(Bike)
            .where(Bike.id == bike_id)
            .options(selectinload(Bike.components))
        )
        bike = (await session.execute(bike_stmt)).scalar_one_or_none()
        if not bike:
            await query.answer("Bike not found", show_alert=True)
            return

        active_components = [c for c in bike.components if c.retired_at is None]
        if not active_components:
            await query.message.edit_text(t("service_no_components", lang))
            await query.answer()
            await state.clear()
            return

        await state.update_data(bike_id=str(bike.id), bike_name=bike.name)
        await state.set_state(ServiceStates.selecting_component)

        await query.message.edit_text(
            t("service_select_component", lang, bike_name=bike.name),
            reply_markup=get_service_components_keyboard(active_components, lang),
        )
    await query.answer()


@router.callback_query(ServiceStates.selecting_component, F.data.startswith("service:comp:"))
async def handle_component_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Handle component selection in service wizard and prompt for maintenance action."""
    if not query.data or not isinstance(query.message, Message):
        return

    comp_id_str = query.data.split(":", 2)[2]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    data = await state.get_data()
    lang = data.get("language", "en")

    async with get_session_context() as session:
        comp_stmt = select(Component).where(Component.id == comp_id)
        comp = (await session.execute(comp_stmt)).scalar_one_or_none()
        if not comp:
            await query.answer("Component not found", show_alert=True)
            return

        await state.update_data(
            component_id=str(comp.id),
            component_name=comp.brand_model,
            component_type=comp.component_type.value,
        )
        await state.set_state(ServiceStates.selecting_service_type)

        await query.message.edit_text(
            t("service_select_type", lang, component_name=comp.brand_model),
            reply_markup=get_service_types_keyboard(lang),
        )
    await query.answer()


@router.callback_query(ServiceStates.selecting_service_type, F.data.startswith("service:type:"))
async def handle_service_type_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Handle service type selection and prompt for technician notes."""
    if not query.data or not isinstance(query.message, Message):
        return

    type_val = query.data.split(":", 2)[2]
    try:
        m_type = MaintenanceType(type_val)
    except ValueError:
        await query.answer("Invalid maintenance type", show_alert=True)
        return

    data = await state.get_data()
    lang = data.get("language", "en")

    await state.update_data(service_type=m_type.value)
    await state.set_state(ServiceStates.entering_notes)

    await query.message.edit_text(
        t("service_enter_notes", lang),
        reply_markup=get_service_skip_notes_keyboard(lang),
    )
    await query.answer()


@router.callback_query(ServiceStates.entering_notes, F.data == "service:skip_notes")
async def handle_skip_notes_callback(query: CallbackQuery, state: FSMContext) -> None:
    """Skip entering technician notes and prompt for cost."""
    if not isinstance(query.message, Message):
        return

    data = await state.get_data()
    lang = data.get("language", "en")

    await state.update_data(notes=None)
    await state.set_state(ServiceStates.entering_cost)

    await query.message.edit_text(
        t("service_enter_cost", lang),
        reply_markup=get_service_skip_cost_keyboard(lang),
    )
    await query.answer()


@router.message(ServiceStates.entering_notes)
async def handle_notes_message(message: Message, state: FSMContext) -> None:
    """Record technician notes text and prompt for cost."""
    notes = message.text.strip() if message.text else None
    data = await state.get_data()
    lang = data.get("language", "en")

    await state.update_data(notes=notes)
    await state.set_state(ServiceStates.entering_cost)

    await message.answer(
        t("service_enter_cost", lang),
        reply_markup=get_service_skip_cost_keyboard(lang),
    )


@router.callback_query(ServiceStates.entering_cost, F.data == "service:skip_cost")
async def handle_skip_cost_callback(query: CallbackQuery, state: FSMContext) -> None:
    """Process zero/free cost and finalize maintenance logging."""
    if not isinstance(query.message, Message):
        return

    await query.answer()
    await _finalize_maintenance_log(
        event_target=query.message,
        cost=Decimal("0.00"),
        state=state,
    )


@router.message(ServiceStates.entering_cost)
async def handle_cost_message(message: Message, state: FSMContext) -> None:
    """Validate numeric cost input and finalize maintenance logging."""
    data = await state.get_data()
    lang = data.get("language", "en")

    raw_text = message.text or ""
    cost = parse_cost_input(raw_text)

    if cost is None:
        await message.answer(
            t("service_invalid_cost", lang),
            reply_markup=get_service_skip_cost_keyboard(lang),
        )
        return

    await _finalize_maintenance_log(
        event_target=message,
        cost=cost,
        state=state,
    )


async def _finalize_maintenance_log(
    event_target: Message,
    cost: Decimal,
    state: FSMContext,
) -> None:
    """Persist maintenance log or replacement and respond with summary confirmation."""
    data = await state.get_data()
    lang = data.get("language", "en")
    user_id = uuid.UUID(data["user_id"])
    comp_id = uuid.UUID(data["component_id"])
    bike_name = data.get("bike_name", "Bike")
    comp_name = data.get("component_name", "Component")
    service_type = MaintenanceType(data["service_type"])
    notes = data.get("notes")

    async with get_session_context() as session:
        if service_type == MaintenanceType.REPLACE:
            old_comp, new_comp, _log = await maintenance_service.replace_component(
                session=session,
                user_id=user_id,
                component_id=comp_id,
                cost=cost,
                description=notes,
            )
            await session.commit()

            summary = t(
                "service_replace_success",
                lang,
                bike_name=bike_name,
                old_name=old_comp.brand_model,
                new_name=new_comp.brand_model,
                cost=f"{cost:,.2f}",
            )
        else:
            _comp, log = await maintenance_service.record_maintenance(
                session=session,
                user_id=user_id,
                component_id=comp_id,
                log_type=service_type,
                description=notes,
                cost=cost,
            )
            await session.commit()

            action_key = f"btn_service_{service_type.value}"
            # map short names to button labels
            type_map = {
                MaintenanceType.CLEAN_AND_LUBE: "btn_service_lube",
                MaintenanceType.INSPECT_TUNE: "btn_service_inspect",
                MaintenanceType.REPAIR: "btn_service_repair",
                MaintenanceType.SEASON_PREP: "btn_service_season",
            }
            action_label = t(type_map.get(service_type, action_key), lang)
            notes_display = notes if notes else t("service_notes_skipped", lang)
            odo_display = f"{log.odometer_km:.1f}" if log.odometer_km is not None else "0.0"

            summary = t(
                "service_success",
                lang,
                bike_name=bike_name,
                component_name=comp_name,
                action=action_label,
                notes=notes_display,
                cost=f"{cost:,.2f}",
                odometer_km=odo_display,
            )

    await state.clear()
    await event_target.answer(summary)
