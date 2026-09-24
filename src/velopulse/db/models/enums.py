"""Database domain enumerations."""

from enum import StrEnum


class BikeType(StrEnum):
    """Categorization of bicycle frame and usage types."""

    ROAD = "road"
    GRAVEL = "gravel"
    MTB = "mtb"
    EBIKE = "ebike"
    COMMUTER = "commuter"
    TT = "tt"


class ComponentType(StrEnum):
    """Bicycle component mechanical sub-assemblies."""

    CHAIN = "chain"
    CASSETTE = "cassette"
    CHAINRING = "chainring"
    FRONT_BRAKE_PAD = "front_brake_pad"
    REAR_BRAKE_PAD = "rear_brake_pad"
    FRONT_ROTOR = "front_rotor"
    REAR_ROTOR = "rear_rotor"
    FRONT_TIRE = "front_tire"
    REAR_TIRE = "rear_tire"
    BOTTOM_BRACKET = "bottom_bracket"
    CABLES = "cables"
    SUSPENSION_FORK = "suspension_fork"
    REAR_SHOCK = "rear_shock"


class ComponentStatus(StrEnum):
    """Wear-lifecycle state machine states."""

    NEW = "new"
    OPTIMAL = "optimal"
    ATTENTION_NEEDED = "attention_needed"
    REPLACE_RECOMMENDED = "replace_recommended"
    RETIRED = "retired"


class MaintenanceType(StrEnum):
    """Class of maintenance action performed on a component."""

    CLEAN_AND_LUBE = "clean_and_lube"
    INSPECT_TUNE = "inspect_tune"
    REPAIR = "repair"
    REPLACE = "replace"
    SEASON_PREP = "season_prep"
