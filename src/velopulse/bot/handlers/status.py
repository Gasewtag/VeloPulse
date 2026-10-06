"""Telegram bot status, bikes, and components inspection handlers."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.bot.utils.formatters import (
    get_component_icon,
    get_status_badge,
    render_progress_bar,
)
from velopulse.db.models.bike import Bike
from velopulse.db.models.enums import ComponentStatus
from velopulse.db.models.user import User
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.status")
router = Router(name="status")


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    """Provide a high-level cockpit report highlighting components requiring maintenance."""
    chat_id = message.chat.id

    async with get_session_context() as session:
        user_stmt = select(User).where(User.telegram_chat_id == chat_id)
        user = (await session.execute(user_stmt)).scalar_one_or_none()

        if not user:
            await message.answer(
                "⚠️ <b>Account not linked.</b>\n"
                "Please run /start or link your Strava profile to inspect equipment status."
            )
            return

        bikes_stmt = (
            select(Bike)
            .where(Bike.user_id == user.id, Bike.is_active.is_(True))
            .options(selectinload(Bike.components))
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

        if not bikes:
            await message.answer(
                f"🚴 <b>{user.first_name}'s Cockpit</b>\n\n"
                "No bicycles found in your profile yet. Sync your gear through Strava!"
            )
            return

        critical_items: list[str] = []
        total_components = 0

        for bike in bikes:
            for comp in bike.components:
                if comp.retired_at is not None:
                    continue
                total_components += 1
                if comp.status in (
                    ComponentStatus.ATTENTION_NEEDED,
                    ComponentStatus.REPLACE_RECOMMENDED,
                    ComponentStatus.RETIRED,
                ):
                    icon = get_component_icon(comp.component_type)
                    pct = (
                        (float(comp.current_wear_points) / float(comp.lifespan_wear_points)) * 100.0
                        if comp.lifespan_wear_points > 0
                        else 100.0
                    )
                    badge = get_status_badge(comp.status)
                    bar = render_progress_bar(pct, length=8)
                    critical_items.append(
                        f"{icon} <b>{comp.brand_model}</b> ({bike.name})\n"
                        f"   {bar}\n"
                        f"   Status: {badge}"
                    )

        text_lines = [
            f"📊 <b>Equipment Status Report — {user.first_name}</b>",
            f"🚴 <b>Active Bicycles:</b> {len(bikes)} | 🔩 <b>Total Components:</b> {total_components}\n",
        ]

        if critical_items:
            text_lines.append("⚠️ <b>Components Requiring Attention:</b>")
            text_lines.extend(critical_items)
            text_lines.append("\n<i>Run /components for a full breakdown of all parts.</i>")
        else:
            text_lines.append("🟢 <b>All systems optimal!</b>")
            text_lines.append("Every monitored component is within safe operating tolerances.")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚲 View Bicycles", callback_data="nav:bikes"),
                    InlineKeyboardButton(text="🔩 All Components", callback_data="nav:components"),
                ]
            ]
        )

        await message.answer("\n".join(text_lines), reply_markup=keyboard)


@router.message(Command("bikes"))
async def handle_bikes(message: Message) -> None:
    """List all registered bicycles with distance and component count."""
    chat_id = message.chat.id

    async with get_session_context() as session:
        user_stmt = select(User).where(User.telegram_chat_id == chat_id)
        user = (await session.execute(user_stmt)).scalar_one_or_none()

        if not user:
            await message.answer("⚠️ Please run /start to connect your account first.")
            return

        bikes_stmt = (
            select(Bike).where(Bike.user_id == user.id).options(selectinload(Bike.components))
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

        if not bikes:
            await message.answer("No bicycles found in your account.")
            return

        text_lines = [f"🚲 <b>Registered Bicycles ({len(bikes)})</b>\n"]
        buttons = []

        for bike in bikes:
            dist_km = round(bike.total_distance_m / 1000.0, 1)
            elev_m = bike.total_elevation_m
            active_comps = [c for c in bike.components if c.retired_at is None]

            # Bike icon by category
            b_type = (
                bike.bike_type.value if hasattr(bike.bike_type, "value") else str(bike.bike_type)
            )
            type_icon = "🚵" if b_type in ["mtb", "gravel"] else "⚡" if b_type == "ebike" else "🚴"

            text_lines.append(
                f"{type_icon} <b>{bike.name}</b> ({b_type.upper()})\n"
                f"   📏 Distance: <b>{dist_km:,.1f} km</b> | ⛰️ Elevation: <b>{elev_m:,} m</b>\n"
                f"   🔩 Active Parts: <b>{len(active_comps)}</b>\n"
            )

            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🔍 View {bike.name}", callback_data=f"view_bike:{bike.id}"
                    )
                ]
            )

        await message.answer(
            "\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


@router.message(Command("components"))
async def handle_components(message: Message) -> None:
    """Display comprehensive component wear telemetry across all active bikes."""
    chat_id = message.chat.id

    async with get_session_context() as session:
        user_stmt = select(User).where(User.telegram_chat_id == chat_id)
        user = (await session.execute(user_stmt)).scalar_one_or_none()

        if not user:
            await message.answer("⚠️ Please run /start to connect your account first.")
            return

        bikes_stmt = (
            select(Bike)
            .where(Bike.user_id == user.id, Bike.is_active.is_(True))
            .options(selectinload(Bike.components))
        )
        bikes = list((await session.execute(bikes_stmt)).scalars().all())

        if not bikes:
            await message.answer("No active bicycles found.")
            return

        for bike in bikes:
            active_comps = [c for c in bike.components if c.retired_at is None]
            if not active_comps:
                continue

            lines = [f"🚴 <b>{bike.name}</b> — Component Telemetry\n"]
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

            await message.answer("\n".join(lines))
