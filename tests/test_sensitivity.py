"""Sensitivity guardrails only; artificial fixtures are never evaluation data."""

import numpy as np
import pandas as pd
import pytest

from worlds_predictor.sensitivity import aligned_pooled_predictions, cohort_eligibility


def fixture_frame(n=4):
    return pd.DataFrame({"game_id": [f"fixture-{i}" for i in range(n)],
                         "date": pd.date_range("2024-01-01", periods=n, tz="UTC"),
                         "available_at": pd.date_range("2024-01-02", periods=n, tz="UTC"),
                         "blue_win": [i % 2 for i in range(n)], "league": "LCK"})


def test_empty_league_calibration_blocks_calibrated_protocol_only():
    parts = {"train": fixture_frame(100), "validation": fixture_frame(),
             "calibration": fixture_frame(0), "test": fixture_frame()}
    summary, blockers = cohort_eligibility(parts, calibrated=True)
    assert summary["calibration"]["n"] == 0
    assert any("calibration" in blocker for blocker in blockers)
    _, raw_blockers = cohort_eligibility(parts, calibrated=False)
    assert raw_blockers == []


def test_comparison_aligns_same_games_and_selects_matching_raw_scale():
    test = fixture_frame()
    pooled = test.assign(p_blue_raw=[.1, .9, .2, .8], p_blue=[.3, .7, .4, .6]).iloc[::-1]
    np.testing.assert_array_equal(aligned_pooled_predictions(test, pooled, "LCK", False), [.1, .9, .2, .8])
    np.testing.assert_array_equal(aligned_pooled_predictions(test, pooled, "LCK", True), [.3, .7, .4, .6])


def test_missing_game_does_not_silently_shrink_comparison():
    test = fixture_frame()
    pooled = test.assign(p_blue_raw=.5, p_blue=.5).iloc[:-1]
    with pytest.raises(ValueError, match="ID sets differ"):
        aligned_pooled_predictions(test, pooled, "LCK", False)


def test_mismatched_ground_truth_and_duplicate_ids_rejected():
    test = fixture_frame()
    pooled = test.assign(p_blue_raw=.5, p_blue=.5)
    pooled.loc[0, "blue_win"] = 1
    with pytest.raises(ValueError, match="labels disagree"):
        aligned_pooled_predictions(test, pooled, "LCK", False)
    pooled.loc[0, "blue_win"] = 0
    with pytest.raises(ValueError, match="Duplicate game IDs"):
        aligned_pooled_predictions(test, pd.concat([pooled, pooled.iloc[[0]]]), "LCK", False)
