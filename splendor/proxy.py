import base64
import json
import zlib
import numpy as np
from MCTS import MCTS
from SplendorGame import SplendorGame as Game
from SplendorLogic import np_all_cards_1, np_all_cards_2, np_all_cards_3, np_all_nobles
from SplendorLogicNumba import my_packbits, my_unpackbits

class dotdict(dict):
    def __getattr__(self, name):
        return self[name]

action_sequence = 0
action_event = None
match_nonce = 0
token_rules_mode = "official"
legacy_token_profile = []
legacy_token_rules = False

# -------------------------------------------------------------------------
# Token Rule Profile Helpers
# -------------------------------------------------------------------------

TOKEN_RULES_MODES = ("official", "legacy", "split")

def _to_py(value):
    """Unwrap a Pyodide JsProxy into plain Python data when needed."""
    return value.to_py() if hasattr(value, "to_py") else value

def _normalize_mode(mode):
    """Accept mode names as well as the historical boolean/0-1 encoding."""
    mode = _to_py(mode)
    if isinstance(mode, str):
        name = mode.strip().lower()
        if name in TOKEN_RULES_MODES:
            return name
        if name in ("old", "true", "1"):
            return "legacy"
        return "official"
    return "legacy" if bool(int(mode)) else "official"

def _normalize_profile(mode, profile):
    """Build the per-seat legacy flag list, or None when the input is invalid."""
    count = int(g.num_players)
    if mode == "official":
        return [False] * count
    if mode == "legacy":
        return [True] * count
    profile = _to_py(profile)
    if profile is None or isinstance(profile, (str, bytes)):
        return None
    try:
        flags = [bool(flag) for flag in profile]
    except TypeError:
        return None
    if len(flags) != count:
        return None
    return flags

def _apply_token_rules():
    """Push the actual-seat profile onto the shared engine board."""
    g.board.set_token_rules(list(legacy_token_profile))

def _set_token_rules_state(mode, profile):
    """Install a validated mode/profile pair and refresh derived globals."""
    global token_rules_mode, legacy_token_profile, legacy_token_rules
    token_rules_mode = mode
    legacy_token_profile = list(profile)
    legacy_token_rules = any(legacy_token_profile)
    _apply_token_rules()

def _player_legacy(seat):
    """Legacy flag of one seat, tolerant of a not-yet-sized profile."""
    seat = int(seat)
    if 0 <= seat < len(legacy_token_profile):
        return bool(legacy_token_profile[seat])
    return bool(legacy_token_rules)

# -------------------------------------------------------------------------
# Core Engine Initialization & State Management
# -------------------------------------------------------------------------

def init_game(numMCTSSims):
    # Initializes the main game environment, MCTS agent, and clears history.
    global g, board, mcts, player, history, edit_mode, action_sequence, action_event, match_nonce

    g = Game()
    board = g.getInitBoard()
    # Keep the configured rule mode across resets, resized to the new table.
    retained = _normalize_profile(token_rules_mode, legacy_token_profile)
    if retained is None:
        retained = [_player_legacy(seat) for seat in range(int(g.num_players))]
    _set_token_rules_state(token_rules_mode, retained)

    mcts_args = dotdict({
        'numMCTSSims'     : numMCTSSims,
        'fpu'             : 0.1 if g.num_players > 2 else 0.0593,
        'cpuct'           : 1.0 if g.num_players == 3 else 0.8,
        'prob_fullMCTS'   : 1.,
        'forced_playouts' : True,
        'no_mem_optim'    : False,
        'universes'       : None if g.num_players == 3 else 3,
    })

    mcts = MCTS(g, None, mcts_args)
    player = 0
    history = []
    edit_mode = 0
    action_sequence = 0
    action_event = None
    match_nonce = int(np.random.randint(1, 2**31))
    reset_selection()
    
    return get_render_state()

def export_game_state():
    """Serialize the active match and its full rewind ledger compactly."""
    history_boards = np.stack([saved_board for _, saved_board, _ in history]) if history else np.empty((0, *board.shape), dtype=board.dtype)
    compressed_history = base64.b64encode(zlib.compress(history_boards.tobytes(), level=9)).decode("ascii")
    payload = {
        "version": 2,
        "num_players": int(g.num_players),
        "board": board.tolist(),
        "player": int(player),
        "history": {
            "count": len(history),
            "players": [int(saved_player) for saved_player, _, _ in history],
            "actions": [int(action) for _, _, action in history],
            "boards": compressed_history,
        },
        "edit_mode": int(edit_mode),
        "legacy_token_rules": bool(legacy_token_rules),
        "token_rules_mode": str(token_rules_mode),
        "legacy_token_profile": [bool(flag) for flag in legacy_token_profile],
        "action_sequence": int(action_sequence),
    }
    return json.dumps(payload, separators=(",", ":"))

