## Camera that follows the player with light smoothing.
extends Camera2D

@export var smoothing_speed: float = 8.0

func _ready() -> void:
	make_current()

func _process(delta: float) -> void:
	if get_parent():
		global_position = global_position.lerp(get_parent().global_position, smoothing_speed * delta)
