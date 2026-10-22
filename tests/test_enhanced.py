"""Synthetic invariants only; product experiments use validated historical CSVs."""
from copy import deepcopy
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression

from worlds_predictor.enhanced import load_enhanced, predict_enhanced
from worlds_predictor.enhanced_features import (
    DecayedOutcomeCounter, build_enhanced_table, enhanced_columns, enhanced_features_for_game,
)
from worlds_predictor.enhanced_training import choose_candidate
from worlds_predictor.features import build_feature_table
from worlds_predictor.model import ModelUnavailableError, _logits, sha256
from test_features import unit_game
from test_model import payload_for, synthetic_games


def test_enhanced_preserves_original_features_exactly():
    games = pd.DataFrame([unit_game(str(i), pd.Timestamp("2024-01-01T12:00:00Z") + pd.Timedelta(days=i), i % 2) for i in range(8)])
    original = build_feature_table(games)
    enhanced = build_enhanced_table(games)
    pd.testing.assert_frame_equal(original, enhanced[original.columns])
    numeric, categorical = enhanced_columns()
    assert len(numeric) + len(categorical) == len(set(numeric + categorical))
    assert np.isfinite(enhanced[numeric]).all().all()


def test_enhanced_training_inference_parity_with_equal_and_late_results():
    games = pd.DataFrame([unit_game("a"), unit_game("b", "2024-01-02T12:00:00Z", 0),
                          unit_game("c", "2024-01-02T12:00:00Z", 1), unit_game("d", "2024-01-03T12:00:00Z", 0)])
    frame = build_enhanced_table(games).set_index("game_id")
    for game in games.to_dict("records"):
        feature, coverage = enhanced_features_for_game(games, game, game["date"])
        for key, value in feature.items():
            assert frame.loc[game["game_id"], key] == value
        if coverage["latest_history_available_at"]:
            assert pd.Timestamp(coverage["latest_history_available_at"]) < game["date"]


def test_enhanced_future_and_target_result_invariance():
    games = [unit_game("a"), unit_game("target", "2024-01-03T12:00:00Z", 0), unit_game("future", "2024-01-05T12:00:00Z", 1)]
    target = games[1]
    before, cov = enhanced_features_for_game(pd.DataFrame(games), target, target["date"])
    altered = deepcopy(games)
    altered[1].update(blue_win=1, kills=9999, gold=123456, damage=999999)
    altered[2].update(blue_win=0, blue_top_champion="future_changed", blue_team_id="changed")
    after, later_cov = enhanced_features_for_game(pd.DataFrame(altered), altered[1], target["date"])
    assert before == after and cov == later_cov
    assert before["blue_roster_games"] == 1
    assert before["blue_mid_jungle_games"] == 1


def test_as_of_and_target_game_exclusion():
    target = unit_game("target", "2024-01-05T12:00:00Z")
    games = [unit_game("known"), unit_game("equal", "2024-01-02T12:00:00Z", available_at=target["date"]),
             unit_game("target", "2024-01-01T12:00:00Z"), unit_game("later", "2024-01-08T12:00:00Z")]
    features, coverage = enhanced_features_for_game(pd.DataFrame(games), target, target["date"])
    assert features["historical_game_count"] == 1
    assert features["blue_bot_support_games"] == 1
    assert coverage["history_games"] == 1


def test_specific_duos_count_once_and_new_patch_is_unknown():
    games = pd.DataFrame([unit_game("a"), unit_game("b", "2024-01-02T12:00:00Z", 0)])
    target = unit_game("c", "2024-01-04T12:00:00Z", patch="new-patch")
    row, coverage = enhanced_features_for_game(games, target, target["date"])
    assert row["blue_mid_jungle_games"] == 2
    assert row["blue_mid_jungle_recent_games"] == 2
    assert row["blue_mid_jungle_patch_games"] == 0
    assert row["blue_top_player_champion_patch_games"] == 0
    assert coverage["same_roster_games"] == {"blue": 2, "red": 2}
    target["blue_top_player_id"] = "new-pro-player"
    row, coverage = enhanced_features_for_game(games, target, target["date"])
    assert row["blue_roster_games"] == 0
    assert row["blue_mid_jungle_players_games"] == 2