def restore_game_state(json_state):
    """Restore a previously serialized match after validating its shape."""
    global board, player, history, edit_mode, action_sequence, action_event, match_nonce, mcts
    payload = json.loads(json_state)
    version = int(payload.get("version", 0))
    if version not in (1, 2) or int(payload.get("num_players", -1)) != int(g.num_players):
        raise ValueError("Saved game is incompatible")

    expected_shape = board.shape
    restored_board = np.asarray(payload["board"], dtype=board.dtype)
    if restored_board.shape != expected_shape:
        raise ValueError("Saved board shape is invalid")

    restored_history = []
    if version == 1:
        for saved_player, saved_board, action in payload.get("history", []):
            restored = np.asarray(saved_board, dtype=board.dtype)
            if restored.shape == expected_shape:
                restored_history.append([int(saved_player), restored, int(action)])
    else:
        packed = payload.get("history", {})
        count = int(packed.get("count", 0))
        players = packed.get("players", [])
        actions = packed.get("actions", [])
        if count < 0 or count > 10000 or len(players) != count or len(actions) != count:
            raise ValueError("Saved history metadata is invalid")
        raw = zlib.decompress(base64.b64decode(packed.get("boards", "")))
        expected_bytes = count * int(np.prod(expected_shape)) * board.dtype.itemsize
        if len(raw) != expected_bytes:
            raise ValueError("Saved history data is invalid")
        boards = np.frombuffer(raw, dtype=board.dtype).reshape((count, *expected_shape))
        restored_history = [[int(players[i]), np.copy(boards[i]), int(actions[i])] for i in range(count)]

    saved_mode = _normalize_mode(payload.get("token_rules_mode", payload.get("legacy_token_rules", False)))
    saved_profile = _normalize_profile(saved_mode, payload.get("legacy_token_profile"))
    if saved_profile is None:
        # Split payload without a usable profile: fall back to the boolean encoding.
        saved_mode = "legacy" if bool(payload.get("legacy_token_rules", False)) else "official"
        saved_profile = _normalize_profile(saved_mode, None)
    _set_token_rules_state(saved_mode, saved_profile)
    g.board.copy_state(restored_board, True)
    board = g.board.get_state()
    player = int(payload["player"])
    history = restored_history
    edit_mode = int(payload.get("edit_mode", 0))
    action_sequence = max(int(payload.get("action_sequence", len(restored_history))), len(restored_history))
    action_event = None
    match_nonce = int(np.random.randint(1, 2**31))
    if mcts is not None:
        mcts.nodes_data.clear()
    reset_selection()
    return get_render_state()

def changeDifficulty(numMCTSSims):
    # Dynamically adjusts MCTS depth parameters during gameplay.
    global mcts
    if mcts is not None:
        mcts.args.numMCTSSims = numMCTSSims

def getNextState(action):
    # Applies a move to the board, advances the player turn, and saves history.
    global g, board, mcts, player, history, action_sequence, action_event

    # MCTS canonicalization rotates the board profile, so restore actual seats.
    _apply_token_rules()
    actor = int(player)
    action_sequence += 1
    action_event = _describe_action_event(int(action), actor, action_sequence)
    previous_reserved = [np.copy(g.board.players_reserved[6*actor + i]) for i in range(6)]
    previous_gems = np.copy(g.board.players_gems[actor])
    previous_nobles = [np.copy(g.board.players_nobles[g.board.num_nobles * actor + i]) for i in range(g.board.num_nobles)]
    history.insert(0, [player, np.copy(board), action])
    board, player = g.getNextState(board, player, action)
    g.board.copy_state(board, False)
    _complete_action_event(action_event, actor, previous_reserved, previous_nobles, previous_gems)
    return get_render_state()

# -------------------------------------------------------------------------
# Formatting & Type Conversion Helpers
# -------------------------------------------------------------------------

DIFFERENT_GEMS_UP_TO_3 = [
    [0], [1], [2], [3], [4],
    [0,1], [0,2], [0,3], [0,4], [1,2], [1,3], [1,4], [2,3], [2,4], [3,4],
    [0,1,2], [0,1,3], [0,1,4], [0,2,3], [0,2,4], [0,3,4], [1,2,3], [1,2,4], [1,3,4], [2,3,4]
]

