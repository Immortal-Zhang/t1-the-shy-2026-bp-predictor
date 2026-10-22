"""Synthetic fixtures test invariants only; never used for model evaluation."""

import copy

import numpy as np
import pandas as pd
import pytest

from worlds_predictor.features import (
    ROLES,
    build_feature_table,
    feature_columns,
    features_for_game,
)


def unit_game(game_id="fixture-1", date="2024-01-01T12:00:00Z", win=1, **changes):
    stamp = pd.Timestamp(date)
    game = {
        "game_id": game_id,
        "date": stamp,
        "available_at": stamp + pd.Timedelta(hours=1),
        "league": "SYNTHETIC_UNIT_TEST",
        "patch": "test.1",
        "blue_team_id": "fixture-blue",
        "red_team_id": "fixture-red",
        "blue_win": win,
        "first_pick_side": "unknown",
    }
    for side in ("blue", "red"):
        for role in ROLES:
            game[f"{side}_{role}_player_id"] = f"fixture-{side}-{role}"
            game[f"{side}_{role}_champion"] = f"fixture-champion-{side}-{role}"
        for i in range(1, 6):
            game[f"{side}_ban{i}"] = None
    game.update(changes)
    return game


def test_nested_feature_sets_and_allowlist():
    a, b, c = [set(sum(feature_columns(level), [])) for level in ("A", "B", "C")]
    assert a < b < c
    assert not c.intersection({"blue_win", "date", "game_id", "available_at", "gold", "kills", "kda", "result"})
    assert "patch" not in b and "patch" in c
    assert "blue_top_champion" not in b and "blue_top_champion" in c
    for level in "ABC":
        numeric, categorical = feature_columns(level)
        assert len(numeric + categorical) == len(set(numeric + categorical))
    with pytest.raises(ValueError):
        feature_columns("D")


def test_current_outcome_and_postgame_stats_do_not_change_features():
    history = pd.DataFrame([unit_game()])
    target = unit_game("fixture-2", "2024-01-03T12:00:00Z")
    before, _ = features_for_game(history, target, target["date"])
    target.update(blue_win=0, gold=999999, kills=100, blue_gold_diff_15=30000, result=0)
    after, _ = features_for_game(history, target, target["date"])
    assert before == after


def test_future_games_cannot_change_past_features():
    games = [unit_game(f"fixture-{i}", f"2024-01-{i:02d}T12:00:00Z", i % 2) for i in range(1, 6)]
    original = build_feature_table(pd.DataFrame(games))
    changed = copy.deepcopy(games)
    changed[-1].update(blue_win=1 - changed[-1]["blue_win"], blue_team_id="unseen-future-team")
    changed[-1]["blue_top_player_id"] = "unseen-future-player"
    changed[-1]["blue_top_champion"] = "unseen-future-champion"
    revised = build_feature_table(pd.DataFrame(changed))
    pd.testing.assert_frame_equal(original.iloc[:-1], revised.iloc[:-1])
    target = games[3]
    feat1, cover1 = features_for_game(pd.DataFrame(games), target, target["date"])
    feat2, cover2 = features_for_game(pd.DataFrame(changed), target, target["date"])
    assert feat1 == feat2 and cover1 == cover2


def test_as_of_excludes_equal_timestamp_and_unavailable_labels():
    target = unit_game("target", "2024-01-05T12:00:00Z")
    older = unit_game("known", "2024-01-01T12:00:00Z")
    equal_available = unit_game("equal-available", "2024-01-02T12:00:00Z", available_at=target["date"])
    late = unit_game("late-result", "2024-01-03T12:00:00Z", available_at=target["date"] + pd.Timedelta(hours=1))
    future = unit_game("future", "2024-01-08T12:00:00Z")
    data = pd.DataFrame([target, older, equal_available, late, future])
    features, coverage = features_for_game(data, target, target["date"])
    assert features["historical_game_count"] == 1
    assert coverage["history_games"] == 1
    assert pd.Timestamp(coverage["latest_history_available_at"]) < target["date"]
    labelled = build_feature_table(data, as_of=target["date"])
    assert labelled["game_id"].tolist() == ["known"]
    # Requesting after the target does not allow its contemporaneous/future data.
    later_features, _ = features_for_game(data, target, "2025-01-01T00:00:00Z")
    assert later_features == features


def test_identical_timestamp_rows_are_atomic_and_order_invariant():
    first = unit_game("same-a")
    second = unit_game("same-b", win=0)
    third = unit_game("later", "2024-01-03T12:00:00Z")
    frame = pd.DataFrame([first, second, third])
    original = build_feature_table(frame)
    shuffled = build_feature_table(frame.sample(frac=1, random_state=51))
    pd.testing.assert_frame_equal(original, shuffled)
    assert original.iloc[:2]["historical_game_count"].tolist() == [0.0, 0.0]
    assert original.iloc[2]["historical_game_count"] == 2


