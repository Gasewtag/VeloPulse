"""Tests for VeloPulse Telegram bot formatters, handlers, keyboards, and FSM flows."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.handlers.bikes import (
    handle_bike_model_entered,
    handle_bike_type_selected,
    handle_cassette_preset,
    handle_chain_lube_preset,
    handle_chain_preset,
    handle_component_view,
    handle_front_brake_preset,
    handle_front_brake_type,
    handle_front_tire_preset,
    handle_rear_brake_preset,
    handle_rear_brake_type,
    handle_rear_tire_preset,
    handle_replace_confirm,
    handle_replace_prompt,
    handle_start_bike_creation,
    parse_mileage_input,
)
from velopulse.bot.handlers.callbacks import (
    handle_clean_lube_callback,
    handle_replace_callback,
    handle_snooze_callback,
    handle_view_bike_callback,
)
from velopulse.bot.handlers.profile import handle_open_strava
from velopulse.bot.handlers.settings import (
    handle_delete_account_confirm,
    handle_delete_account_prompt,
    handle_language_command,
    handle_open_settings,
    handle_open_settings_language,
    handle_settings_set_language,
)
from velopulse.bot.handlers.start import (
    handle_help,
    handle_language_selection,
    handle_open_profile,
    handle_start_deeplink,
    handle_start_plain,
    handle_uncompleted_profile_message,
)
from velopulse.bot.handlers.status import (
    handle_bikes,
    handle_components,
    handle_status,
)
from velopulse.bot.keyboards import (
    get_bike_type_keyboard,
    get_bikes_list_keyboard,
    get_brake_type_keyboard,
    get_language_keyboard,
    get_mileage_preset_keyboard,
    get_profile_menu_keyboard,
    get_profile_prompt_keyboard,
    get_settings_keyboard,
    get_settings_language_keyboard,
)
from velopulse.bot.states import (
    BikeCreationStates,
    ProfileStates,
)
from velopulse.bot.utils.formatters import (
    get_component_icon,
    get_status_badge,
    render_progress_bar,
)
from velopulse.core.security import encrypt_token
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.db.models.user import User


def test_render_progress_bar() -> None:
    """Verify progress bar generation for various wear percentages."""
    assert render_progress_bar(0.0, length=10) == "[░░░░░░░░░░] 0.0%"
    assert render_progress_bar(50.0, length=10) == "[█████░░░░░] 50.0%"
    assert render_progress_bar(100.0, length=10) == "[██████████] 100.0%"
    assert render_progress_bar(80.0, length=10, with_brackets=False) == "████████░░ 80%"


def test_get_status_badge() -> None:
    """Verify status badges correctly map to indicators."""
    assert "NEW" in get_status_badge(ComponentStatus.NEW)
    assert "OPTIMAL" in get_status_badge(ComponentStatus.OPTIMAL)
    assert "ATTENTION NEEDED" in get_status_badge(ComponentStatus.ATTENTION_NEEDED)
    assert "REPLACE RECOMMENDED" in get_status_badge(ComponentStatus.REPLACE_RECOMMENDED)
    assert "CRITICAL / OVERDUE" in get_status_badge(ComponentStatus.RETIRED)


def test_get_component_icon() -> None:
    """Verify component type icons return appropriate emojis."""
    assert get_component_icon(ComponentType.CHAIN) == "⛓️"
    assert get_component_icon(ComponentType.CASSETTE) == "⚙️"
    assert get_component_icon(ComponentType.FRONT_TIRE) == "🛞"
    assert get_component_icon(ComponentType.FRONT_BRAKE_PAD) == "🛑"


def test_parse_mileage_input() -> None:
    """Verify mileage parsing from raw user strings."""
    assert parse_mileage_input("1250") == 1250.0
    assert parse_mileage_input("1250 km") == 1250.0
    assert parse_mileage_input("1 250 км") == 1250.0
    assert parse_mileage_input("0") == 0.0
    assert parse_mileage_input("-50") is None
    assert parse_mileage_input("invalid") is None


def test_keyboards_structure() -> None:
    """Verify keyboard builders return valid inline keyboards."""
    lang_kb = get_language_keyboard()
    assert len(lang_kb.inline_keyboard) == 1
    assert len(lang_kb.inline_keyboard[0]) == 2

    profile_prompt_kb = get_profile_prompt_keyboard("en")
    assert len(profile_prompt_kb.inline_keyboard) == 1

    profile_menu_kb = get_profile_menu_keyboard("en")
    assert len(profile_menu_kb.inline_keyboard) == 3

    type_kb = get_bike_type_keyboard("en")
    assert len(type_kb.inline_keyboard) == 4

    preset_kb = get_mileage_preset_keyboard("en")
    assert len(preset_kb.inline_keyboard) == 3

    brake_kb = get_brake_type_keyboard("en")
    assert len(brake_kb.inline_keyboard) == 2

    settings_kb = get_settings_keyboard("en")
    assert len(settings_kb.inline_keyboard) == 3

    lang_kb = get_settings_language_keyboard("en")
    assert len(lang_kb.inline_keyboard) == 2


def test_bikes_list_keyboard_limit() -> None:
    """Verify bike list keyboard respects 3-bike limit."""
    mock_bikes = [
        MagicMock(spec=Bike, id=uuid.uuid4(), name="Bike 1"),
        MagicMock(spec=Bike, id=uuid.uuid4(), name="Bike 2"),
    ]
    kb_2 = get_bikes_list_keyboard(mock_bikes, "en")
    btn_texts_2 = [btn.text for row in kb_2.inline_keyboard for btn in row]
    assert any("Create bike" in b for b in btn_texts_2)

    mock_bikes.append(MagicMock(spec=Bike, id=uuid.uuid4(), name="Bike 3"))
    kb_3 = get_bikes_list_keyboard(mock_bikes, "en")
    btn_texts_3 = [btn.text for row in kb_3.inline_keyboard for btn in row]
    assert not any("Create bike" in b for b in btn_texts_3)


@pytest.mark.asyncio
async def test_handle_start_plain_unlinked(db_session: AsyncSession) -> None:
    """Verify plain /start asks for language selection without greeting."""
    msg = AsyncMock(spec=Message)
    msg.from_user = TgUser(id=12345, is_bot=False, first_name="Alex")
    msg.chat = Chat(id=12345, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_start_plain(msg)

    msg.answer.assert_called_once()
    assert "Please select your language:" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_start_plain_linked(db_session: AsyncSession) -> None:
    """Verify plain /start asks for language selection even when linked."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=random.randint(10_000_000, 99_999_999),
        first_name="Serena",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=chat_id,
    )
    db_session.add(user)
    await db_session.commit()

    msg = AsyncMock(spec=Message)
    msg.from_user = TgUser(id=chat_id, is_bot=False, first_name="Serena")
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_start_plain(msg)

    msg.answer.assert_called_once()
    assert "Please select your language:" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_start_deeplink_valid_uuid(db_session: AsyncSession) -> None:
    """Verify deep-linked /start with valid UUID links telegram_chat_id and prompts language."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Marco",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    chat_id = random.randint(10_000_000, 99_999_999)
    msg = AsyncMock(spec=Message)
    msg.from_user = TgUser(id=chat_id, is_bot=False, first_name="Marco")
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    cmd = CommandObject(prefix="/", command="start", args=str(user.id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_start_deeplink(msg, cmd)

    await db_session.refresh(user)
    assert user.telegram_chat_id == chat_id
    msg.answer.assert_called_once()
    assert "Please select your language:" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_help() -> None:
    """Verify /help returns list of bot commands and wear mechanics."""
    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=123, type="private")
    msg.answer = AsyncMock()

    await handle_help(msg)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "/status" in text
    assert "/bikes" in text
    assert "/components" in text
    assert "Wear Points" in text


@pytest.mark.asyncio
async def test_language_selection_en(db_session: AsyncSession) -> None:
    """Verify selecting English saves setting and greets user dynamically."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(telegram_chat_id=chat_id, first_name="Oliver")
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "set_lang:en"
    cb.from_user = TgUser(id=chat_id, is_bot=False, first_name="Oliver")
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_language_selection(cb, state)

    await db_session.refresh(user)
    assert user.settings.get("language") == "en"

    cb.message.edit_text.assert_called_once()
    text = cb.message.edit_text.call_args[0][0]
    assert "Hello, Oliver! Welcome to VeloPulse." in text
    current_state = await state.get_state()
    assert current_state == ProfileStates.awaiting_profile_setup.state