DIFFERENT_GEMS_UP_TO_2 = [
    [0], [1], [2], [3], [4],
    [0,1], [0,2], [0,3], [0,4], [1,2], [1,3], [1,4], [2,3], [2,4], [3,4]
]

def _convertTokensToJS(card_data_1):
    # Translates raw NumPy array token arrays into standard Python lists.
    tokens_col = card_data_1[:6].nonzero()[0]
    tokens_val = card_data_1[tokens_col]
    return np.vstack([tokens_col, tokens_val]).T.tolist()

def _convertCardToJS(card_data_1, card_data_2):
    # Packages a dual-matrix card format into [color, points, [cost matrix]].
    if card_data_1.sum() == 0:
        return [-1, -1, []]
    
    color = card_data_2.nonzero()[0][0].item()
    points = card_data_2[6].item()
    tokens = _convertTokensToJS(card_data_1)
    
    return [color, points, tokens]

def _describe_action_event(action, actor, sequence, source_board=None):
    """Capture semantic move details from the board immediately before a move."""
    g.board.copy_state(board if source_board is None else source_board, False)
    event = {
        "id": f"{match_nonce}:{int(sequence)}",
        "actor": int(actor),
        "type": "unknown",
        "label": "made a move",
        "gems": [],
        "card": None,
        "tier": -1,
        "index": -1,
    }

    if action >= 80:
        if action == 80 and int(g.board.players_gems[actor].sum()) > 10:
            event.update({"type": "return", "label": "returned gold", "gems": [5]})
        else:
            event.update({"type": "pass", "label": "passed"})
        return event

    if action < 12:
        tier, index = divmod(action, 4)
        event.update({
            "type": "buy",
            "label": "bought a development",
            "tier": tier,
            "index": index,
            "card": _convertCardToJS(g.board.cards_tiers[8*tier + 2*index], g.board.cards_tiers[8*tier + 2*index + 1]),
        })
    elif action < 24:
        tier, index = divmod(action - 12, 4)
        event.update({
            "type": "reserve",
            "label": "reserved a development",
            "tier": tier,
            "index": index,
            "card": _convertCardToJS(g.board.cards_tiers[8*tier + 2*index], g.board.cards_tiers[8*tier + 2*index + 1]),
        })
    elif action < 27:
        event.update({"type": "reserve", "label": "reserved from a deck", "tier": action - 24})
    elif action < 30:
        index = action - 27
        event.update({
            "type": "buy",
            "label": "bought a reserved card",
            "index": index,
            "card": _convertCardToJS(g.board.players_reserved[6*actor + 2*index], g.board.players_reserved[6*actor + 2*index + 1]),
        })
    elif action < 60:
        gems = DIFFERENT_GEMS_UP_TO_3[action - 30] if action < 55 else [action - 55, action - 55]
        event.update({"type": "gems", "label": "collected gems", "gems": gems})
    else:
        combo_index = action - 60
        gems = DIFFERENT_GEMS_UP_TO_2[combo_index] if action < 75 else [action - 75, action - 75]
        event.update({"type": "return", "label": "returned gems", "gems": gems})

    return event

def _complete_action_event(event, actor, previous_reserved, previous_nobles, previous_gems):
    """Attach assets that arrived in the acting player's inventory."""
    event["arriving_gems"] = []
    event["visitors"] = []
    event["reserved_index"] = -1

    for index in range(3):
        row = 6 * actor + 2 * index
        before_1, before_2 = previous_reserved[2 * index:2 * index + 2]
        after_1, after_2 = g.board.players_reserved[row], g.board.players_reserved[row + 1]
        if (not np.array_equal(before_1, after_1) or not np.array_equal(before_2, after_2)) and after_1.sum() > 0:
            event["reserved_index"] = index
            if event["type"] == "reserve" and event["card"] is None:
                event["card"] = _convertCardToJS(after_1, after_2)
            break

    for index in range(g.board.num_nobles):
        after = g.board.players_nobles[g.board.num_nobles * actor + index]
        if previous_nobles[index].sum() == 0 and after.sum() > 0:
            event["visitors"].append(_convertTokensToJS(after)[:3])

    for color, delta in enumerate(g.board.players_gems[actor] - previous_gems):
        if delta > 0:
            event["arriving_gems"].extend([color] * int(delta))

