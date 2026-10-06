"""Telegram bot callback query handlers for interactive inline buttons."""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.bot.utils.formatters import (
    get_component_icon,
    get_status_badge,
    render_progress_bar,
)
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import ComponentStatus, MaintenanceType
from velopulse.db.models.maintenance import MaintenanceLog
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.callbacks")
router = Router(name="callbacks")


@router.callback_query(lambda c: c.data and c.data.startswith("clean_lube:"))
async def handle_clean_lube_callback(query: CallbackQuery) -> None:
    """Handle [✅ Clean & Lube] action button: record maintenance and improve wear condition."""
    if not query.data or not isinstance(query.message, Message):
        return

    comp_id_str = query.data.split(":", 1)[1]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    async with get_session_context() as session:
        stmt = (
            select(Component).where(Component.id == comp_id).options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()

        if not comp:
            await query.answer("Component not found", show_alert=True)
            return

        # 1. Record minor wear reduction benefit (5% wear reduction for cleaning & lubrication)
        reduction = comp.current_wear_points * Decimal("0.05")
        comp.current_wear_points = max(Decimal("0.00"), comp.current_wear_points - reduction)

        # 2. Re-evaluate status
        ratio = float(comp.current_wear_points) / float(comp.lifespan_wear_points)
        if ratio < 0.60:
            comp.status = ComponentStatus.OPTIMAL

        # 3. Create MaintenanceLog record
        if comp.bike:
            log_entry = MaintenanceLog(
                user_id=comp.bike.user_id,
                component_id=comp.id,
                log_type=MaintenanceType.CLEAN_AND_LUBE,
                performed_at=datetime.now(UTC),
                description=f"Cleaned & lubricated via Telegram bot inline action. Wear points adjusted by -{reduction:.1f} WP.",
            )
            session.add(log_entry)

        await session.commit()

        await query.answer("✅ Maintenance recorded! Component cleaned & lubed.", show_alert=True)

        # Update message in-place
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        updated_text = (
            f"{query.message.html_text}\n\n"
            f"✅ <b>Action Recorded:</b> Cleaned & Lubed on {now_str} (-{reduction:.1f} WP)"
        )
        try:
            await query.message.edit_text(updated_text, reply_markup=None)
        except Exception as exc:
            logger.debug("Failed to edit message in place: %s", exc)


@router.callback_query(lambda c: c.data and c.data.startswith("replace:"))
async def handle_replace_callback(query: CallbackQuery) -> None:
    """Handle [🔄 Replace Part] action button: reset component wear baseline to 0."""
    if not query.data or not isinstance(query.message, Message):
        return

    comp_id_str = query.data.split(":", 1)[1]
    try:
        comp_id = uuid.UUID(comp_id_str)
    except ValueError:
        await query.answer("Invalid component ID", show_alert=True)
        return

    async with get_session_context() as session:
        stmt = (
            select(Component).where(Component.id == comp_id).options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()

        if not comp:
            await query.answer("Component not found", show_alert=True)
            return

        old_wear = comp.current_wear_points
        comp.current_wear_points = Decimal("0.00")
        comp.status = ComponentStatus.NEW

        # Record maintenance log
        if comp.bike:
            log_entry = MaintenanceLog(
                user_id=comp.bike.user_id,
                component_id=comp.id,
                log_type=MaintenanceType.REPLACE,
                performed_at=datetime.now(UTC),
                description=f"Component replaced via Telegram bot. Previous wear was {old_wear:.1f} WP.",
            )
            session.add(log_entry)

        await session.commit()

        await query.answer("🔄 Part replaced! Wear points reset to 0 WP.", show_alert=True)

        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        updated_text = (
            f"{query.message.html_text}\n\n"
            f"🔄 <b>Action Recorded:</b> Component replaced on {now_str} (Reset to 0 WP)"
        )
        try:
            await query.message.edit_text(updated_text, reply_markup=None)
        except Exception as exc:
            logger.debug("Failed to edit message in place: %s", exc)


@router.callback_query(lambda c: c.data and c.data.startswith("snooze:"))
async def handle_snooze_callback(query: CallbackQuery) -> None:
    """Handle [⏸️ Snooze] action button."""
    if not isinstance(query.message, Message):
        return

    await query.answer("⏸️ Alert snoozed for future rides.", show_alert=False)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    updated_text = f"{query.message.html_text}\n\n<i>⏸️ Snoozed by user on {now_str}</i>"
    try:
        await query.message.edit_text(updated_text, reply_markup=None)
    except Exception as exc:
        logger.debug("Failed to edit message in place: %s", exc)


@router.callback_query(lambda c: c.data and c.data.startswith("view_bike:"))
async def handle_view_bike_callback(query: CallbackQuery) -> None:
    """Handle [🔍 View Bike] button: display active components for a specific bike."""
    if not query.data or not isinstance(query.message, Message):
        return

    bike_id_str = query.data.split(":", 1)[1]
    try:
        bike_id = uuid.UUID(bike_id_str)
    except ValueError:
        await query.answer("Invalid bike ID", show_alert=True)
        return

    async with get_session_context() as session:
        stmt = select(Bike).where(Bike.id == bike_id).options(selectinload(Bike.components))
        bike = (await session.execute(stmt)).scalar_one_or_none()

        if not bike:
            await query.answer("Bike not found", show_alert=True)
            return

        active_comps = [c for c in bike.components if c.retired_at is None]
        lines = [f"🚴 <b>{bike.name}</b> — Component Telemetry\n"]

        if not active_comps:
            lines.append("No active components registered for this bicycle.")
        else:
            for comp in active_comps:
                icon = get_component_icon(comp.component_type)
                curr = float(comp.current_wear_points)
                max_wp = float(comp.lifespan_wear_points)
                pct = (curr / max_wp) * 100.0 if max_wp > 0 else 100.0
                bar = render_progress_bar(pct, length=10)
                badge = get_status_badge(comp.status)
                lines.append(
                    f"{icon} <b>{comp.brand_model}</b>\n"
                    f"   {bar} ({curr:,.0f} / {max_wp:,.0f} WP)\n"
                    f"   Status: {badge}\n"
                )

        await query.answer()
        await query.message.answer("\n".join(lines))