@pytest.mark.asyncio
async def test_language_selection_ru(db_session: AsyncSession) -> None:
    """Verify selecting Russian saves setting and greets user in Russian."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(telegram_chat_id=chat_id, first_name="Дмитрий")
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "set_lang:ru"
    cb.from_user = TgUser(id=chat_id, is_bot=False, first_name="Дмитрий")
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_language_selection(cb, state)

    await db_session.refresh(user)
    assert user.settings.get("language") == "ru"

    cb.message.edit_text.assert_called_once()
    text = cb.message.edit_text.call_args[0][0]
    assert "Привет, Дмитрий! Добро пожаловать в VeloPulse." in text


@pytest.mark.asyncio
async def test_profile_not_setup_block(db_session: AsyncSession) -> None:
    """Verify user is blocked from bypassing profile setup."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Elena",
        settings={"language": "en", "profile_setup_completed": False},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )
    await state.set_state(ProfileStates.awaiting_profile_setup)

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_uncompleted_profile_message(msg, state)

    msg.answer.assert_called_once()
    assert "Your profile is not set up yet" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_open_profile_menu(db_session: AsyncSession) -> None:
    """Verify opening profile marks profile completed and shows Profile menu."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Lucas",
        settings={"language": "en", "profile_setup_completed": False},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )
    await state.set_state(ProfileStates.awaiting_profile_setup)

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "open:profile"
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.start.get_session_context", mock_ctx):
        await handle_open_profile(cb, state)

    await db_session.refresh(user)
    assert user.settings.get("profile_setup_completed") is True
    assert (await state.get_state()) is None
    cb.message.edit_text.assert_called_once()
    assert "Profile Setup & Management" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_open_strava(db_session: AsyncSession) -> None:
    """Verify Strava integration view displays connection instructions."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Anna",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "open:strava"
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.profile.get_session_context", mock_ctx):
        await handle_open_strava(cb, state)

    cb.message.edit_text.assert_called_once()
    text = cb.message.edit_text.call_args[0][0]
    assert "Strava Integration" in text
    assert "Not connected" in text


