"""Extended tests for Telegram bot callback query handlers."""

import random
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.handlers.callbacks import (
    handle_clean_lube_callback,
    handle_replace_callback,
    handle_snooze_callback,
    handle_view_bike_callback,
)
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.db.models.user import User


@pytest.mark.asyncio
async def test_clean_lube_callback_errors(db_session: AsyncSession) -> None:
    """Verify clean_lube callback handles invalid UUID and not-found components."""
    # 1. Invalid UUID
    cb_inv = AsyncMock(spec=CallbackQuery)
    cb_inv.data = "clean_lube:not-a-uuid"
    cb_inv.message = AsyncMock(spec=Message)
    cb_inv.answer = AsyncMock()
    await handle_clean_lube_callback(cb_inv)
    cb_inv.answer.assert_called_with("Invalid component ID", show_alert=True)

    # 2. Not found
    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        cb_nf = AsyncMock(spec=CallbackQuery)
        cb_nf.data = f"clean_lube:{uuid.uuid4()}"
        cb_nf.message = AsyncMock(spec=Message)
        cb_nf.answer = AsyncMock()
        await handle_clean_lube_callback(cb_nf)
        cb_nf.answer.assert_called_with("Component not found", show_alert=True)


@pytest.mark.asyncio
async def test_replace_callback_errors(db_session: AsyncSession) -> None:
    """Verify replace callback handles invalid UUID and not-found components."""
    # 1. Invalid UUID
    cb_inv = AsyncMock(spec=CallbackQuery)
    cb_inv.data = "replace:not-a-uuid"
    cb_inv.message = AsyncMock(spec=Message)
    cb_inv.answer = AsyncMock()
    await handle_replace_callback(cb_inv)
    cb_inv.answer.assert_called_with("Invalid component ID", show_alert=True)

    # 2. Not found
    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        cb_nf = AsyncMock(spec=CallbackQuery)
        cb_nf.data = f"replace:{uuid.uuid4()}"
        cb_nf.message = AsyncMock(spec=Message)
        cb_nf.answer = AsyncMock()
        await handle_replace_callback(cb_nf)
        cb_nf.answer.assert_called_with("Component not found", show_alert=True)


@pytest.mark.asyncio
async def test_snooze_callback() -> None:
    """Verify snooze callback answers user and updates message."""
    cb = AsyncMock(spec=CallbackQuery)
    cb.data = f"snooze:{uuid.uuid4()}"
    cb.message = AsyncMock(spec=Message)
    cb.message.html_text = "<b>Alert: Chain worn</b>"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await handle_snooze_callback(cb)
    cb.answer.assert_called_once()
    cb.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_view_bike_callback_flow(db_session: AsyncSession) -> None:
    """Verify view_bike callback with invalid ID, not found, empty comps, and active comps."""
    # 1. Invalid ID
    cb_inv = AsyncMock(spec=CallbackQuery)
    cb_inv.data = "view_bike:not-a-uuid"
    cb_inv.message = AsyncMock(spec=Message)
    cb_inv.answer = AsyncMock()
    await handle_view_bike_callback(cb_inv)
    cb_inv.answer.assert_called_with("Invalid bike ID", show_alert=True)

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.callbacks.get_session_context", mock_ctx):
        # 2. Not found
        cb_nf = AsyncMock(spec=CallbackQuery)
        cb_nf.data = f"view_bike:{uuid.uuid4()}"
        cb_nf.message = AsyncMock(spec=Message)
        cb_nf.answer = AsyncMock()
        await handle_view_bike_callback(cb_nf)
        cb_nf.answer.assert_called_with("Bike not found", show_alert=True)

        # 3. Bike with no components
        user = User(
            telegram_chat_id=random.randint(10_000_000, 99_999_999),
            first_name="Rider",
            settings={"language": "en"},
        )
        db_session.add(user)
        await db_session.flush()

        bike = Bike(
            user_id=user.id,
            strava_gear_id=f"g_view_{uuid.uuid4().hex[:8]}",
            name="Empty Bike",
            bike_type=BikeType.ROAD,
        )
        db_session.add(bike)
        await db_session.commit()

        cb_empty = AsyncMock(spec=CallbackQuery)
        cb_empty.data = f"view_bike:{bike.id}"
        cb_empty.message = AsyncMock(spec=Message)
        cb_empty.message.answer = AsyncMock()
        cb_empty.answer = AsyncMock()
        await handle_view_bike_callback(cb_empty)
        cb_empty.message.answer.assert_called_once()
        assert "No active components" in cb_empty.message.answer.call_args[0][0]

        # 4. Bike with active component
        bike2 = Bike(
            user_id=user.id,
            strava_gear_id=f"g_view2_{uuid.uuid4().hex[:8]}",
            name="Equipped Bike",
            bike_type=BikeType.ROAD,
        )
        db_session.add(bike2)
        await db_session.flush()

        comp = Component(
            bike_id=bike2.id,
            component_type=ComponentType.CHAIN,
            brand_model="KMC X11",
            current_wear_points=Decimal("500.00"),
            lifespan_wear_points=Decimal("2000.00"),
            status=ComponentStatus.OPTIMAL,
        )
        db_session.add(comp)
        await db_session.commit()

        cb_active = AsyncMock(spec=CallbackQuery)
        cb_active.data = f"view_bike:{bike2.id}"
        cb_active.message = AsyncMock(spec=Message)
        cb_active.message.answer = AsyncMock()
        cb_active.answer = AsyncMock()
        await handle_view_bike_callback(cb_active)
        assert "KMC X11" in cb_active.message.answer.call_args[0][0]
