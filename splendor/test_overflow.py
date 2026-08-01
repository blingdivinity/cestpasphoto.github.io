import json
import sys
from types import SimpleNamespace
import unittest

import numpy as np

from SplendorLogic import list_different_gems_up_to_2, list_different_gems_up_to_3
from MCTS import MCTS, get_next_best_action_and_canonical_state
from SplendorLogicNumba import Board, idx_gold, idx_points, observation_size


def combination_action(start, combinations, colors):
    target = np.zeros(7, dtype=np.int8)
    target[list(colors)] = 1
    return start + next(i for i, combo in enumerate(combinations) if np.array_equal(combo, target))


TAKE_THREE = combination_action(30, list_different_gems_up_to_3, (0, 1, 2))
TAKE_ONE_WHITE = combination_action(30, list_different_gems_up_to_3, (0,))
RETURN_ONE_WHITE = combination_action(60, list_different_gems_up_to_2, (0,))
RETURN_WHITE_BLUE = combination_action(60, list_different_gems_up_to_2, (0, 1))


class ForcedOverflowTests(unittest.TestCase):
    def setUp(self):
        # Build a minimal deterministic board. This avoids unrelated deck
        # bit-packing differences between browser NumPy and newer desktop NumPy.
        self.board = Board.__new__(Board)
        self.board.num_players = 2
        self.board.current_player_index = 0
        self.board.num_gems_in_play = 4
        self.board.num_nobles = 3
        self.board.max_moves = 124
        self.board.score_win = 15
        self.board.legacy_token_rules = np.zeros(2, dtype=np.bool_)
        self.board.state = None
        state = np.zeros(observation_size(2), dtype=np.int8)
        self.board.copy_state(state, copy_or_not=False)
        self.board.bank[0] = np.array([4, 4, 4, 4, 4, 5, 0], dtype=np.int8)
        self.board.cards_tiers[0] = np.array([1, 0, 0, 0, 0, 0, 0], dtype=np.int8)
        self.board.cards_tiers[1] = np.array([1, 0, 0, 0, 0, 0, 0], dtype=np.int8)

    def set_inventory(self, gems):
        gems = np.asarray(gems, dtype=np.int8)
        self.board.players_gems[0] = 0
        self.board.players_gems[0, : len(gems)] = gems
        self.board.bank[0, :5] = self.board.num_gems_in_play - self.board.players_gems[0, :5]
        self.board.bank[0, idx_gold] = 5 - self.board.players_gems[0, idx_gold]

    def test_normal_play_preserves_fixed_action_space_and_masks_returns(self):
        valid = self.board.valid_moves(0)
        self.assertEqual((81,), valid.shape)
        self.assertFalse(valid[60:80].any())
        self.assertTrue(valid[80])

    def test_take_over_limit_forces_same_player_return_and_counts_one_turn(self):
        self.set_inventory([2, 2, 2, 2, 1, 0])
        initial_round = int(self.board.bank[0, idx_points])
        self.assertTrue(self.board.valid_moves(0)[TAKE_THREE])

        next_player = self.board.make_move(TAKE_THREE, 0, deterministic=True)

        self.assertEqual(0, next_player)
        self.assertEqual(12, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round, int(self.board.bank[0, idx_points]))
        valid = self.board.valid_moves(0)
        self.assertFalse(valid[:60].any())
        self.assertTrue(valid[RETURN_WHITE_BLUE])
        self.assertFalse(valid[80])

        next_player = self.board.make_move(RETURN_WHITE_BLUE, 0, deterministic=True)
        self.assertEqual(1, next_player)
        self.assertEqual(10, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round + 1, int(self.board.bank[0, idx_points]))

    def test_overflow_three_can_be_resolved_across_multiple_existing_actions(self):
        self.set_inventory([2, 2, 2, 2, 2, 0])
        initial_round = int(self.board.bank[0, idx_points])

        self.assertEqual(0, self.board.make_move(TAKE_THREE, 0, deterministic=True))
        self.assertEqual(13, int(self.board.players_gems[0].sum()))
        self.assertEqual(0, self.board.make_move(RETURN_WHITE_BLUE, 0, deterministic=True))
        self.assertEqual(11, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round, int(self.board.bank[0, idx_points]))

        valid = self.board.valid_moves(0)
        self.assertTrue(valid[RETURN_ONE_WHITE])
        self.assertFalse(valid[RETURN_WHITE_BLUE])
        self.assertFalse(valid[75:80].any())

        self.assertEqual(1, self.board.make_move(RETURN_ONE_WHITE, 0, deterministic=True))
        self.assertEqual(10, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round + 1, int(self.board.bank[0, idx_points]))

    def test_reserving_at_ten_takes_gold_then_forces_gold_return(self):
        self.set_inventory([2, 2, 2, 2, 2, 0])
        initial_round = int(self.board.bank[0, idx_points])
        initial_gold_bank = int(self.board.bank[0, idx_gold])

        self.assertEqual(0, self.board.make_move(12, 0, deterministic=True))
        self.assertEqual(11, int(self.board.players_gems[0].sum()))
        self.assertEqual(1, int(self.board.players_gems[0, idx_gold]))
        self.assertEqual(initial_round, int(self.board.bank[0, idx_points]))
        valid = self.board.valid_moves(0)
        self.assertTrue(valid[80])
        self.assertFalse(valid[:60].any())
        self.assertFalse(valid[75:80].any())

        self.assertEqual(1, self.board.make_move(80, 0, deterministic=True))
        self.assertEqual(10, int(self.board.players_gems[0].sum()))
        self.assertEqual(0, int(self.board.players_gems[0, idx_gold]))
        self.assertEqual(initial_gold_bank, int(self.board.bank[0, idx_gold]))
        self.assertEqual(initial_round + 1, int(self.board.bank[0, idx_points]))

    def test_return_options_never_overshoot_remaining_overflow(self):
        self.set_inventory([3, 2, 2, 2, 2, 0])
        valid = self.board.valid_moves(0)
        self.assertEqual(1, int(self.board._overflow(0)))
        self.assertTrue(valid[RETURN_ONE_WHITE])
        self.assertFalse(valid[RETURN_WHITE_BLUE])
        self.assertFalse(valid[75:80].any())

    def test_legacy_mode_caps_takes_and_allows_voluntary_returns(self):
        self.board.set_token_rules(True)
        self.set_inventory([2, 2, 2, 2, 1, 0])
        valid = self.board.valid_moves(0)
        self.assertTrue(valid[TAKE_ONE_WHITE])
        self.assertFalse(valid[TAKE_THREE])
        self.assertFalse(valid[55:60].any())
        self.assertTrue(valid[RETURN_ONE_WHITE])
        self.assertTrue(valid[RETURN_WHITE_BLUE])

        initial_round = int(self.board.bank[0, idx_points])
        self.assertEqual(1, self.board.make_move(RETURN_ONE_WHITE, 0, deterministic=True))
        self.assertEqual(8, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round + 1, int(self.board.bank[0, idx_points]))

    def test_legacy_reserve_at_ten_skips_gold(self):
        self.board.set_token_rules(True)
        self.set_inventory([2, 2, 2, 2, 2, 0])
        initial_gold_bank = int(self.board.bank[0, idx_gold])

        self.assertEqual(1, self.board.make_move(12, 0, deterministic=True))
        self.assertEqual(10, int(self.board.players_gems[0].sum()))
        self.assertEqual(0, int(self.board.players_gems[0, idx_gold]))
        self.assertEqual(initial_gold_bank, int(self.board.bank[0, idx_gold]))

    def test_legacy_mode_recovers_an_overflowed_history_state(self):
        self.board.set_token_rules(True)
        self.set_inventory([3, 2, 2, 2, 2, 0])
        initial_round = int(self.board.bank[0, idx_points])

        valid = self.board.valid_moves(0)
        self.assertFalse(valid[:60].any())
        self.assertTrue(valid[RETURN_ONE_WHITE])
        self.assertFalse(valid[RETURN_WHITE_BLUE])
        self.assertEqual(1, self.board.make_move(RETURN_ONE_WHITE, 0, deterministic=True))
        self.assertEqual(10, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_round + 1, int(self.board.bank[0, idx_points]))

    def test_switching_back_to_official_restores_forced_return_semantics(self):
        self.board.set_token_rules(True)
        self.set_inventory([2, 2, 2, 2, 1, 0])
        self.assertFalse(self.board.valid_moves(0)[TAKE_THREE])

        self.board.set_token_rules(False)
        valid = self.board.valid_moves(0)
        self.assertTrue(valid[TAKE_THREE])
        self.assertFalse(valid[60:80].any())

    def test_per_player_profile_applies_rules_by_seat(self):
        self.board.set_token_rules([False, True])
        self.set_inventory([2, 2, 2, 2, 1, 0])
        self.board.players_gems[1] = self.board.players_gems[0]

        official_moves = self.board.valid_moves(0)
        legacy_moves = self.board.valid_moves(1)
        self.assertTrue(official_moves[TAKE_THREE])
        self.assertFalse(official_moves[60:80].any())
        self.assertFalse(legacy_moves[TAKE_THREE])
        self.assertTrue(legacy_moves[RETURN_ONE_WHITE])

    def test_per_player_profile_rotates_with_canonical_players(self):
        self.board.set_token_rules([False, True])
        self.board.swap_players(1)
        self.assertEqual([True, False], self.board.legacy_token_rules.tolist())
        self.board.swap_players(1)
        self.assertEqual([False, True], self.board.legacy_token_rules.tolist())

    def test_per_player_profile_requires_one_flag_per_seat(self):
        with self.assertRaises(ValueError):
            self.board.set_token_rules([True])

    def test_split_reserve_only_caps_legacy_seat(self):
        self.board.set_token_rules([False, True])
        self.set_inventory([2, 2, 2, 2, 2, 0])
        self.board.players_gems[1] = self.board.players_gems[0]
        initial_gold = int(self.board.bank[0, idx_gold])

        self.assertEqual(0, self.board.make_move(12, 0, deterministic=True))
        self.assertEqual(11, int(self.board.players_gems[0].sum()))
        self.assertEqual(initial_gold - 1, int(self.board.bank[0, idx_gold]))

        self.board.bank[0, idx_gold] = initial_gold
        self.assertEqual(0, int(self.board.players_gems[1, idx_gold]))
        self.board._reserve(1, 1, deterministic=True)
        self.assertEqual(10, int(self.board.players_gems[1].sum()))
        self.assertEqual(initial_gold, int(self.board.bank[0, idx_gold]))


