## Client-side state cache. Populated from full_state on connect,
## updated incrementally from push messages. Other scripts read from here only.
extends Node

# ── State ─────────────────────────────────────────────────────────────────────
var zones: Dictionary = {}      # zone_id → zone dict
var npcs: Dictionary = {}       # npc_id → npc dict
var player: Dictionary = {}     # player state
var time: Dictionary = {}       # tick, game_hour, day, period

signal state_loaded()
signal zone_changed(zone_id: String)
signal npc_updated(npc_id: String)
signal time_ticked()

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	GameBridge.full_state_received.connect(_on_full_state)
	GameBridge.move_result_received.connect(_on_move_result)
	GameBridge.npc_moved.connect(_on_npc_moved)
	GameBridge.time_updated.connect(_on_time_update)
	GameBridge.tick_result_received.connect(_on_tick_result)

# ── Handlers ──────────────────────────────────────────────────────────────────

func _on_full_state(data: Dictionary) -> void:
	zones.clear()
	npcs.clear()
	for zone in data.get("world", {}).get("zones", []):
		zones[zone["id"]] = zone
	for npc in data.get("npcs", []):
		npcs[npc["id"]] = npc
	player = data.get("player", {})
	time = data.get("time", {})
	state_loaded.emit()

func _on_move_result(data: Dictionary) -> void:
	if data.get("success") and data.has("zone_data"):
		var zd: Dictionary = data["zone_data"]
		zones[zd["id"]] = zd
		player["current_zone_id"] = zd["id"]
		zone_changed.emit(zd["id"])

func _on_npc_moved(data: Dictionary) -> void:
	var npc_id: String = data.get("npc_id", "")
	var to_zone: String = data.get("to_zone", "")
	if npc_id in npcs:
		npcs[npc_id]["current_zone_id"] = to_zone
		npc_updated.emit(npc_id)
		# Update zone npc lists
		var from_zone: String = data.get("from_zone", "")
		if from_zone in zones and zones[from_zone].has("npcs"):
			zones[from_zone]["npcs"].erase(npc_id)
		if to_zone in zones and zones[to_zone].has("npcs"):
			if not (npc_id in zones[to_zone]["npcs"]):
				zones[to_zone]["npcs"].append(npc_id)

func _on_time_update(data: Dictionary) -> void:
	time = data
	time_ticked.emit()

func _on_tick_result(data: Dictionary) -> void:
	if data.has("time"):
		time = data["time"]
		time_ticked.emit()

# ── Queries ───────────────────────────────────────────────────────────────────

func get_current_zone() -> Dictionary:
	var zone_id: String = player.get("current_zone_id", "")
	return zones.get(zone_id, {})

func get_npcs_in_zone(zone_id: String) -> Array:
	var zone: Dictionary = zones.get(zone_id, {})
	var result: Array = []
	for npc_id in zone.get("npcs", []):
		if npc_id in npcs:
			result.append(npcs[npc_id])
	return result

func get_zone_connections(zone_id: String) -> Array:
	var zone: Dictionary = zones.get(zone_id, {})
	return zone.get("connections", [])

func get_npc(npc_id: String) -> Dictionary:
	return npcs.get(npc_id, {})

func is_loaded() -> bool:
	return not zones.is_empty()