def _get_turn_log():
    """Return newest-first semantic history while preserving the live board view."""
    current_board = np.copy(board)
    events = []
    try:
        for offset, (actor, saved_board, action) in enumerate(history):
            actor = int(actor)
            event = _describe_action_event(int(action), actor, action_sequence - offset, saved_board)
            previous_reserved = [np.copy(g.board.players_reserved[6*actor + i]) for i in range(6)]
            previous_nobles = [np.copy(g.board.players_nobles[g.board.num_nobles * actor + i]) for i in range(g.board.num_nobles)]
            previous_gems = np.copy(g.board.players_gems[actor])
            post_board = current_board if offset == 0 else history[offset - 1][1]
            g.board.copy_state(post_board, False)
            _complete_action_event(event, actor, previous_reserved, previous_nobles, previous_gems)
            event["id"] = f"history:{offset}:{actor}:{int(action)}"
            event["offset"] = offset
            event["moves_back"] = offset + 1
            events.append(event)
    finally:
        g.board.copy_state(current_board, False)
    return events

# -------------------------------------------------------------------------
# Move Translation & Validation
# -------------------------------------------------------------------------

def _get_move_index():
    # Maps internal UI selection states to exact SplendorGame action integer IDs.
    global sel_type, sel_items
    overflow = max(0, int(g.board.players_gems[player].sum()) - 10)
    
    if sel_type == 'none' or not sel_items:
        return -1
        
    if sel_type == 'card':
        tier, index = sel_items[0]
        return 27 + index if tier == -1 else tier * 4 + index
            
    elif sel_type == 'rsv':
        tier, index = sel_items[0]
        return 12 + tier * 4 + index
        
    elif sel_type == 'gem':
        if len(sel_items) == 2 and sel_items[0] == sel_items[1]:
            return 55 + sel_items[0] 
        else:
            sorted_gems = sorted(sel_items)
            try:
                combo_index = DIFFERENT_GEMS_UP_TO_3.index(sorted_gems)
                return 30 + combo_index 
            except ValueError:
                return -1
    
    elif sel_type == 'deck':
        return 24 + sel_items[0]
        
    elif sel_type == 'gemback':
        if sel_items == [5]:
            return 80 if overflow > 0 else -1
        if 5 in sel_items:
            return -1
        if len(sel_items) == 2 and sel_items[0] == sel_items[1]:
            return 60 + DIFFERENT_GEMS_UP_TO_2.index([sel_items[0]]) + len(DIFFERENT_GEMS_UP_TO_2)
        sorted_gems = sorted(sel_items)
        try:
            combo_index = DIFFERENT_GEMS_UP_TO_2.index(sorted_gems)
            return 60 + combo_index
        except ValueError:
            return -1

    return -1

def _is_selection_valid():
    # Validates against the engine's rule constraints for the active player.
    global g, board, player
    
    if sel_type == 'none':
        return False
        
    move = _get_move_index()
    if move < 0 or move >= g.getActionSize():
        return False
        
    valids = g.getValidMoves(board, player)
    return bool(valids[move])

def _get_move_short_desc():
    # Generates a human-readable string based on active selection vectors.
    global sel_type, sel_items
    
    if sel_type == 'none' or not sel_items:
        return "none"
    
    if sel_type == 'card':
        return "buy a reserved card" if sel_items[0][0] == -1 else "buy a card"
    elif sel_type == 'rsv':
        return "reserve a card"
    elif sel_type == 'deck':
        return "reserve a card from deck"
    elif sel_type == 'gem':
        if len(sel_items) == 2 and sel_items[0] == sel_items[1]:
            return "take 2 similar gems"
        if len(sel_items) == 1:
            return "take 1 gem"
        return f"take {len(sel_items)} different gems"
    elif sel_type == 'gemback':
        if sel_items == [5]:
            return "return 1 gold token"
        if len(sel_items) == 2 and sel_items[0] == sel_items[1]:
            return "return 2 matching tokens"
        if len(sel_items) == 1:
            return "return 1 token"
        return f"return {len(sel_items)} different tokens"
        
    return "none"

def _get_last_action_details():
    # Extracts the latest move from the ledger to drive UI styling highlights.
    global history
    
    if not history:
        return ["none", -1]
        
    last_move = int(history[0][2])
    if last_move < 0:
        return ["none", -1]
    
    if last_move < 12:
        return ["card", last_move]
    elif last_move < 24:
        return ["rsv", last_move - 12]
    elif last_move < 27:
        return ["deck", last_move - 24]
    elif last_move < 30:
        return ["buyrsv", last_move - 27]
    elif last_move < 60: 
        combo_idx = last_move - 30
        gems = DIFFERENT_GEMS_UP_TO_3[combo_idx] if last_move < 55 else [last_move - 55, last_move - 55]
        return ["gem", gems]
    elif last_move < 80:
        combo_idx = last_move - 60
        gems = DIFFERENT_GEMS_UP_TO_2[combo_idx] if last_move < 75 else [last_move - 75, last_move - 75]
        return ["gemback", gems]
    elif last_move == 80:
        actor, source_board, _ = history[0]
        gems_row = 32 + g.num_players + int(actor)
        if int(source_board[gems_row].sum()) > 10:
            return ["gemback", [5]]
    return ["pass", []]

