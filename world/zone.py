from __future__ import annotations
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from world.terrain import TerrainType


class PropertyValue(BaseModel):
    """A typed key-value property attached to a zone, feature, or item."""
    type: str  # "str" | "int" | "float" | "bool" | "list"
    value: Any

    @classmethod
    def of(cls, value: Any) -> "PropertyValue":
        type_map = {str: "str", int: "int", float: "float", bool: "bool", list: "list"}
        return cls(type=type_map.get(type(value), "str"), value=value)


class Feature(BaseModel):
    """
    A fixed, non-movable element in a zone — forge, well, millstone, etc.
    Features contribute their tags to the zone's effective tag set.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    tags: set[str] = Field(default_factory=set)
    properties: dict[str, PropertyValue] = Field(default_factory=dict)
    quality: float = 1.0  # 0.0–1.0; affects tool quality calculations


class Item(BaseModel):
    """
    A movable object that can exist in a zone or an NPC's inventory.
    Items contribute their tags to whatever zone contains them.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    item_type: str  # references an item-type definition in the action registry
    tags: set[str] = Field(default_factory=set)
    properties: dict[str, PropertyValue] = Field(default_factory=dict)
    quality: float = 1.0
    quantity: int = 1
    owner_id: Optional[str] = None  # NPC that owns this item (None = unclaimed)


class Zone(BaseModel):
    """
    A discrete, non-overlapping location. Zones form the nodes of the world graph.
    Containment (room ⊂ building ⊂ village) and adjacency (doorways, paths) are
    edges in that graph, not fields here.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""

    terrain_type: TerrainType = TerrainType.GROUND

    # Intrinsic tags and properties (not derived from contents)
    tags: set[str] = Field(default_factory=set)
    properties: dict[str, PropertyValue] = Field(default_factory=dict)

    # Fixed features (forge, well, tannery vat, etc.)
    features: list[Feature] = Field(default_factory=list)

    # Dynamic contents — stored as IDs, resolved through the world graph
    item_ids: list[str] = Field(default_factory=list)
    npc_ids: list[str] = Field(default_factory=list)

    # Ownership: entity IDs (NPC or authority) that own this zone
    owner_ids: list[str] = Field(default_factory=list)

    # Optional modifiable appearance description
    appearance: Optional[str] = None

    def effective_tags(
        self,
        item_registry: dict[str, Item] | None = None,
        npc_tag_map: dict[str, set[str]] | None = None,
    ) -> set[str]:
        """
        Compute the effective tag set for this zone:
        own tags + all feature tags + tags of contained items and NPCs.

        Callers pass registries so this stays a pure function of current state.
        Child zone tags are NOT included here — the affordance query traverses
        the graph explicitly rather than relying on recursive propagation.
        """
        result = set(self.tags)
        for feature in self.features:
            result |= feature.tags
        if item_registry:
            for iid in self.item_ids:
                if item := item_registry.get(iid):
                    result |= item.tags
        if npc_tag_map:
            for nid in self.npc_ids:
                if npc_tags := npc_tag_map.get(nid):
                    result |= npc_tags
        return result

    def feature_by_name(self, name: str) -> Feature | None:
        return next((f for f in self.features if f.name == name), None)
