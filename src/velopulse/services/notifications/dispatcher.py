"""Decoupled notification dispatcher and alert message generator."""

import logging
from datetime import timedelta
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from redis.asyncio import Redis

from velopulse.bot.bot import create_bot
from velopulse.bot.utils.formatters import (
    get_component_icon,
    get_status_badge,
    render_progress_bar,
)
from velopulse.core.config import Settings, get_settings
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import ComponentStatus
from velopulse.db.models.user import User

logger = logging.getLogger("velopulse.services.notifications")


class NotificationDispatcher:
    """Service formatting and delivering maintenance notifications to cyclists."""

    def __init__(
        self,
        bot: Bot | None = None,
        redis_client: Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.bot = bot or create_bot(settings=self.settings)
        self._redis = redis_client
        self._owns_redis = redis_client is None

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(self.settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def should_suppress_alert(self, component_id: Any, status: ComponentStatus) -> bool:
        """Anti-fatigue filter: suppress duplicate ATTENTION_NEEDED alerts within 7 days."""
        # Always allow critical replacement alerts
        if status in (ComponentStatus.REPLACE_RECOMMENDED, ComponentStatus.RETIRED):
            return False

        try:
            r = await self._get_redis()
            cooldown_key = f"alert_cooldown:{component_id}"
            is_active = await r.exists(cooldown_key)
            if is_active:
                logger.info(
                    "Alert for component %s suppressed by 7-day anti-fatigue policy.", component_id
                )
                return True
            # Set 7-day cooldown
            await r.set(cooldown_key, "1", ex=int(timedelta(days=7).total_seconds()))
        except Exception as exc:
            logger.warning("Error checking notification cooldown in Redis: %s", exc)

        return False

    async def dispatch_wear_alert(
        self,
        user: User,
        bike: Bike,
        activity: Activity,
        components_to_alert: list[Component],
    ) -> bool:
        """Send formatted maintenance alert to athlete's Telegram account."""
        if not user.telegram_chat_id:
            logger.info(
                "User %s has no telegram_chat_id configured. Skipping notification.", user.id
            )
            return False

        filtered_comps: list[Component] = []
        for comp in components_to_alert:
            if not await self.should_suppress_alert(comp.id, comp.status):
                filtered_comps.append(comp)

        if not filtered_comps:
            logger.info(
                "All components for activity %s suppressed by anti-fatigue policy.", activity.id
            )
            return False

        # Build message
        dist_km = round(float(activity.distance_m) / 1000.0, 1) if activity.distance_m else 0.0
        lines = [
            "⚠️ <b>VeloPulse Maintenance Alert</b>",
            f"🚴 <b>{bike.name}</b> (Ride: <i>{activity.name}</i> — {dist_km} km)\n",
            "The following component(s) have reached critical service milestones:\n",
        ]

        buttons = []
        for comp in filtered_comps:
            icon = get_component_icon(comp.component_type)
            curr = float(comp.current_wear_points)
            max_wp = float(comp.lifespan_wear_points)
            pct = (curr / max_wp) * 100.0 if max_wp > 0 else 100.0
            bar = render_progress_bar(pct, length=10)
            badge = get_status_badge(comp.status)

            lines.append(
                f"{icon} <b>{comp.brand_model}</b>\n"
                f"   {bar} ({curr:,.0f} / {max_wp:,.0f} WP)\n"
                f"   Status: {badge}"
            )

            # Row of quick actions for this component
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Clean & Lube {comp.brand_model[:12]}",
                        callback_data=f"clean_lube:{comp.id}",
                    ),
                    InlineKeyboardButton(
                        text="🔄 Replace",
                        callback_data=f"replace:{comp.id}",
                    ),
                    InlineKeyboardButton(
                        text="⏸️ Snooze",
                        callback_data=f"snooze:{comp.id}",
                    ),
                ]
            )

        text = "\n".join(lines)
        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await self.bot.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            logger.info(
                "Sent Telegram wear alert for %d component(s) to chat %s",
                len(filtered_comps),
                user.telegram_chat_id,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to send Telegram message to chat %s: %s", user.telegram_chat_id, exc
            )
            return False

    async def close(self) -> None:
        """Close connections."""
        if self._owns_redis and self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        await self.bot.session.close()
