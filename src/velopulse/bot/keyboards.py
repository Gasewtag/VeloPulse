"""Inline keyboard factories for VeloPulse Telegram bot."""

import uuid
from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velopulse.bot.i18n import t
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentType


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting bot language."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
            ]
        ]
    )


def get_profile_prompt_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Prompt button to begin profile setup."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_profile", lang),
                    callback_data="open:profile",
                )
            ]
        ]
    )


def get_profile_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Main profile setup and navigation menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_new_trip", lang), callback_data="trip:new"),
            ],
            [
                InlineKeyboardButton(text=t("btn_strava", lang), callback_data="open:strava"),
                InlineKeyboardButton(text=t("btn_bikes", lang), callback_data="open:bikes"),
            ],
            [
                InlineKeyboardButton(text=t("btn_clean_chat", lang), callback_data="chat:clean"),
                InlineKeyboardButton(text=t("btn_settings", lang), callback_data="open:settings"),
            ],
        ]
    )


def get_strava_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Back button for Strava info view."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:profile")]
        ]
    )


def get_bikes_list_keyboard(bikes: Sequence[Bike], lang: str = "en") -> InlineKeyboardMarkup:
    """Bike list keyboard respecting 3-bike limit."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Individual bike items
    for b in bikes:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("bike_item_btn", lang, name=b.name),
                    callback_data=f"bike:manage:{b.id}",
                )
            ]
        )

    # Show create button only if fewer than 3 bikes
    if len(bikes) < 3:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("btn_create_bike", lang),
                    callback_data="bike:create",
                )
            ]
        )

    # Back to profile menu
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_bike_type_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Bike type selection buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_road", lang), callback_data="bike_type:road")],
            [InlineKeyboardButton(text=t("btn_gravel", lang), callback_data="bike_type:gravel")],
            [InlineKeyboardButton(text=t("btn_mtb", lang), callback_data="bike_type:mtb")],
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:bikes")],
        ]
    )


def get_mileage_preset_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Preset mileage buttons + cancel option."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0 km", callback_data="preset_km:0"),
                InlineKeyboardButton(text="500 km", callback_data="preset_km:500"),
                InlineKeyboardButton(text="1 000 km", callback_data="preset_km:1000"),
            ],
            [
                InlineKeyboardButton(text="2 500 km", callback_data="preset_km:2500"),
                InlineKeyboardButton(text="5 000 km", callback_data="preset_km:5000"),
            ],
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:bikes")],
        ]
    )


def get_lube_preset_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Preset buttons for chain lubrication history."""
    fresh_label = "0 km (Fresh)" if lang == "en" else "0 км (Свежая)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=fresh_label, callback_data="preset_lube:0"),
                InlineKeyboardButton(text="50 km", callback_data="preset_lube:50"),
                InlineKeyboardButton(text="100 km", callback_data="preset_lube:100"),
            ],
            [
                InlineKeyboardButton(text="150 km", callback_data="preset_lube:150"),
                InlineKeyboardButton(text="200+ km", callback_data="preset_lube:200"),
            ],
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:bikes")],
        ]
    )


def get_brake_type_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Brake type selection (Disc vs Rim)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_disc_brake", lang), callback_data="brake_type:disc"
                ),
                InlineKeyboardButton(text=t("btn_rim_brake", lang), callback_data="brake_type:rim"),
            ],
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:bikes")],
        ]
    )


def get_bike_manage_keyboard(
    bike: Bike,
    components: Sequence[Component],
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Bike management menu with component buttons and delete bike."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Map component types to buttons
    comp_type_map = {c.component_type: c for c in components if c.retired_at is None}

    # Standard components order
    order = [
        (ComponentType.CHAIN, "btn_comp_chain"),
        (ComponentType.CASSETTE, "btn_comp_cassette"),
        (ComponentType.FRONT_TIRE, "btn_comp_front_tire"),
        (ComponentType.REAR_TIRE, "btn_comp_rear_tire"),
        (ComponentType.FRONT_BRAKE_PAD, "btn_comp_front_brake"),
        (ComponentType.REAR_BRAKE_PAD, "btn_comp_rear_brake"),
    ]

    # MTB only includes suspension fork
    is_mtb = (bike.bike_type == BikeType.MTB) or (
        hasattr(bike.bike_type, "value") and bike.bike_type.value == "mtb"
    )
    if is_mtb:
        order.append((ComponentType.SUSPENSION_FORK, "btn_comp_suspension"))

    for c_type, label_key in order:
        comp = comp_type_map.get(c_type)
        if comp:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=t(label_key, lang),
                        callback_data=f"comp:view:{comp.id}",
                    )
                ]
            )

    # Delete bike & Back buttons
    buttons.append(
        [
            InlineKeyboardButton(
                text=t("btn_delete_bike", lang),
                callback_data=f"bike:delete_prompt:{bike.id}",
            )
        ]
    )
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:bikes")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_component_details_keyboard(
    comp_id: uuid.UUID,
    bike_id: uuid.UUID,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Component inspection keyboard with replace and back actions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_replace_comp", lang),
                    callback_data=f"comp:replace_prompt:{comp_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_back", lang),
                    callback_data=f"bike:manage:{bike_id}",
                )
            ],
        ]
    )