@pytest.mark.asyncio
async def test_create_bike_wizard_full_flow(db_session: AsyncSession) -> None:
    """Verify complete multi-step bike creation wizard creates Bike & Components."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Rider",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # Step 1: Start bike creation
    cb1 = AsyncMock(spec=CallbackQuery)
    cb1.data = "bike:create"
    cb1.message = AsyncMock(spec=Message)
    cb1.message.chat = Chat(id=chat_id, type="private")
    cb1.message.edit_text = AsyncMock()
    cb1.answer = AsyncMock()

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        await handle_start_bike_creation(cb1, state)

    assert await state.get_state() == BikeCreationStates.selecting_bike_type.state

    # Step 2: Select bike type Road
    cb2 = AsyncMock(spec=CallbackQuery)
    cb2.data = "bike_type:road"
    cb2.message = AsyncMock(spec=Message)
    cb2.message.chat = Chat(id=chat_id, type="private")
    cb2.message.edit_text = AsyncMock()
    cb2.answer = AsyncMock()

    await handle_bike_type_selected(cb2, state)
    assert await state.get_state() == BikeCreationStates.entering_model.state

    # Step 3: Enter model name
    msg_model = AsyncMock(spec=Message)
    msg_model.text = "Trek Domane AL 5"
    msg_model.answer = AsyncMock()

    await handle_bike_model_entered(msg_model, state)
    assert await state.get_state() == BikeCreationStates.entering_cassette_mileage.state

    # Step 4: Cassette mileage 1000 km
    cb_cass = AsyncMock(spec=CallbackQuery)
    cb_cass.data = "preset_km:1000"
    cb_cass.message = AsyncMock(spec=Message)
    cb_cass.message.edit_text = AsyncMock()
    cb_cass.answer = AsyncMock()
    await handle_cassette_preset(cb_cass, state)
    assert await state.get_state() == BikeCreationStates.entering_chain_mileage.state

    # Step 5: Chain mileage 500 km
    cb_chain = AsyncMock(spec=CallbackQuery)
    cb_chain.data = "preset_km:500"
    cb_chain.message = AsyncMock(spec=Message)
    cb_chain.message.edit_text = AsyncMock()
    cb_chain.answer = AsyncMock()
    await handle_chain_preset(cb_chain, state)
    assert await state.get_state() == BikeCreationStates.entering_chain_lube_mileage.state

    # Step 5b: Chain lube mileage
    cb_lube = AsyncMock(spec=CallbackQuery)
    cb_lube.data = "preset_lube:50"
    cb_lube.message = AsyncMock(spec=Message)
    cb_lube.message.edit_text = AsyncMock()
    cb_lube.answer = AsyncMock()
    await handle_chain_lube_preset(cb_lube, state)
    assert await state.get_state() == BikeCreationStates.entering_front_tire_mileage.state

    # Step 6: Front tire mileage 500 km
    cb_ftire = AsyncMock(spec=CallbackQuery)
    cb_ftire.data = "preset_km:500"
    cb_ftire.message = AsyncMock(spec=Message)
    cb_ftire.message.edit_text = AsyncMock()
    cb_ftire.answer = AsyncMock()
    await handle_front_tire_preset(cb_ftire, state)
    assert await state.get_state() == BikeCreationStates.entering_rear_tire_mileage.state

    # Step 7: Rear tire mileage 500 km
    cb_rtire = AsyncMock(spec=CallbackQuery)
    cb_rtire.data = "preset_km:500"
    cb_rtire.message = AsyncMock(spec=Message)
    cb_rtire.message.edit_text = AsyncMock()
    cb_rtire.answer = AsyncMock()
    await handle_rear_tire_preset(cb_rtire, state)
    assert await state.get_state() == BikeCreationStates.selecting_front_brake_type.state

    # Step 8: Front brake type Disc
    cb_fb_type = AsyncMock(spec=CallbackQuery)
    cb_fb_type.data = "brake_type:disc"
    cb_fb_type.message = AsyncMock(spec=Message)
    cb_fb_type.message.edit_text = AsyncMock()
    cb_fb_type.answer = AsyncMock()
    await handle_front_brake_type(cb_fb_type, state)
    assert await state.get_state() == BikeCreationStates.entering_front_brake_mileage.state

    # Step 9: Front brake mileage 500 km
    cb_fb_km = AsyncMock(spec=CallbackQuery)
    cb_fb_km.data = "preset_km:500"
    cb_fb_km.message = AsyncMock(spec=Message)
    cb_fb_km.message.edit_text = AsyncMock()
    cb_fb_km.answer = AsyncMock()
    await handle_front_brake_preset(cb_fb_km, state)
    assert await state.get_state() == BikeCreationStates.selecting_rear_brake_type.state

    # Step 10: Rear brake type Disc
    cb_rb_type = AsyncMock(spec=CallbackQuery)
    cb_rb_type.data = "brake_type:disc"
    cb_rb_type.message = AsyncMock(spec=Message)
    cb_rb_type.message.edit_text = AsyncMock()
    cb_rb_type.answer = AsyncMock()
    await handle_rear_brake_type(cb_rb_type, state)
    assert await state.get_state() == BikeCreationStates.entering_rear_brake_mileage.state

    # Step 11: Rear brake mileage 500 km -> Road bike finishes here!
    cb_rb_km = AsyncMock(spec=CallbackQuery)
    cb_rb_km.data = "preset_km:500"
    cb_rb_km.message = AsyncMock(spec=Message)
    cb_rb_km.message.chat = Chat(id=chat_id, type="private")
    cb_rb_km.message.edit_text = AsyncMock()
    cb_rb_km.answer = AsyncMock()

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        await handle_rear_brake_preset(cb_rb_km, state)

    # State cleared after successful creation
    assert (await state.get_state()) is None
    cb_rb_km.message.edit_text.assert_called_once()
    assert (
        "Your bike has been created successfully! 🚲" in cb_rb_km.message.edit_text.call_args[0][0]
    )


@pytest.mark.asyncio
async def test_component_view_and_replace(db_session: AsyncSession) -> None:
    """Verify component details screen and replacement flow."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Rider",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"tg_test_{uuid.uuid4().hex[:8]}",
        name="Canyon Grail",
        bike_type=BikeType.GRAVEL,
    )
    db_session.add(bike)
    await db_session.commit()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="KMC 11-speed Chain",
        lifespan_wear_points=Decimal("4000.00"),
        current_wear_points=Decimal("3200.00"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )
    db_session.add(comp)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # 1. View Component
    cb_view = AsyncMock(spec=CallbackQuery)
    cb_view.data = f"comp:view:{comp.id}"
    cb_view.message = AsyncMock(spec=Message)
    cb_view.message.chat = Chat(id=chat_id, type="private")
    cb_view.message.edit_text = AsyncMock()
    cb_view.answer = AsyncMock()

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        await handle_component_view(cb_view, state)

    cb_view.message.edit_text.assert_called_once()
    text = cb_view.message.edit_text.call_args[0][0]
    assert "KMC 11-speed Chain" in text
    assert "3,200.0 km" in text
    assert "80%" in text
    assert "Lubrication:" in text

    # 2. Replace Prompt
    cb_prompt = AsyncMock(spec=CallbackQuery)
    cb_prompt.data = f"comp:replace_prompt:{comp.id}"
    cb_prompt.message = AsyncMock(spec=Message)
    cb_prompt.message.chat = Chat(id=chat_id, type="private")
    cb_prompt.message.edit_text = AsyncMock()
    cb_prompt.answer = AsyncMock()

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        await handle_replace_prompt(cb_prompt, state)

    assert (
        "Are you sure you want to replace this component?"
        in cb_prompt.message.edit_text.call_args[0][0]
    )

    # 3. Replace Confirm
    cb_confirm = AsyncMock(spec=CallbackQuery)
    cb_confirm.data = f"comp:replace_confirm:{comp.id}"
    cb_confirm.message = AsyncMock(spec=Message)
    cb_confirm.message.chat = Chat(id=chat_id, type="private")
    cb_confirm.message.edit_text = AsyncMock()
    cb_confirm.answer = AsyncMock()

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        await handle_replace_confirm(cb_confirm, state)

    await db_session.refresh(comp)
    assert comp.current_wear_points == Decimal("0.00")
    assert comp.status == ComponentStatus.NEW
    cb_confirm.answer.assert_any_call(
        "Component has been successfully replaced! 🔄", show_alert=True
    )


