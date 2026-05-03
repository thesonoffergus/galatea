## Constants for WebSocket message type strings.
extends Node

# Client → Server
const CONNECT          = "connect"
const PLAYER_MOVE      = "player_move"
const PLAYER_INTERACT  = "player_interact"
const DIALOGUE_INPUT   = "dialogue_input"
const DIALOGUE_END     = "dialogue_end"
const GET_AFFORDANCES  = "get_affordances"
const EXECUTE_ACTION   = "execute_action"
const TICK             = "tick"

# Server → Client (responses)
const FULL_STATE       = "full_state"
const MOVE_RESULT      = "move_result"
const DIALOGUE_START   = "dialogue_start"
const DIALOGUE_RESPONSE = "dialogue_response"
const DIALOGUE_ENDED   = "dialogue_ended"
const AFFORDANCE_LIST  = "affordance_list"
const ACTION_RESULT    = "action_result"
const TICK_RESULT      = "tick_result"
const ERROR            = "error"

# Server → Client (push)
const NPC_MOVED        = "npc_moved"
const WORLD_EVENT      = "world_event"
const TIME_UPDATE      = "time_update"