def _overflowed_seats():
    g.board.copy_state(board, False)
    return {p for p in range(int(g.num_players)) if int(g.board.players_gems[p].sum()) > 10}

def set_token_rules(mode, profile=None):
    """Switch between official, legacy, and split (humans official / AI legacy) rules."""
    wanted_mode = _normalize_mode(mode)
    wanted_profile = _normalize_profile(wanted_mode, profile)
    if wanted_profile is None:
        # Malformed split profile: keep the current configuration untouched.
        return get_render_state()

    # Marking an overflowed seat legacy would let its >10 gem inventory survive
    # and advance turns, so refuse the change and keep the current mode.
    newly_legacy = {seat for seat, flag in enumerate(wanted_profile) if flag and not _player_legacy(seat)}
    if newly_legacy and (newly_legacy & _overflowed_seats()):
        return get_render_state()

    if wanted_mode != token_rules_mode or wanted_profile != list(legacy_token_profile):
        _set_token_rules_state(wanted_mode, wanted_profile)
        if mcts is not None:
            mcts.nodes_data.clear()
        reset_selection()
    return get_render_state()

# -------------------------------------------------------------------------
# Interaction Handlers (Pyodide Entrypoints)
# -------------------------------------------------------------------------

def handle_action(action_name, *args):
    # Main Python-side router receiving directives triggered via Alpine.js JS bridging.
    if 'g' not in globals() or g is None:
        return json.dumps({"viewData": {}, "extra": {}})
        
    if action_name == "click_and_render":
        return click_and_render(args[0], args[1], args[2] if len(args) > 2 else -1)
    elif action_name == "select_card_action":
        return select_card_action(args[0], args[1], args[2])
    elif action_name == "clear_selection":
        reset_selection()
        return get_render_state()
    elif action_name == "confirm_action":
        return confirm_action()
    elif action_name == "set_token_rules":
        return set_token_rules(args[0], args[1] if len(args) > 1 else None)
    elif action_name == "undo":
        if len(args) > 0:
            humans = args[0].to_py() if hasattr(args[0], 'to_py') else args[0]
            return undo(humans)
        return undo()
    elif action_name == "rewind_to":
        return rewind_to(args[0])
    elif action_name == "filter_cards":
        global editor_matching_cards
        editor_matching_cards = filterCards(args[0], args[1], args[2])
        return get_render_state()
    elif action_name == "change_deck_card":
        return changeDeckCard(args[0], args[1], args[2], args[3], args[4], False)
    elif action_name == "change_noble":
        return changeNoble(args[0], args[1], args[2])
    elif action_name == "change_gem":
        return changeGemOrNbCards(args[0], args[1], args[2], args[3])
        
    return get_render_state()

def click_and_render(item_category, arg1, arg2=-1):
    # Triggers selection state updates before broadcasting back the unified state.
    click_item(item_category, arg1, arg2)
    return get_render_state()

def select_card_action(mode, tier, index):
    """Select a card action directly, without relying on click-cycle state."""
    global sel_type, sel_items
    if max(0, int(g.board.players_gems[player].sum()) - 10) > 0:
        return get_render_state()
    tier = int(tier)
    index = int(index)
    if mode == "buy":
        sel_type = "card"
        sel_items = [[tier, index]]
    elif mode == "reserve" and tier >= 0:
        sel_type = "rsv"
        sel_items = [[tier, index]]
    else:
        reset_selection()
    return get_render_state()

def confirm_action():
    # Commits the formulated command to the environment if legal.
    global sel_type, sel_items, player, board
    
    if not _is_selection_valid():
        return get_render_state()
        
    move = _get_move_index()
    _ = getNextState(move) 
    
    reset_selection()
    return get_render_state()

def undo(are_players_human=None):
    # Traverses the history stack backwards until encountering a human player turn.
    global board, player, history
    
    if are_players_human is None:
        are_players_human = [True, True, True]
        
    if len(history) > 0:
        index_to_restore = 0
        for index, state in enumerate(history):
            p = int(state[0])
            if are_players_human[p] and (index+1 == len(history) or history[index+1][0] != p):
                index_to_restore = index
                break
                
        state = history[index_to_restore]
        player = state[0]
        board = np.copy(state[1])
        history = history[index_to_restore+1:]
        reset_selection()
        
    return get_render_state()