class MixedRulesMCTSTests(unittest.IsolatedAsyncioTestCase):
    def _transition(self, board, action, profile):
        valid = np.zeros(81, dtype=np.bool_)
        valid[action] = True
        policy = np.zeros(81, dtype=np.float64)
        policy[action] = 1.0
        qsa = np.full(81, -42.0, dtype=np.float64)
        nsa = np.zeros(81, dtype=np.int64)
        return get_next_best_action_and_canonical_state(
            np.zeros(2), valid, policy, 0, qsa, nsa, 0.0,
            1.0, board, board.get_state(), False, 0, 0.1, profile,
        )

    def test_turn_change_rotates_split_profile_for_next_canonical_player(self):
        board = Board(2)
        board.set_token_rules([False, True])
        action, _, next_player, next_profile = self._transition(
            board, 80, (False, True)
        )
        self.assertEqual(80, action)
        self.assertEqual(1, next_player)
        self.assertEqual((True, False), next_profile)

    def test_official_overflow_keeps_player_and_profile_during_search(self):
        board = Board(2)
        board.set_token_rules([False, True])
        board.players_gems[0] = np.array([2, 2, 2, 2, 1, 0, 0], dtype=np.int8)
        board.bank[0, :5] = board.num_gems_in_play - board.players_gems[0, :5]
        action, next_state, next_player, next_profile = self._transition(
            board, TAKE_THREE, (False, True)
        )
        self.assertEqual(TAKE_THREE, action)
        self.assertEqual(0, next_player)
        self.assertEqual((False, True), next_profile)
        self.assertEqual(12, int(next_state[32 + board.num_players].sum()))

    async def test_mcts_runs_with_split_profile_and_contextual_cache_keys(self):
        import SplendorGame_2pl

        class Prediction:
            def to_py(self):
                return {
                    "pi": np.zeros(81, dtype=np.float32).tolist(),
                    "v": [0.0, 0.0],
                }

        async def predict(_board, _valid):
            return Prediction()

        old_js = sys.modules.get("js")
        sys.modules["js"] = SimpleNamespace(predict=predict)
        try:
            game = SplendorGame_2pl.SplendorGame()
            game.board.set_token_rules([False, True])
            args = SimpleNamespace(
                numMCTSSims=3,
                prob_fullMCTS=1.0,
                ratio_fullMCTS=1,
                forced_playouts=False,
                no_mem_optim=True,
                cpuct=1.0,
                fpu=0.1,
            )
            mcts = MCTS(game, None, args)
            canonical = game.getCanonicalForm(game.getInitBoard(), 0)
            probabilities, _, _ = await mcts.getActionProb(canonical, temp=0)
            self.assertAlmostEqual(1.0, float(sum(probabilities)))
            self.assertEqual(1, sum(1 for probability in probabilities if probability == 1))
            self.assertEqual([False, True], game.board.legacy_token_rules.tolist())
            self.assertTrue(mcts.nodes_data)
            self.assertTrue(all(b"|token-rules|" in key for key in mcts.nodes_data))
        finally:
            if old_js is None:
                sys.modules.pop("js", None)
            else:
                sys.modules["js"] = old_js

