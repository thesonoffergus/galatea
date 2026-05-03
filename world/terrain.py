from enum import StrEnum


class TerrainType(StrEnum):
    # Natural
    GROUND = "ground"
    FOREST = "forest"
    RIVER = "river"
    HILL = "hill"
    MARSH = "marsh"
    ROAD = "road"

    # Settlement
    SETTLEMENT = "settlement"
    BUILDING_INTERIOR = "building_interior"
    UNDERGROUND = "underground"

    # Surrounding / meta
    WILDERNESS = "wilderness"
