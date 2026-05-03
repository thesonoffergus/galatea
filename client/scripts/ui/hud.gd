## HUD — current zone name (top-left) and time (top-right).
extends CanvasLayer

@onready var _zone_label: Label = $TopLeft/ZoneName
@onready var _time_label: Label = $TopRight/TimeLabel

func _ready() -> void:
	GameState.state_loaded.connect(_refresh)
	GameState.zone_changed.connect(func(_z): _refresh())
	GameState.time_ticked.connect(_refresh_time)

func _refresh() -> void:
	var zone: Dictionary = GameState.get_current_zone()
	_zone_label.text = zone.get("name", "Unknown")
	_refresh_time()

func _refresh_time() -> void:
	var t: Dictionary = GameState.time
	var hour: float   = t.get("game_hour", 6.0)
	var day: int      = t.get("day", 1)
	var period: String = t.get("period", "morning")
	_time_label.text = "Day %d  %02d:00  (%s)" % [day, int(hour), period]