def rewind_to(history_offset):
    """Restore the position before a selected move and discard the newer branch."""
    global board, player, history, action_event
    history_offset = int(history_offset)
    if 0 <= history_offset < len(history):
        state = history[history_offset]
        player = int(state[0])
        board = np.copy(state[1])
        history = history[history_offset + 1:]
        g.board.copy_state(board, False)
        action_event = None
        reset_selection()
    return get_render_state()

# -------------------------------------------------------------------------
# Selection State Machine 
# -------------------------------------------------------------------------

sel_type = 'none'
sel_items = []

def reset_selection():
    # Flushes pending selection buffers globally.
    global sel_type, sel_items
    sel_type = 'none'
    sel_items = []

def click_item(item_category, arg1, arg2=-1):
    # Processes UI clicks to construct actionable move arrays.
    global sel_type, sel_items
    overflow = max(0, int(g.board.players_gems[player].sum()) - 10)
    if overflow > 0 and item_category != 'gemback':
        return
    # Legacy rules make returning gems a voluntary turn, so allow it outside overflow
    if overflow == 0 and item_category == 'gemback' and not _player_legacy(player):
        return
    
    if item_category == 'gem':
        color = arg1
        if color == 5:
            return
            
        if sel_type != 'gem':
            sel_type = 'gem'
            sel_items = [color]
        else:
            if color in sel_items:
                if len(sel_items) == 1:
                    sel_items.append(color)
                elif len(sel_items) == 2 and sel_items[0] == sel_items[1] and sel_items[0] == color:
                    reset_selection()
                else:
                    sel_items.remove(color)
                    if not sel_items:
                        sel_type = 'none'
            else:
                if len(sel_items) == 2 and sel_items[0] == sel_items[1]:
                    pass 
                elif len(sel_items) < 3:
                    sel_items.append(color)

    elif item_category == 'card':
        tier = arg1
        index = arg2
        if sel_type == 'card' and sel_items == [[tier, index]]:
            sel_type = 'rsv'
        elif sel_type == 'rsv' and sel_items == [[tier, index]]:
            reset_selection()
        else:
            sel_type = 'card'
            sel_items = [[tier, index]]

    elif item_category == 'reserved':
        index = arg1
        if sel_type == 'card' and sel_items == [[-1, index]]:
            reset_selection()
        else:
            sel_type = 'card'
            sel_items = [[-1, index]]

    elif item_category == 'deck':
        tier = arg1
        if sel_type == 'deck' and sel_items == [tier]:
            reset_selection()
        else:
            sel_type = 'deck'
            sel_items = [tier]
            
    elif item_category == 'gemback':
        color = int(arg1)
        if color == 5:
            if sel_type == 'gemback' and sel_items == [5]:
                reset_selection()
            else:
                sel_type = 'gemback'
                sel_items = [5]
            return

        if sel_type != 'gemback' or 5 in sel_items:
            sel_type = 'gemback'
            sel_items = [color]
        elif color in sel_items:
            if len(sel_items) == 1:
                valid_moves = g.getValidMoves(board, player)
                if valid_moves[75 + color]:
                    sel_items.append(color)
                else:
                    reset_selection()
            elif len(sel_items) == 2 and sel_items[0] == sel_items[1] and sel_items[0] == color:
                reset_selection()
            else:
                sel_items.remove(color)
                if not sel_items:
                    sel_type = 'none'
        elif len(sel_items) < 2 and not (len(sel_items) == 2 and sel_items[0] == sel_items[1]):
            sel_items.append(color)

# -------------------------------------------------------------------------
# Serialized Presentation Engine
# -------------------------------------------------------------------------