class OverflowProxyTests(unittest.TestCase):
    def setUp(self):
        import SplendorGame_2pl

        sys.modules["SplendorGame"] = SplendorGame_2pl
        import proxy

        self.proxy = proxy
        self.proxy.g = SplendorGame_2pl.SplendorGame()
        self.proxy.board = self.proxy.g.getInitBoard()
        self.proxy.player = 0
        self.proxy.history = []
        self.proxy.edit_mode = 0
        self.proxy.action_sequence = 0
        self.proxy.action_event = None
        self.proxy.match_nonce = 1
        self.proxy.token_rules_mode = "official"
        self.proxy.legacy_token_profile = [False, False]
        self.proxy.legacy_token_rules = False
        self.proxy.g.board.set_token_rules([False, False])
        self.proxy.mcts = SimpleNamespace(nodes_data={})
        self.proxy.reset_selection()

    def test_render_state_exposes_forced_options_and_gold_mapping(self):
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([2, 2, 2, 2, 2, 1, 0], dtype=np.int8)
        game_board.bank[0, :5] = game_board.num_gems_in_play - game_board.players_gems[0, :5]
        game_board.bank[0, idx_gold] = 5 - game_board.players_gems[0, idx_gold]
        self.proxy.board = game_board.get_state()

        state = json.loads(self.proxy.get_render_state())
        self.assertEqual(1, state["extra"]["overflow_count"])
        self.assertEqual([], state["extra"]["take_options"])
        self.assertIn([5], state["extra"]["return_options"])

        self.proxy.click_item("gem", 0)
        self.assertEqual("none", self.proxy.sel_type)
        self.proxy.click_item("gemback", 5)
        self.assertEqual("gemback", self.proxy.sel_type)
        self.assertEqual([5], self.proxy.sel_items)
        self.assertEqual(80, self.proxy._get_move_index())
        self.assertTrue(self.proxy._is_selection_valid())

    def test_single_forced_return_can_be_deselected(self):
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([3, 2, 2, 2, 2, 0, 0], dtype=np.int8)
        game_board.bank[0, :5] = game_board.num_gems_in_play - game_board.players_gems[0, :5]
        self.proxy.board = game_board.get_state()

        self.proxy.click_item("gemback", 0)
        self.assertEqual("gemback", self.proxy.sel_type)
        self.assertEqual([0], self.proxy.sel_items)

        self.proxy.click_item("gemback", 0)
        self.assertEqual("none", self.proxy.sel_type)
        self.assertEqual([], self.proxy.sel_items)

    def test_action_80_history_uses_persisted_pre_action_state(self):
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([2, 2, 2, 2, 2, 1, 0], dtype=np.int8)
        overflow_state = np.copy(game_board.get_state())
        self.proxy.history = [[0, overflow_state, 80]]
        self.proxy.action_event = None
        self.assertEqual(["gemback", [5]], self.proxy._get_last_action_details())

        game_board.players_gems[0] = 0
        normal_state = np.copy(game_board.get_state())
        self.proxy.history = [[0, normal_state, 80]]
        self.proxy.action_event = {"type": "return"}
        self.assertEqual(["pass", []], self.proxy._get_last_action_details())

    def test_legacy_mode_is_persisted_and_clears_mcts_cache(self):
        self.proxy.mcts.nodes_data["stale"] = object()
        state = json.loads(self.proxy.set_token_rules("legacy"))
        self.assertTrue(state["extra"]["legacy_token_rules"])
        self.assertTrue(self.proxy.g.board.legacy_token_rules.all())
        self.assertEqual({}, self.proxy.mcts.nodes_data)

        saved = json.loads(self.proxy.export_game_state())
        self.assertTrue(saved["legacy_token_rules"])
        self.proxy.set_token_rules("official")
        self.proxy.mcts.nodes_data["stale-after-switch"] = object()
        self.proxy.restore_game_state(json.dumps(saved))
        self.assertTrue(self.proxy.legacy_token_rules)
        self.assertTrue(self.proxy.g.board.legacy_token_rules.all())
        self.assertEqual({}, self.proxy.mcts.nodes_data)

        # Historical saves only carried the all-player boolean.
        saved.pop("token_rules_mode")
        saved.pop("legacy_token_profile")
        saved["legacy_token_rules"] = False
        self.proxy.restore_game_state(json.dumps(saved))
        self.assertFalse(self.proxy.legacy_token_rules)
        self.assertFalse(self.proxy.g.board.legacy_token_rules.any())

    def test_legacy_voluntary_return_is_clickable_and_advances_turn(self):
        self.proxy.set_token_rules(True)
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([2, 1, 0, 0, 0, 0, 0], dtype=np.int8)
        game_board.bank[0, :5] = game_board.num_gems_in_play - game_board.players_gems[0, :5]
        self.proxy.board = game_board.get_state()

        state = json.loads(self.proxy.get_render_state())
        self.assertEqual(0, state["extra"]["overflow_count"])
        self.assertIn([0], state["extra"]["return_options"])
        self.proxy.click_item("gemback", 0)
        self.assertEqual(RETURN_ONE_WHITE, self.proxy._get_move_index())
        self.assertTrue(self.proxy._is_selection_valid())
        self.proxy.confirm_action()
        self.assertEqual(1, self.proxy.player)
        self.assertEqual(1, int(self.proxy.g.board.players_gems[0, 0]))

    def test_cannot_enable_legacy_during_unresolved_overflow(self):
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([3, 2, 2, 2, 2, 0, 0], dtype=np.int8)
        self.proxy.board = game_board.get_state()

        state = json.loads(self.proxy.set_token_rules(True))
        self.assertFalse(state["extra"]["legacy_token_rules"])
        self.assertFalse(self.proxy.g.board.legacy_token_rules.any())


    def test_split_mode_is_persisted_with_per_seat_profile(self):
        self.proxy.mcts.nodes_data["stale"] = object()
        state = json.loads(self.proxy.set_token_rules("split", [False, True]))

        self.assertEqual("split", state["extra"]["token_rules_mode"])
        self.assertEqual([False, True], state["extra"]["legacy_token_profile"])
        self.assertFalse(state["extra"]["current_player_legacy"])
        self.assertEqual([False, True], self.proxy.g.board.legacy_token_rules.tolist())
        self.assertEqual({}, self.proxy.mcts.nodes_data)

        saved = self.proxy.export_game_state()
        self.proxy.set_token_rules("official")
        restored = json.loads(self.proxy.restore_game_state(saved))
        self.assertEqual("split", restored["extra"]["token_rules_mode"])
        self.assertEqual([False, True], restored["extra"]["legacy_token_profile"])
        self.assertEqual([False, True], self.proxy.g.board.legacy_token_rules.tolist())

    def test_split_mode_rejects_malformed_profiles_without_mutating_state(self):
        before = json.loads(self.proxy.get_render_state())
        after = json.loads(self.proxy.set_token_rules("split", [True]))
        self.assertEqual(before["extra"]["token_rules_mode"], after["extra"]["token_rules_mode"])
        self.assertEqual(before["extra"]["legacy_token_profile"], after["extra"]["legacy_token_profile"])

    def test_split_mode_exposes_legacy_returns_only_on_ai_seat(self):
        self.proxy.set_token_rules("split", [False, True])
        game_board = self.proxy.g.board
        game_board.players_gems[0] = np.array([2, 1, 0, 0, 0, 0, 0], dtype=np.int8)
        game_board.players_gems[1] = np.array([2, 1, 0, 0, 0, 0, 0], dtype=np.int8)
        self.proxy.board = game_board.get_state()

        human_state = json.loads(self.proxy.get_render_state())
        self.assertFalse(human_state["extra"]["current_player_legacy"])
        self.assertEqual([], human_state["extra"]["return_options"])

        self.proxy.player = 1
        ai_state = json.loads(self.proxy.get_render_state())
        self.assertTrue(ai_state["extra"]["current_player_legacy"])
        self.assertIn([0], ai_state["extra"]["return_options"])


if __name__ == "__main__":
    unittest.main()
