"""Database and session helpers for Telegram bot handlers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models.user import User


async def get_user_by_chat_id(chat_id: int, session: AsyncSession) -> User | None:
    """Retrieve User by telegram_chat_id."""
    stmt = select(User).where(User.telegram_chat_id == chat_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_create_user(
    chat_id: int,
    first_name: str,
    last_name: str | None,
    session: AsyncSession,
) -> User:
    """Fetch existing user by chat_id or register new user."""
    user = await get_user_by_chat_id(chat_id, session)
    if not user:
        user = User(
            telegram_chat_id=chat_id,
            first_name=first_name or "Cyclist",
            last_name=last_name,
            settings={
                "language": "en",
                "notifications_enabled": True,
                "weather_enrichment": True,
                "profile_setup_completed": False,
            },
        )
        session.add(user)
        await session.commit()
    return user


def get_user_language(user: User | None, default: str = "en") -> str:
    """Extract user language setting with fallback."""
    if not user or not user.settings:
        return default
    lang = user.settings.get("language", default)
    return str(lang) if lang in ("en", "ru") else default


def is_profile_completed(user: User | None) -> bool:
    """Check if the user has completed initial profile setup."""
    if not user or not user.settings:
        return False
    return bool(user.settings.get("profile_setup_completed", False))