def get_render_state():
    # Assembles the definitive truth for the game state as a JSON string for JS injection.
    global g, board, player, history
    
    if g is None or board is None:
        return json.dumps({"viewData": {}, "extra": {}})

    _apply_token_rules()
        
    num_players = g.num_players

    view = {
        "bank": [int(g.board.bank[0][c]) for c in range(6)],
        "tiers": [],
        "decks": [int(g.board.nb_deck_tiers[2*t, :5].sum()) for t in range(3)],
        "nobles": [],
        "players": []
    }
    
    for t in range(3):
        tier_cards = []
        for i in range(4):
            c1 = g.board.cards_tiers[8*t + 2*i]
            c2 = g.board.cards_tiers[8*t + 2*i + 1]
            tier_cards.append(_convertCardToJS(c1, c2))
        view["tiers"].append(tier_cards)
        
    for n in g.board.nobles:
        if n.sum() > 0:
            view["nobles"].append(_convertTokensToJS(n)[:3])
        else:
            view["nobles"].append([])
            
    for p in range(num_players):
        pts = int(g.getScore(board, p))
        
        p_data = {
            "gems": [int(g.board.players_gems[p][c]) for c in range(6)],
            "cards": [int(g.board.players_cards[p][c]) for c in range(6)],
            "reserved": [],
            "nobles": [],
            "points": pts
        }
        p_data["total_gems"] = sum(p_data["gems"])
        
        for i in range(3):
            c1 = g.board.players_reserved[6*p + 2*i]
            c2 = g.board.players_reserved[6*p + 2*i + 1]
            p_data["reserved"].append(_convertCardToJS(c1, c2))
            
        noble_start = g.board.num_nobles * p
        noble_rows = g.board.players_nobles[noble_start:noble_start + g.board.num_nobles]
        for noble in noble_rows:
            if noble.sum() > 0:
                p_data["nobles"].append(_convertTokensToJS(noble)[:3])
        p_data["noble_points"] = int(noble_rows[:, 6].sum())

        view["players"].append(p_data)
        
    valid_moves = g.getValidMoves(board, player)
    card_actions = [
        [
            {
                "buy": bool(valid_moves[tier * 4 + index]),
                "reserve": bool(valid_moves[12 + tier * 4 + index]),
            }
            for index in range(4)
        ]
        for tier in range(3)
    ]
    reserved_actions = [bool(valid_moves[27 + index]) for index in range(3)]
    overflow_count = max(0, int(g.board.players_gems[player].sum()) - 10)
    take_options = [
        DIFFERENT_GEMS_UP_TO_3[action - 30] if action < 55 else [action - 55, action - 55]
        for action in range(30, 60)
        if valid_moves[action]
    ]
    return_options = [
        DIFFERENT_GEMS_UP_TO_2[action - 60] if action < 75 else [action - 75, action - 75]
        for action in range(60, 80)
        if valid_moves[action]
    ]
    if overflow_count > 0 and valid_moves[80]:
        return_options.append([5])

    extra = {
        "sel_type": sel_type,
        "sel_items": sel_items,
        "can_confirm": _is_selection_valid(),
        "move_desc": _get_move_short_desc(),
        "last_action": _get_last_action_details(),
        "previous_player": int(history[0][0]) if history else -1,
        "matching_cards": editor_matching_cards,
        "card_actions": card_actions,
        "reserved_actions": reserved_actions,
        "overflow_count": overflow_count,
        "take_options": take_options,
        "return_options": return_options,
        "action_event": action_event,
        "turn_log": _get_turn_log(),
        "legacy_token_rules": bool(legacy_token_rules),
        "token_rules_mode": str(token_rules_mode),
        "legacy_token_profile": [bool(flag) for flag in legacy_token_profile],
        "current_player_legacy": _player_legacy(player),
        "token_rules_locked": overflow_count > 0,
    }

    end_status = g.getGameEnded(board, player)
    winners = [i for i, x in enumerate(end_status) if x > 0]
    
    response = {
        "viewData": view,
        "extra": extra,
        "currentPlayer": int(player),
        "gameEnded": bool(end_status[0] != 0),
        "winners": winners if end_status[0] != 0 else [],
        "canUndo": len(history) > 0,
        "editMode": int(edit_mode),
        "token_rules": str(token_rules_mode),
        "token_rules_mode": str(token_rules_mode),
        "legacy_token_profile": [bool(flag) for flag in legacy_token_profile],
    }
    
    return json.dumps(response)

# -------------------------------------------------------------------------
# God-Mode & Editor Configuration Methods 
# -------------------------------------------------------------------------

edit_mode = 0
editor_matching_cards = []

def set_edit_mode(mode):
    # Globally activates or deactivates environment editing overrides.
    global edit_mode
    edit_mode = int(mode)
    return get_render_state()

def filterCards(tier, color, points):
    # Generates a restricted view of cards matching user-provided criteria.
    pattern = np.zeros(7,)
    pattern[color] = 1
    pattern[6] = points
    
    list_cards = [np_all_cards_1, np_all_cards_2, np_all_cards_3][tier].reshape(-1,2,7)
    indexes = np.where((list_cards[:,1,:] == pattern).all(axis=1))[0]
    
    return [_convertCardToJS(list_cards[i,0,:], list_cards[i,1,:]) for i in indexes]

