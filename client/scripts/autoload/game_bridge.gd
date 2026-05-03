## WebSocket client singleton. Manages the connection to the Python simulation server.
## All other scripts send messages through this node and subscribe to its signals.
extends Node

const MT = preload("res://scripts/util/message_types.gd")

# ── Configuration ─────────────────────────────────────────────────────────────
@export var server_url: String = "ws://localhost:8765"
@export var reconnect_delay: float = 3.0

# ── Signals ───────────────────────────────────────────────────────────────────
signal connected_to_server()
signal disconnected_from_server()
signal connection_failed()

signal full_state_received(data: Dictionary)
signal move_result_received(data: Dictionary)
signal dialogue_started(data: Dictionary)
signal dialogue_response_received(data: Dictionary)
signal dialogue_ended(data: Dictionary)
signal affordances_received(data: Dictionary)
signal action_result_received(data: Dictionary)
signal tick_result_received(data: Dictionary)
signal npc_moved(data: Dictionary)
signal world_event(data: Dictionary)
signal time_updated(data: Dictionary)
signal error_received(data: Dictionary)

# ── State ─────────────────────────────────────────────────────────────────────
var _socket: WebSocketPeer = WebSocketPeer.new()
var _connected: bool = false
var _reconnecting: bool = false

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_connect_to_server()

func _process(_delta: float) -> void:
	_socket.poll()
	var state := _socket.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN:
		if not _connected:
			_connected = true
			_reconnecting = false
			connected_to_server.emit()
			send_connect()
		while _socket.get_available_packet_count() > 0:
			_on_message(_socket.get_packet().get_string_from_utf8())

	elif state == WebSocketPeer.STATE_CLOSING:
		pass  # waiting for graceful close

	elif state in [WebSocketPeer.STATE_CLOSED, WebSocketPeer.STATE_CONNECTING]:
		if _connected:
			_connected = false
			disconnected_from_server.emit()
			if not _reconnecting:
				_schedule_reconnect()

# ── Connection management ─────────────────────────────────────────────────────

func _connect_to_server() -> void:
	var err := _socket.connect_to_url(server_url)
	if err != OK:
		push_error("GameBridge: failed to initiate connection to %s (error %d)" % [server_url, err])
		connection_failed.emit()

func _schedule_reconnect() -> void:
	_reconnecting = true
	await get_tree().create_timer(reconnect_delay).timeout
	_socket = WebSocketPeer.new()
	_connect_to_server()

func is_connected_to_server() -> bool:
	return _connected

# ── Message dispatch ──────────────────────────────────────────────────────────

func _on_message(raw: String) -> void:
	var data = JSON.parse_string(raw)
	if data == null:
		push_warning("GameBridge: received non-JSON message")
		return

	match data.get("type", ""):
		MT.FULL_STATE:       full_state_received.emit(data)
		MT.MOVE_RESULT:      move_result_received.emit(data)
		MT.DIALOGUE_START:   dialogue_started.emit(data)
		MT.DIALOGUE_RESPONSE: dialogue_response_received.emit(data)
		MT.DIALOGUE_ENDED:   dialogue_ended.emit(data)
		MT.AFFORDANCE_LIST:  affordances_received.emit(data)
		MT.ACTION_RESULT:    action_result_received.emit(data)
		MT.TICK_RESULT:      tick_result_received.emit(data)
		MT.NPC_MOVED:        npc_moved.emit(data)
		MT.WORLD_EVENT:      world_event.emit(data)
		MT.TIME_UPDATE:      time_updated.emit(data)
		MT.ERROR:            error_received.emit(data)
		_:
			push_warning("GameBridge: unknown message type: %s" % data.get("type", ""))

# ── Send helpers ──────────────────────────────────────────────────────────────

func _send(msg: Dictionary) -> void:
	if _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		push_warning("GameBridge: tried to send while not connected: %s" % msg.get("type", "?"))
		return
	_socket.send_text(JSON.stringify(msg))

func send_connect() -> void:
	_send({"type": MT.CONNECT})

func send_player_move(zone_id: String) -> void:
	_send({"type": MT.PLAYER_MOVE, "zone_id": zone_id})

func send_interact(npc_id: String) -> void:
	_send({"type": MT.PLAYER_INTERACT, "npc_id": npc_id})

func send_dialogue_input(npc_id: String, text: String) -> void:
	_send({"type": MT.DIALOGUE_INPUT, "npc_id": npc_id, "input": text})

func send_dialogue_end(npc_id: String) -> void:
	_send({"type": MT.DIALOGUE_END, "npc_id": npc_id})

func send_get_affordances() -> void:
	_send({"type": MT.GET_AFFORDANCES})

func send_execute_action(action_id: String) -> void:
	_send({"type": MT.EXECUTE_ACTION, "action_id": action_id})

func send_tick(count: int = 1) -> void:
	_send({"type": MT.TICK, "count": count})
