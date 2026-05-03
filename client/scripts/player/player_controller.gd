## Handles player movement, interaction input, and action menu trigger.
extends CharacterBody2D

const SPEED := 200.0

@onready var _sprite: ColorRect        = $Sprite
@onready var _camera: Camera2D         = $Camera2D
@onready var _interact_area: Area2D    = $InteractionArea

var _dialogue_open: bool = false
var _action_menu_open: bool = false

func _ready() -> void:
	add_to_group("player")
	GameBridge.dialogue_started.connect(func(_d): _dialogue_open = true)
	GameBridge.dialogue_ended.connect(func(_d): _dialogue_open = false)

func _physics_process(delta: float) -> void:
	if _dialogue_open or _action_menu_open:
		velocity = Vector2.ZERO
		return

	var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity = dir * SPEED
	move_and_slide()

func _unhandled_input(event: InputEvent) -> void:
	if _dialogue_open:
		return

	if event.is_action_pressed("interact"):
		_try_interact()

	if event.is_action_pressed("open_actions"):
		GameBridge.send_get_affordances()

func _try_interact() -> void:
	# Find the closest NPC in the interaction area
	var overlapping := _interact_area.get_overlapping_bodies()
	var closest: Node = null
	var closest_dist := INF
	for body in overlapping:
		if body.is_in_group("npc"):
			var d := position.distance_to(body.position)
			if d < closest_dist:
				closest_dist = d
				closest = body
	if closest and closest.has_method("get_npc_id"):
		GameBridge.send_interact(closest.get_npc_id())