def test_decayed_counts_follow_elapsed_days_and_shrink():
    counter = DecayedOutcomeCounter(strength=10)
    t = pd.Timestamp("2024-01-01", tz="UTC")
    counter.update("a", 1, t)
    before = counter.get("a", t)
    after = counter.get("a", t + pd.Timedelta(days=90))
    assert before[1] == 1 and after[1] == pytest.approx(.5)
    assert .5 < after[0] < before[0]
    with pytest.raises(ValueError, match="availability"):
        counter.update("a", 0, t - pd.Timedelta(days=1))


def test_validation_gate_never_uses_test_scores():
    base = {"validation_raw": {"roc_auc": .70, "log_loss": .63}}
    candidates = {
        "good": {"validation_raw": {"roc_auc": .71, "log_loss": .635}, "calibrator": {"coefficient": 1.0}, "test_calibrated": {"roc_auc": .40}},
        "test_only": {"validation_raw": {"roc_auc": .69, "log_loss": .61}, "calibrator": {"coefficient": 1.0}, "test_calibrated": {"roc_auc": .99}},
        "bad_loss": {"validation_raw": {"roc_auc": .73, "log_loss": .65}, "calibrator": {"coefficient": 1.0}},
        "reversed": {"validation_raw": {"roc_auc": .75, "log_loss": .62}, "calibrator": {"coefficient": -1.0}},
    }
    assert choose_candidate(base, candidates, .01) == "good"
    del candidates["good"]
    assert choose_candidate(base, candidates, .01) is None


def test_missing_enhanced_never_returns_probability(tmp_path):
    with pytest.raises(ModelUnavailableError, match="unavailable"):
        load_enhanced(tmp_path)


def test_enhanced_real_inference_fixture_and_integrity(tmp_path):
    # Actual estimator executed on synthetic fixtures under pytest tempdir only.
    from worlds_predictor import features, enhanced_features
    games = synthetic_games()
    frame = build_enhanced_table(games)
    numeric, cats = enhanced_columns()
    cols = numeric + cats
    estimator = CatBoostClassifier(iterations=8, depth=3, thread_count=1, random_seed=7, cat_features=cats, verbose=False, allow_writing_files=False)
    estimator.fit(frame.iloc[:40][cols], frame.iloc[:40].blue_win)
    calibrator = LogisticRegression().fit(_logits(estimator.predict_proba(frame.iloc[40:55][cols])[:, 1]), frame.iloc[40:55].blue_win)
    # Monotonicity is an explicit inference gate; set a monotonic fixture only.
    calibrator.coef_[0, 0] = abs(calibrator.coef_[0, 0]) + .1
    artifact = {"estimator": estimator, "calibrator": calibrator, "columns": cols, "categorical": cats}
    artifact_path = tmp_path / "selected_model.joblib"
    joblib.dump(artifact, artifact_path)
    metadata = {"status": "trained", "enhanced_available": True, "artifact_sha256": sha256(artifact_path),
        "feature_code_sha256": {"features.py": sha256(Path(features.__file__)), "enhanced_features.py": sha256(Path(enhanced_features.__file__))},
        "label_cutoff": games.iloc[54].available_at.isoformat(), "model_version": "SYNTHETIC_TEST_ONLY"}
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    games_path = tmp_path / "synthetic.parquet"
    games.to_parquet(games_path)
    payload = payload_for(games.iloc[70].to_dict())
    result = predict_enhanced(payload, games_path, tmp_path)
    assert 0 < result["calibrated_probability"] < 1
    assert result["reconstruction_error"] < 1e-8
    assert result["coverage"]["history_games"] == 70
    games.loc[games.date >= pd.Timestamp(payload["as_of"]), "blue_win"] ^= 1
    games.to_parquet(games_path)
    assert predict_enhanced(payload, games_path, tmp_path) == result
    old = dict(payload, as_of=metadata["label_cutoff"])
    with pytest.raises(ValueError, match="label cutoff"):
        predict_enhanced(old, games_path, tmp_path)
    metadata["artifact_sha256"] = "tampered"
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(ModelUnavailableError, match="integrity mismatch"):
        predict_enhanced(payload, games_path, tmp_path)


def test_invalid_or_duplicate_enhanced_history_rejected():
    with pytest.raises(ValueError, match="unique game_id"):
        build_enhanced_table(pd.DataFrame([unit_game(), unit_game()]))
    with pytest.raises(ValueError, match="binary"):
        build_enhanced_table(pd.DataFrame([unit_game(win=3)]))
