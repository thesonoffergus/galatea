## Builds and updates the visual world from GameState.
## Manages the active ZoneRenderer and scene transitions.
extends Node2D

const ZoneRendererScene = preload("res://scenes/world.tscn")

var _current_renderer: Node2D = null
var _current_zone_id: String  = ""

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	GameState.state_loaded.connect(_on_state_loaded)
	GameState.zone_changed.connect(_on_zone_changed)
	GameBridge.connected_to_server.connect(_on_bridge_connected)
	GameBridge.disconnected_from_server.connect(_on_bridge_disconnected)

func _on_bridge_connected() -> void:
	pass  # full_state will arrive shortly; handled via GameState.state_loaded

func _on_bridge_disconnected() -> void:
	if _current_renderer:
		_current_renderer.queue_free()
		_current_renderer = null

func _on_state_loaded() -> void:
	var zone_id: String = GameState.player.get("current_zone_id", "")
	_load_zone(zone_id)

func _on_zone_changed(zone_id: String) -> void:
	_load_zone(zone_id)

# ── Zone loading ──────────────────────────────────────────────────────────────

func _load_zone(zone_id: String) -> void:
	if zone_id == _current_zone_id and _current_renderer != null:
		return
	if _current_renderer:
		_current_renderer.queue_free()
		_current_renderer = null

	var zone_data: Dictionary = GameState.zones.get(zone_id, {})
	if zone_data.is_empty():
		push_warning("WorldManager: unknown zone %s" % zone_id)
		return

	_current_zone_id = zone_id
	_current_renderer = ZoneRendererScene.instantiate()
	add_child(_current_renderer)
	_current_renderer.setup(zone_data)

# ── NPC movement notifications ────────────────────────────────────────────────

func on_npc_zone_change(npc_id: String, from_zone: String, to_zone: String) -> void:
	if _current_renderer == null:
		return
	if from_zone == _current_zone_id:
		_current_renderer.npc_left(npc_id)
	if to_zone == _current_zone_id:
		_current_renderer.npc_arrived(npc_id)

# ── Interaction forwarding ────────────────────────────────────────────────────

func _on_npc_interaction_triggered(npc_id: String) -> void:
	GameBridge.send_interact(npc_id)
