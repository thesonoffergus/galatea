## Handles NPC sprite updates from server push messages (npc_moved).
## Attached to the WorldManager; delegates visual updates to ZoneRenderer.
extends Node

func _ready() -> void:
	GameBridge.npc_moved.connect(_on_npc_moved)

func _on_npc_moved(data: Dictionary) -> void:
	var npc_id: String  = data.get("npc_id", "")
	var from_zone: String = data.get("from_zone", "")
	var to_zone: String   = data.get("to_zone", "")

	# Only update visible zone renderers
	var world_manager := get_parent()
	if world_manager.has_method("on_npc_zone_change"):
		world_manager.on_npc_zone_change(npc_id, from_zone, to_zone)
