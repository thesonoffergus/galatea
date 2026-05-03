## Affordance / action selection popup.
## Opens on "open_actions", populates from server, player selects to execute.
extends CanvasLayer

@onready var _panel: PanelContainer  = $ActionPanel
@onready var _list: VBoxContainer    = $ActionPanel/VBox/ActionList
@onready var _close_btn: Button      = $ActionPanel/VBox/CloseButton

func _ready() -> void:
	_panel.hide()
	_close_btn.pressed.connect(func(): _panel.hide())
	GameBridge.affordances_received.connect(_on_affordances)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("open_actions") and not _panel.visible:
		GameBridge.send_get_affordances()
	elif event.is_action_pressed("cancel") and _panel.visible:
		_panel.hide()

func _on_affordances(data: Dictionary) -> void:
	for child in _list.get_children():
		child.queue_free()

	var actions: Array = data.get("actions", [])
	if actions.is_empty():
		var lbl := Label.new()
		lbl.text = "Nothing you can do here."
		_list.add_child(lbl)
	else:
		for action in actions:
			var btn := Button.new()
			btn.text = "%s" % action.get("name", action.get("id", "?"))
			btn.tooltip_text = action.get("description", "")
			btn.pressed.connect(_on_action_selected.bind(action.get("id", "")))
			_list.add_child(btn)

	_panel.show()

func _on_action_selected(action_id: String) -> void:
	_panel.hide()
	GameBridge.send_execute_action(action_id)
