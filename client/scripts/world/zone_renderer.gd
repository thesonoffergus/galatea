## Renders a single zone as a colored background with NPC sprites and exit arrows.
## Instantiated and managed by WorldManager.
extends Node2D

const TERRAIN_COLORS: Dictionary = {
	"settlement":        Color(0.76, 0.70, 0.58),
	"building_interior": Color(0.55, 0.47, 0.38),
	"ground":            Color(0.55, 0.65, 0.40),
	"forest":            Color(0.25, 0.48, 0.28),
	"river":             Color(0.30, 0.55, 0.80),
	"hill":              Color(0.60, 0.55, 0.42),
	"marsh":             Color(0.45, 0.52, 0.38),
	"road":              Color(0.68, 0.62, 0.52),
	"wilderness":        Color(0.38, 0.52, 0.32),
	"underground":       Color(0.28, 0.25, 0.22),
}

const NPC_COLORS: Array = [
	Color(0.85, 0.35, 0.35),  # red
	Color(0.35, 0.65, 0.85),  # blue
	Color(0.85, 0.75, 0.35),  # gold
	Color(0.55, 0.85, 0.55),  # green
	Color(0.85, 0.55, 0.85),  # purple
]

const ZONE_SIZE := Vector2(1280.0, 720.0)
const NPC_SIZE  := Vector2(32.0, 48.0)
const EXIT_SIZE := Vector2(80.0, 40.0)

@onready var _background: ColorRect = $Background
@onready var _zone_label: Label     = $ZoneLabel
@onready var _exits_container: HBoxContainer = $ExitsContainer
@onready var _npcs_container: Node2D = $NPCsContainer

var _zone_data: Dictionary = {}
var _npc_nodes: Dictionary = {}     # npc_id → Node2D

# ── Setup ─────────────────────────────────────────────────────────────────────

func setup(zone_data: Dictionary) -> void:
	_zone_data = zone_data
	_background.color = TERRAIN_COLORS.get(zone_data.get("terrain_type", ""), Color(0.5, 0.5, 0.5))
	_zone_label.text = zone_data.get("name", "Unknown")
	_build_exits()
	_build_npcs()

func _build_exits() -> void:
	for child in _exits_container.get_children():
		child.queue_free()

	var connections: Array = _zone_data.get("connections", [])
	for conn_id in connections:
		var zone = GameState.zones.get(conn_id, {})
		var btn := Button.new()
		btn.text = "→ %s" % zone.get("name", conn_id)
		btn.custom_minimum_size = EXIT_SIZE
		btn.pressed.connect(_on_exit_pressed.bind(conn_id))
		_exits_container.add_child(btn)

func _build_npcs() -> void:
	for child in _npcs_container.get_children():
		child.queue_free()
	_npc_nodes.clear()

	var npc_list: Array = GameState.get_npcs_in_zone(_zone_data.get("id", ""))
	var i := 0
	for npc in npc_list:
		if npc.get("is_player", false):
			continue
		var node := _make_npc_sprite(npc, i)
		_npcs_container.add_child(node)
		_npc_nodes[npc["id"]] = node
		i += 1

func _make_npc_sprite(npc: Dictionary, idx: int) -> Node2D:
	var root := Node2D.new()
	root.name = "NPC_%s" % npc.get("id", str(idx))

	# Colored rectangle as body
	var rect := ColorRect.new()
	rect.size = NPC_SIZE
	rect.position = -NPC_SIZE / 2.0
	rect.color = NPC_COLORS[idx % NPC_COLORS.size()]
	root.add_child(rect)

	# Name label
	var lbl := Label.new()
	lbl.text = npc.get("name", "NPC")
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.position = Vector2(-50, -NPC_SIZE.y / 2.0 - 20)
	lbl.custom_minimum_size = Vector2(100, 20)
	root.add_child(lbl)

	# Interaction area
	var area := Area2D.new()
	area.name = "InteractionArea"
	var shape := CollisionShape2D.new()
	var capsule := CapsuleShape2D.new()
	capsule.radius = 36.0
	capsule.height = 64.0
	shape.shape = capsule
	area.add_child(shape)
	root.add_child(area)
	area.body_entered.connect(_on_player_near_npc.bind(npc.get("id", "")))

	# Spread NPCs across the zone
	var cols := 5
	var spacing := Vector2(160, 200)
	var origin := Vector2(200, 250)
	root.position = origin + Vector2((idx % cols) * spacing.x, (idx / cols) * spacing.y)

	return root

# ── Signals ───────────────────────────────────────────────────────────────────

func _on_exit_pressed(zone_id: String) -> void:
	GameBridge.send_player_move(zone_id)

func _on_player_near_npc(body: Node, npc_id: String) -> void:
	if body.is_in_group("player"):
		# Signal up to WorldManager via a custom event on the tree
		get_tree().get_root().propagate_call("_on_npc_interaction_triggered", [npc_id], true)

# ── Live updates ──────────────────────────────────────────────────────────────

func npc_arrived(npc_id: String) -> void:
	if npc_id not in _npc_nodes:
		var npc: Dictionary = GameState.get_npc(npc_id)
		if not npc.is_empty():
			var node := _make_npc_sprite(npc, _npc_nodes.size())
			_npcs_container.add_child(node)
			_npc_nodes[npc_id] = node

func npc_left(npc_id: String) -> void:
	if npc_id in _npc_nodes:
		_npc_nodes[npc_id].queue_free()
		_npc_nodes.erase(npc_id)
