"""Aiogram FSM States for VeloPulse Telegram bot conversation flows."""

from aiogram.fsm.state import State, StatesGroup


class LanguageStates(StatesGroup):
    """States for language selection."""

    selecting_language = State()


class ProfileStates(StatesGroup):
    """States for user profile initialization."""

    awaiting_profile_setup = State()


class BikeCreationStates(StatesGroup):
    """Multi-step bike creation wizard states."""

    selecting_bike_type = State()
    entering_model = State()
    entering_cassette_mileage = State()
    entering_chain_mileage = State()
    entering_chain_lube_mileage = State()
    entering_front_tire_mileage = State()
    entering_rear_tire_mileage = State()
    selecting_front_brake_type = State()
    entering_front_brake_mileage = State()
    selecting_rear_brake_type = State()
    entering_rear_brake_mileage = State()
    entering_suspension_mileage = State()


class TripStates(StatesGroup):
    """States for manual trip entry."""

    selecting_bike = State()
    entering_distance = State()
    entering_elevation = State()


class ComponentStates(StatesGroup):
    """States for component inspection and replacement."""

    confirming_replace = State()


class BikeStates(StatesGroup):
    """States for bike management."""

    confirming_delete = State()


class SettingsStates(StatesGroup):
    """States for settings and account management."""

    confirming_delete_account = State()


class ServiceStates(StatesGroup):
    """States for maintenance service logging wizard."""

    selecting_bike = State()
    selecting_component = State()
    selecting_service_type = State()
    entering_notes = State()
    entering_cost = State()