def get_replace_confirm_keyboard(
    comp_id: uuid.UUID,
    bike_id: uuid.UUID,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Confirmation buttons for resetting component wear."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_yes_replace", lang),
                    callback_data=f"comp:replace_confirm:{comp_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_cancel", lang),
                    callback_data=f"comp:view:{comp_id}",
                )
            ],
        ]
    )


def get_delete_bike_confirm_keyboard(
    bike_id: uuid.UUID,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Confirmation buttons for bike deletion."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_yes_delete", lang),
                    callback_data=f"bike:delete_confirm:{bike_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_cancel", lang),
                    callback_data=f"bike:manage:{bike_id}",
                )
            ],
        ]
    )


def get_settings_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Settings menu options."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_language", lang),
                    callback_data="settings:language",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_delete_account", lang),
                    callback_data="settings:delete_account_prompt",
                )
            ],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:profile")],
        ]
    )


def get_settings_language_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Keyboard for selecting bot language within Settings."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="settings:set_lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="settings:set_lang:ru"),
            ],
            [
                InlineKeyboardButton(text=t("btn_back", lang), callback_data="open:settings"),
            ],
        ]
    )


def get_delete_account_confirm_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Two-step confirmation for deleting user account."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_yes_delete_account", lang),
                    callback_data="settings:delete_account_confirm",
                ),
                InlineKeyboardButton(
                    text=t("btn_no_keep_account", lang),
                    callback_data="open:settings",
                ),
            ]
        ]
    )


def get_trip_bikes_keyboard(bikes: Sequence[Bike], lang: str = "en") -> InlineKeyboardMarkup:
    """Bike selection keyboard for manual trip entry."""
    buttons: list[list[InlineKeyboardButton]] = []
    for b in bikes:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("bike_item_btn", lang, name=b.name),
                    callback_data=f"trip:bike:{b.id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_elevation_preset_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Preset buttons for elevation gain in meters."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0 m (Flat)", callback_data="preset_elev:0"),
                InlineKeyboardButton(text="100 m", callback_data="preset_elev:100"),
                InlineKeyboardButton(text="300 m", callback_data="preset_elev:300"),
            ],
            [
                InlineKeyboardButton(text="500 m", callback_data="preset_elev:500"),
                InlineKeyboardButton(text="1 000 m", callback_data="preset_elev:1000"),
            ],
            [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="open:profile")],
        ]
    )


def get_service_bikes_keyboard(
    bikes: Sequence[Bike],
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Keyboard for selecting a bike in the /service maintenance wizard."""
    buttons: list[list[InlineKeyboardButton]] = []
    for b in bikes:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("bike_item_btn", lang, name=b.name),
                    callback_data=f"service:bike:{b.id}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="service:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_service_components_keyboard(
    components: Sequence[Component],
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Keyboard for selecting a component in the /service wizard."""
    buttons: list[list[InlineKeyboardButton]] = []
    for comp in components:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{comp.brand_model} ({comp.component_type.value})",
                    callback_data=f"service:comp:{comp.id}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="service:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_service_types_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Keyboard for selecting the maintenance action type."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_service_lube", lang),
                    callback_data="service:type:clean_and_lube",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_service_inspect", lang),
                    callback_data="service:type:inspect_tune",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_service_repair", lang),
                    callback_data="service:type:repair",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_service_replace", lang),
                    callback_data="service:type:replace",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_service_season", lang),
                    callback_data="service:type:season_prep",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_cancel", lang),
                    callback_data="service:cancel",
                )
            ],
        ]
    )


def get_service_skip_notes_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Keyboard allowing the user to skip entering technician notes."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_skip_notes", lang),
                    callback_data="service:skip_notes",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_cancel", lang),
                    callback_data="service:cancel",
                )
            ],
        ]
    )


def get_service_skip_cost_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Keyboard allowing the user to skip cost (free / 0.00)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_skip_cost", lang),
                    callback_data="service:skip_cost",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_cancel", lang),
                    callback_data="service:cancel",
                )
            ],
        ]
    )
