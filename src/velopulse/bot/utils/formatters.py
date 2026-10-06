"""Visual text formatting and Unicode progress bars for Telegram messages."""

from velopulse.db.models.enums import ComponentStatus, ComponentType


def render_progress_bar(percentage: float, length: int = 10, with_brackets: bool = True) -> str:
    """Render a visual Unicode progress bar for component wear.

    Example:
        render_progress_bar(80.0, length=10, with_brackets=True) -> "[████████░░] 80.0%"
        render_progress_bar(80.0, length=10, with_brackets=False) -> "████████░░ 80%"
    """
    pct = max(0.0, min(100.0, percentage))
    filled_len = round((pct / 100.0) * length)
    filled_len = min(length, max(0, filled_len))
    empty_len = length - filled_len

    bar = "█" * filled_len + "░" * empty_len
    if with_brackets:
        return f"[{bar}] {percentage:.1f}%"
    return f"{bar} {round(pct)}%"


def get_status_badge(status: ComponentStatus) -> str:
    """Return an intuitive emoji and text badge for a component status."""
    if status == ComponentStatus.NEW:
        return "✨ <b>NEW</b>"
    elif status == ComponentStatus.OPTIMAL:
        return "🟢 <b>OPTIMAL</b>"
    elif status == ComponentStatus.ATTENTION_NEEDED:
        return "🟡 <b>ATTENTION NEEDED</b>"
    elif status == ComponentStatus.REPLACE_RECOMMENDED:
        return "🟠 <b>REPLACE RECOMMENDED</b>"
    elif status == ComponentStatus.RETIRED:
        return "🔴 <b>CRITICAL / OVERDUE</b>"
    return str(status)


def get_component_icon(comp_type: ComponentType) -> str:
    """Return a descriptive icon for a component type."""
    icons: dict[ComponentType, str] = {
        ComponentType.CHAIN: "⛓️",
        ComponentType.CASSETTE: "⚙️",
        ComponentType.CHAINRING: "☸️",
        ComponentType.FRONT_BRAKE_PAD: "🛑",
        ComponentType.REAR_BRAKE_PAD: "🛑",
        ComponentType.FRONT_ROTOR: "💿",
        ComponentType.REAR_ROTOR: "💿",
        ComponentType.FRONT_TIRE: "🛞",
        ComponentType.REAR_TIRE: "🛞",
        ComponentType.BOTTOM_BRACKET: "🔩",
        ComponentType.CABLES: "🔌",
        ComponentType.SUSPENSION_FORK: "🚵",
        ComponentType.REAR_SHOCK: "🚵",
    }
    return icons.get(comp_type, "🔧")