@pytest.mark.asyncio
async def test_settings_and_delete_account(db_session: AsyncSession) -> None:
    """Verify settings menu and account deletion flow."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Temporary User",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # 1. Open Settings
    cb_set = AsyncMock(spec=CallbackQuery)
    cb_set.data = "open:settings"
    cb_set.message = AsyncMock(spec=Message)
    cb_set.message.chat = Chat(id=chat_id, type="private")
    cb_set.message.edit_text = AsyncMock()
    cb_set.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_open_settings(cb_set, state)

    assert "Settings" in cb_set.message.edit_text.call_args[0][0]

    # 2. Delete Account Prompt
    cb_del_prompt = AsyncMock(spec=CallbackQuery)
    cb_del_prompt.data = "settings:delete_account_prompt"
    cb_del_prompt.message = AsyncMock(spec=Message)
    cb_del_prompt.message.chat = Chat(id=chat_id, type="private")
    cb_del_prompt.message.edit_text = AsyncMock()
    cb_del_prompt.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_delete_account_prompt(cb_del_prompt, state)

    assert (
        "Are you sure you want to delete your account?"
        in cb_del_prompt.message.edit_text.call_args[0][0]
    )

    # 3. Delete Account Confirm
    cb_del_confirm = AsyncMock(spec=CallbackQuery)
    cb_del_confirm.data = "settings:delete_account_confirm"
    cb_del_confirm.message = AsyncMock(spec=Message)
    cb_del_confirm.message.chat = Chat(id=chat_id, type="private")
    cb_del_confirm.message.edit_text = AsyncMock()
    cb_del_confirm.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_delete_account_confirm(cb_del_confirm, state)

    cb_del_confirm.message.edit_text.assert_called_once()
    assert "Your account has been deleted." in cb_del_confirm.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_settings_language_switch(db_session: AsyncSession) -> None:
    """Verify switching language via settings and /language command."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        first_name="LangUser",
        telegram_chat_id=chat_id,
        settings={"language": "en", "profile_setup_completed": True},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # 1. Open Language Menu from Settings
    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "settings:language"
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_open_settings_language(cb, state)

    assert "Please select your language:" in cb.message.edit_text.call_args[0][0]

    # 2. Switch to Russian
    cb_ru = AsyncMock(spec=CallbackQuery)
    cb_ru.data = "settings:set_lang:ru"
    cb_ru.message = AsyncMock(spec=Message)
    cb_ru.message.chat = Chat(id=chat_id, type="private")
    cb_ru.message.edit_text = AsyncMock()
    cb_ru.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_settings_set_language(cb_ru, state)

    await db_session.refresh(user)
    assert user.settings.get("language") == "ru"
    assert "Настройки" in cb_ru.message.edit_text.call_args[0][0]
    assert "Язык изменён на Русский" in cb_ru.answer.call_args[0][0]

    # 3. /language command
    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    with patch("velopulse.bot.handlers.settings.get_session_context", mock_ctx):
        await handle_language_command(msg, state)

    assert "Пожалуйста, выберите язык:" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_status_unlinked_user(db_session: AsyncSession) -> None:
    """Verify /status prompts to link when chat ID is not found."""
    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=111222, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.status.get_session_context", mock_ctx):
        await handle_status(msg)

    msg.answer.assert_called_once()
    assert "Account not linked" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_status_linked_user(db_session: AsyncSession) -> None:
    """Verify /status outputs cockpit overview with active bicycles."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=random.randint(10_000_000, 99_999_999),
        first_name="Elena",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=chat_id,
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Canyon Aeroad",
        bike_type=BikeType.ROAD,
        total_distance_m=1250000,
        total_elevation_m=12000,
        is_active=True,
    )
    db_session.add(bike)
    await db_session.commit()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="KMC X12",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("2600.00"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )
    db_session.add(comp)
    await db_session.commit()

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.status.get_session_context", mock_ctx):
        await handle_status(msg)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "Elena" in text
    assert "KMC X12" in text
    assert "ATTENTION NEEDED" in text


@pytest.mark.asyncio
async def test_handle_bikes(db_session: AsyncSession) -> None:
    """Verify /bikes lists athlete's registered bikes with distance."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=random.randint(10_000_000, 99_999_999),
        first_name="Julian",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=chat_id,
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Specialized Diverge",
        bike_type=BikeType.GRAVEL,
        total_distance_m=850000,
        total_elevation_m=5400,
    )
    db_session.add(bike)
    await db_session.commit()

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.status.get_session_context", mock_ctx):
        await handle_bikes(msg)

    msg.answer.assert_called_once()
    assert "Specialized Diverge" in msg.answer.call_args[0][0]
    assert "850.0 km" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_components(db_session: AsyncSession) -> None:
    """Verify /components lists component wear points and lifespans."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=random.randint(10_000_000, 99_999_999),
        first_name="Sara",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=chat_id,
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Trek Emonda",
        bike_type=BikeType.ROAD,
        total_distance_m=300000,
        total_elevation_m=2000,
    )
    db_session.add(bike)
    await db_session.commit()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="Shimano L05A",
        lifespan_wear_points=Decimal("1500.00"),
        current_wear_points=Decimal("300.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add(comp)
    await db_session.commit()

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.status.get_session_context", mock_ctx):
        await handle_components(msg)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "Shimano L05A" in text
    assert "300 / 1,500 WP" in text


@pytest.mark.asyncio
async def test_handle_clean_lube_callback(db_session: AsyncSession) -> None:
    """Verify clean & lube callback reduces wear points by 5% and logs maintenance."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Rider",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Road Bike",
        bike_type=BikeType.ROAD,
        total_distance_m=0,
        total_elevation_m=0,
    )
    db_session.add(bike)
    await db_session.commit()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Chain",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("1000.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add(comp)
    await db_session.commit()

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = f"clean_lube:{comp.id}"
    cb.answer = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.html_text = "Alert Text"
    cb.message.edit_text = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        await handle_clean_lube_callback(cb)

    await db_session.refresh(comp)
    assert comp.current_wear_points == Decimal("950.00")
    cb.answer.assert_called_once_with(
        "✅ Maintenance recorded! Component cleaned & lubed.", show_alert=True
    )
    cb.message.edit_text.assert_called_once()
    assert "Cleaned & Lubed" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_replace_callback(db_session: AsyncSession) -> None:
    """Verify replace callback resets component wear to 0 and status to NEW."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Rider",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Road Bike",
        bike_type=BikeType.ROAD,
        total_distance_m=0,
        total_elevation_m=0,
    )
    db_session.add(bike)
    await db_session.commit()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Chain",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("3100.00"),
        status=ComponentStatus.REPLACE_RECOMMENDED,
    )
    db_session.add(comp)
    await db_session.commit()

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = f"replace:{comp.id}"
    cb.answer = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.html_text = "Alert Text"
    cb.message.edit_text = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        await handle_replace_callback(cb)

    await db_session.refresh(comp)
    assert comp.current_wear_points == Decimal("0.00")
    assert comp.status == ComponentStatus.NEW
    cb.answer.assert_called_once_with(
        "🔄 Part replaced! Wear points reset to 0 WP.", show_alert=True
    )
    cb.message.edit_text.assert_called_once()
    assert "Component replaced" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_snooze_callback() -> None:
    """Verify snooze callback updates message and acknowledges alert."""
    comp_id = uuid.uuid4()
    cb = AsyncMock(spec=CallbackQuery)
    cb.data = f"snooze:{comp_id}"
    cb.answer = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.html_text = "Alert Text"
    cb.message.edit_text = AsyncMock()

    await handle_snooze_callback(cb)

    cb.answer.assert_called_once_with("⏸️ Alert snoozed for future rides.", show_alert=False)
    cb.message.edit_text.assert_called_once()
    assert "Snoozed by user" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_view_bike_callback(db_session: AsyncSession) -> None:
    """Verify view_bike callback renders components breakdown for the bike."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Rider",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{uuid.uuid4().hex[:10]}",
        name="Giant TCR",
        bike_type=BikeType.ROAD,
        total_distance_m=500000,
        total_elevation_m=3000,
    )
    db_session.add(bike)
    await db_session.commit()

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = f"view_bike:{bike.id}"
    cb.answer = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        await handle_view_bike_callback(cb)

    cb.answer.assert_called_once()
    cb.message.answer.assert_called_once()
    assert "Giant TCR" in cb.message.answer.call_args[0][0]