def test_training_and_inference_feature_parity_at_every_game():
    games = pd.DataFrame([
        unit_game("a", "2024-01-01T12:00:00Z"),
        unit_game("b", "2024-01-02T12:00:00Z", 0),
        unit_game("c", "2024-01-02T12:00:00Z", 1),
        unit_game("d", "2024-01-03T12:00:00Z", 0),
    ])
    table = build_feature_table(games).set_index("game_id")
    for game in games.to_dict("records"):
        features, _ = features_for_game(games, game, game["date"])
        for column, value in features.items():
            assert table.loc[game["game_id"], column] == value


def test_target_id_excluded_even_if_mislabeled_earlier():
    historical_target = unit_game("target", "2024-01-01T12:00:00Z")
    target = unit_game("target", "2024-01-03T12:00:00Z")
    features, coverage = features_for_game(pd.DataFrame([historical_target]), target, target["date"])
    assert features["historical_game_count"] == 0
    assert coverage["history_games"] == 0


def test_smoothed_statistics_derive_from_previous_results():
    previous = unit_game()
    target = unit_game("next", "2024-01-03T12:00:00Z")
    features, coverage = features_for_game(pd.DataFrame([previous]), target, target["date"])
    assert features["blue_team_win_rate"] == pytest.approx(6 / 11)
    assert features["red_team_win_rate"] == pytest.approx(5 / 11)
    assert features["blue_top_player_champion_win_rate"] == pytest.approx(6 / 11)
    assert features["blue_top_matchup_win_rate"] == pytest.approx(11 / 21)
    assert features["red_top_matchup_win_rate"] == pytest.approx(10 / 21)
    assert features["blue_synergy_mean_win_rate"] == pytest.approx(16 / 31)
    assert features["blue_top_patch_champion_games"] == 1
    assert features["first_pick_side"] == "__UNKNOWN__"
    assert coverage["first_pick_side_observed"] is False
    assert coverage["missing_ban_slots"] == 10


def test_unseen_patch_and_player_champion_are_flagged_not_fabricated():
    target = unit_game("next", "2024-01-03T12:00:00Z", patch="unseen-patch")
    target["blue_top_player_id"] = "unseen-pro-id"
    target["blue_top_champion"] = "unseen-champion"
    features, coverage = features_for_game(pd.DataFrame([unit_game()]), target, target["date"])
    assert coverage["patch_history_games"] == 0
    assert coverage["unknown_players_in_role"] == ["unseen-pro-id"]
    assert coverage["unknown_champions_in_role"] == ["unseen-champion"]
    assert features["blue_top_player_champion_games"] == 0
    assert features["blue_top_player_champion_win_rate"] == 0.5
    assert features["blue_top_patch_champion_games"] == 0


@pytest.mark.parametrize("missing", [None, "", "unknown", "Unknown", "__UNKNOWN__"])
def test_missing_ban_sentinels_have_identical_training_inference_semantics(missing):
    target = unit_game("next", "2024-01-03T12:00:00Z")
    for side in ("blue", "red"):
        for i in range(1, 6):
            target[f"{side}_ban{i}"] = missing
    features, coverage = features_for_game(pd.DataFrame([unit_game()]), target, target["date"])
    assert coverage["missing_ban_slots"] == 10
    assert features["blue_known_bans"] == 0
    assert features["red_known_bans"] == 0
    assert features["blue_ban1"] == "__UNKNOWN__"


def test_recent_form_window_and_player_team_change():
    games = [unit_game(f"fixture-{i}", pd.Timestamp("2024-01-01T12:00:00Z") + pd.Timedelta(days=i), int(i > 0)) for i in range(21)]
    target = unit_game("next", "2024-02-01T12:00:00Z", blue_team_id="new-organization")
    features, coverage = features_for_game(pd.DataFrame(games), target, target["date"])
    assert features["blue_team_games"] == 0
    assert features["blue_top_player_games"] == 21
    assert features["blue_top_player_recent_games"] == 20
    assert features["blue_top_player_recent_win_rate"] == pytest.approx(25 / 30)
    assert coverage["unknown_teams"] == ["new-organization"]


@pytest.mark.parametrize("change", [
    {"available_at": "2023-01-01T00:00:00Z"},
    {"available_at": None},
    {"blue_win": 3},
])
def test_unsafe_history_rejected(change):
    with pytest.raises(ValueError):
        build_feature_table(pd.DataFrame([unit_game(**change)]))


def test_duplicate_game_ids_rejected():
    with pytest.raises(ValueError, match="unique game_id"):
        build_feature_table(pd.DataFrame([unit_game(), unit_game()]))


def test_empty_history_produces_complete_finite_vector_with_zero_coverage():
    empty = pd.DataFrame(columns=["game_id", "date", "available_at", "blue_win"])
    features, coverage = features_for_game(empty, unit_game(), "2024-01-01T00:00:00Z")
    numeric, categorical = feature_columns("C")
    assert set(features) == set(numeric + categorical)
    assert np.isfinite([features[name] for name in numeric]).all()
    assert coverage["history_games"] == 0
    assert len(coverage["unknown_players_in_role"]) == 10
    assert build_feature_table(empty).empty
