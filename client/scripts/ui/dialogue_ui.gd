## Dialogue box UI — JRPG-style panel at bottom of screen.
## Shows NPC name, response text (typewriter), menu option buttons, freeform input.
extends CanvasLayer

@onready var _panel: PanelContainer           = $DialoguePanel
@onready var _npc_name_label: Label           = $DialoguePanel/VBox/NPCName
@onready var _response_label: RichTextLabel   = $DialoguePanel/VBox/ResponseText
@onready var _menu_container: VBoxContainer   = $DialoguePanel/VBox/MenuOptions
@onready var _input_line: LineEdit            = $DialoguePanel/VBox/InputRow/FreeformInput
@onready var _send_button: Button             = $DialoguePanel/VBox/InputRow/SendButton
@onready var _close_button: Button            = $DialoguePanel/CloseButton
@onready var _typewriter_timer: Timer         = $TypewriterTimer

const TYPEWRITER_SPEED := 0.03   # seconds per character

var _active_npc_id: String = ""
var _full_text: String = ""
var _visible_chars: int = 0

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_panel.hide()
	_send_button.pressed.connect(_on_send_pressed)
	_close_button.pressed.connect(_on_close_pressed)
	_typewriter_timer.wait_time = TYPEWRITER_SPEED
	_typewriter_timer.timeout.connect(_on_typewriter_tick)
	_input_line.text_submitted.connect(func(t): _send_input(t))

	GameBridge.dialogue_started.connect(_on_dialogue_started)
	GameBridge.dialogue_response_received.connect(_on_dialogue_response)
	GameBridge.dialogue_ended.connect(func(_d): hide_dialogue())
	GameBridge.error_received.connect(func(_d): hide_dialogue())

func _unhandled_input(event: InputEvent) -> void:
	if not _panel.visible:
		return
	if event.is_action_pressed("cancel"):
		_on_close_pressed()
	elif event.is_action_pressed("menu_select_1"):
		_click_menu_option(0)
	elif event.is_action_pressed("menu_select_2"):
		_click_menu_option(1)
	elif event.is_action_pressed("menu_select_3"):
		_click_menu_option(2)
	elif event.is_action_pressed("menu_select_4"):
		_click_menu_option(3)

# ── Show / hide ───────────────────────────────────────────────────────────────

func _on_dialogue_started(data: Dictionary) -> void:
	_active_npc_id = data.get("npc_id", "")
	_npc_name_label.text = data.get("npc_name", "NPC")
	_show_response(data.get("greeting", ""), data.get("menu_options", []))
	_panel.show()
	_input_line.grab_focus()

func _on_dialogue_response(data: Dictionary) -> void:
	_show_response(data.get("npc_response", ""), data.get("menu_options", []))

func hide_dialogue() -> void:
	_panel.hide()
	_active_npc_id = ""
	_typewriter_timer.stop()

# ── Response rendering ────────────────────────────────────────────────────────

func _show_response(text: String, menu_options: Array) -> void:
	_full_text = text
	_visible_chars = 0
	_response_label.text = ""
	_typewriter_timer.start()
	_build_menu(menu_options)

func _on_typewriter_tick() -> void:
	if _visible_chars >= _full_text.length():
		_typewriter_timer.stop()
		return
	_visible_chars += 1
	_response_label.text = _full_text.left(_visible_chars)

func _build_menu(options: Array) -> void:
	for child in _menu_container.get_children():
		child.queue_free()
	for i in range(options.size()):
		var opt: String = options[i]
		var btn := Button.new()
		btn.text = "[%d] %s" % [i + 1, opt]
		btn.pressed.connect(_send_input.bind(opt))
		_menu_container.add_child(btn)

func _click_menu_option(idx: int) -> void:
	var buttons := _menu_container.get_children()
	if idx < buttons.size():
		buttons[idx].emit_signal("pressed")

# ── Input ─────────────────────────────────────────────────────────────────────

func _send_input(text: String) -> void:
	if _active_npc_id.is_empty() or text.strip_edges().is_empty():
		return
	GameBridge.send_dialogue_input(_active_npc_id, text.strip_edges())
	_input_line.clear()

func _on_send_pressed() -> void:
	_send_input(_input_line.text)

func _on_close_pressed() -> void:
	if not _active_npc_id.is_empty():
		GameBridge.send_dialogue_end(_active_npc_id)
	hide_dialogue()