def searchCard(card, many_cards, onlyCardIncome=False):
    # Locates specific multi-dimensional arrays efficiently across board memory pools.
    if onlyCardIncome:
        assert(card.ndim == 1)
        assert(many_cards.ndim == 3)
        return np.where((many_cards[:,1,:] == card).all(axis=1))[0]

    assert(card.ndim == 2)
    if many_cards.ndim == 3:    
        result = np.where(np.logical_and(
            (many_cards[:,0,:] == card[0,:]).all(axis=1),
            (many_cards[:,1,:] == card[1,:]).all(axis=1)
        ))[0]
    else:
        result = np.where(np.logical_and(
            (many_cards[ ::2,:] == card[0,:]).all(axis=1),
            (many_cards[1::2,:] == card[1,:]).all(axis=1)
        ))[0]
        result *= 2
        
    return result

def changeDeckCard(tier, color, points, selectedIndexInList, locationIndex, lapidaryMode):
    # Performs surgical injection of selected deck cards, swapping visible and static states.
    global g, board, player
    
    pattern = np.zeros(7,)
    pattern[color] = 1
    pattern[6] = points
    
    list_cards = [np_all_cards_1, np_all_cards_2, np_all_cards_3][tier].reshape(-1,2,7)
    indexes = searchCard(pattern, list_cards, onlyCardIncome=True)

    newCardIndex = indexes[selectedIndexInList]
    newCardX, newCardY = divmod(newCardIndex, list_cards.shape[0] // 5)
    newCard = list_cards[newCardIndex, :, :]

    oldCard = g.board.cards_tiers[8*tier+2*locationIndex:8*tier+2*locationIndex+2]
    oldCardIndex = searchCard(oldCard, list_cards)[0]
    oldCardX, oldCardY = divmod(oldCardIndex, list_cards.shape[0] // 5)
    old_i = 8*tier + 2*locationIndex

    if newCardIndex != oldCardIndex:
        index_visible = searchCard(newCard, g.board.cards_tiers)
        index_reserved = searchCard(newCard, g.board.players_reserved)
        deck_cards = my_unpackbits(g.board.nb_deck_tiers[2*tier+1, newCardX])
        new_is_in_deck = (deck_cards[newCardY] > 0)
        
        if index_visible.size > 0 or index_reserved.size > 0:
            new_i = index_visible[0] if index_visible.size else index_reserved[0]
            g.board.cards_tiers[[old_i  , new_i  ], :] = g.board.cards_tiers[[new_i  , old_i  ], :]
            g.board.cards_tiers[[old_i+1, new_i+1], :] = g.board.cards_tiers[[new_i+1, old_i+1], :]
        else:
            g.board.cards_tiers[old_i  , :] = newCard[0, :]
            g.board.cards_tiers[old_i+1, :] = newCard[1, :]
            
            if new_is_in_deck:
                deck_cards[newCardY] = 0
                g.board.nb_deck_tiers[2*tier+1, newCardX] = my_packbits(deck_cards)
                g.board.nb_deck_tiers[2*tier, newCardX] -= 1
                
                deck_cards = my_unpackbits(g.board.nb_deck_tiers[2*tier+1, oldCardX])
                deck_cards[oldCardY] = 1
                g.board.nb_deck_tiers[2*tier+1, oldCardX] = my_packbits(deck_cards)
                g.board.nb_deck_tiers[2*tier, oldCardX] += 1

    if lapidaryMode:
        end_tier = 8*(tier+1)
        g.board.cards_tiers[old_i:end_tier, :] = np.roll(g.board.cards_tiers[old_i:end_tier, :], shift=-2, axis=0)

    return get_render_state()

def changeGemOrNbCards(p, color, type_, delta):
    # Modifies discrete gem counts or permanent bonus counts artificially.
    global g, board, player
    
    if p < 0:
        g.board.bank[0][color] = max(0, g.board.bank[0][color] + delta)
    elif type_ == 'gem':
        g.board.players_gems[p][color] = max(0, g.board.players_gems[p][color] + delta)
    else:
        g.board.players_cards[p][color] = max(0, g.board.players_cards[p][color] + delta)

    return get_render_state()

def changeNoble(index, nobleId, assignedPlayer):
    # Reassigns nobles from global pool to specific players manually.
    global g, board, player
    
    g.board.nobles[index, :] = np_all_nobles[nobleId, :] if assignedPlayer < 0 else 0
    for p in range(g.num_players):
        g.board.players_nobles[g.board.num_nobles * p + index, :] = np_all_nobles[nobleId, :] if assignedPlayer == p else 0

    return get_render_state()