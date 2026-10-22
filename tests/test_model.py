"""Actual estimator/artifact checks on explicit synthetic unit-test data only.

No product model, report, evaluation result or real-data claim is produced here.
All fitted fixtures and predictions live only under pytest temporary directories.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from worlds_predictor import features as feature_module
from worlds_predictor.features import ROLES, build_feature_table, feature_columns
from worlds_predictor.model import (
    ModelUnavailableError,
    _fit,
    _logits,
    make_estimator,
    predict,
    request_to_game,
    sha256,
)
from worlds_predictor.schemas import PredictionRequest


def synthetic_games():
    rows = []
    for number in range(80):
        date = pd.Timestamp("2024-01-01T12:00:00Z") + pd.Timedelta(days=number)
        game = {"game_id": f"synthetic-unit-game-{number}", "date": date,
                "available_at": date + pd.Timedelta(hours=1), "blue_win": number % 2,
                "league": "SYNTHETIC_UNIT_TEST_ONLY", "patch": "24.1", "first_pick_side": "blue"}
        for side in ("blue", "red"):
            game[f"{side}_team_id"] = f"synthetic-{side}-team"
            game[f"{side}_team_name"] = f"synthetic-{side}-team"
            for role in ROLES:
                game[f"{side}_{role}_player_id"] = f"synthetic-{side}-{role}-pro"
                game[f"{side}_{role}_champion"] = f"synthetic-{side}-{role}-champion"
            for ban in range(1, 6):
                game[f"{side}_ban{ban}"] = None
        rows.append(game)
    return pd.DataFrame(rows)


def payload_for(game):
    request = {"game_id": game["game_id"], "as_of": game["date"].isoformat(),
               "scheduled_start": game["date"].isoformat(), "league": game["league"],
               "patch": game["patch"], "first_pick_side": game["first_pick_side"]}
    for side in ("blue", "red"):
        request[side] = {"team_id": game[f"{side}_team_id"], "players": [
            {"role": role, "player_id": game[f"{side}_{role}_player_id"],
             "champion": game[f"{side}_{role}_champion"]} for role in ROLES
        ], "bans": []}
    return PredictionRequest.model_validate(request).model_dump(mode="json")


@pytest.fixture(scope="module", params=["logistic", "catboost"])
def fitted(request):
    games = synthetic_games()
    table = build_feature_table(games)
    numeric, categorical = feature_columns("C")
    columns = numeric + categorical
    config = {"seed": 7, "iterations": 8, "depth": 3, "learning_rate": .1,
              "l2_leaf_reg": 5, "thread_count": 1}
    estimator = make_estimator(request.param, numeric, categorical, config)
    _fit(estimator, request.param, table.iloc[:40][columns], table.iloc[:40].blue_win, np.ones(40))
    calibrator = LogisticRegression().fit(_logits(estimator.predict_proba(table.iloc[40:55][columns])[:, 1]), table.iloc[40:55].blue_win)
    artifact = {"estimator": estimator, "calibrator": calibrator, "columns": columns,
                "numeric": numeric, "categorical": categorical, "kind": request.param, "level": "C"}
    return {"games": games, "table": table, "artifact": artifact, "kind": request.param}


def save_fixture(tmp_path, fitted):
    model_dir = tmp_path / "synthetic-model-only"
    model_dir.mkdir()
    artifact_path = model_dir / "selected_model.joblib"
    joblib.dump(fitted["artifact"], artifact_path)
    games_path = tmp_path / "synthetic-unit-history.parquet"
    fitted["games"].to_parquet(games_path)
    metadata = {"status": "trained", "artifact_sha256": sha256(artifact_path),
                "feature_code_sha256": sha256(Path(feature_module.__file__)),
                "label_cutoff": fitted["games"].iloc[54].available_at.isoformat(),
                "model_version": "SYNTHETIC_UNIT_TEST_ONLY/" + fitted["kind"],
                "selected_model": "test-only", "splits": {"test_fixture_only": True},
                "identity_limitation": "Synthetic fixture, not a real prediction or evaluation"}
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    payload = payload_for(fitted["games"].iloc[70].to_dict())
    return model_dir, games_path, payload, metadata


def test_actual_estimators_fit_and_handle_unseen_categories(fitted):
    artifact = fitted["artifact"]
    x = fitted["table"].iloc[[70]][artifact["columns"]].copy()
    x["blue_top_player_id"] = "unseen-unit-pro"
    x["blue_top_champion"] = "unseen-unit-champion"
    x["patch"] = "99.1"
    probabilities = artifact["estimator"].predict_proba(x)
    assert probabilities.shape == (1, 2)
    assert np.isfinite(probabilities).all()
    assert np.logical_and(probabilities >= 0, probabilities <= 1).all()
    assert probabilities.sum() == pytest.approx(1)


def test_prediction_loads_fitted_artifact_and_reports_strict_coverage(tmp_path, fitted):
    model_dir, games_path, payload, metadata = save_fixture(tmp_path, fitted)
    result = predict(payload, model_dir, games_path)
    assert result["model_version"] == metadata["model_version"]
    assert result["blue_win_probability"] + result["red_win_probability"] == pytest.approx(1)
    assert np.isfinite(result["blue_win_probability"])
    assert result["sample_coverage"]["history_games"] == 70
    assert result["sample_coverage"]["missing_ban_slots"] == 10
    assert pd.Timestamp(result["data_cutoff"]) < pd.Timestamp(payload["as_of"])
    assert pd.Timestamp(result["history_result_available_cutoff"]) < pd.Timestamp(payload["as_of"])


def test_future_history_changes_cannot_change_loaded_model_prediction(tmp_path, fitted):
    model_dir, games_path, payload, _ = save_fixture(tmp_path, fitted)
    before = predict(payload, model_dir, games_path)
    altered = fitted["games"].copy()
    future = altered.date >= pd.Timestamp(payload["as_of"])
    altered.loc[future, "blue_win"] = 1 - altered.loc[future, "blue_win"]
    altered.loc[future, "blue_top_champion"] = "perturbed-future-unit-champion"
    altered.to_parquet(games_path)
    after = predict(payload, model_dir, games_path)
    assert before == after


def test_artifact_hash_tampering_fails_before_unpickling(tmp_path, fitted):
    model_dir, games_path, payload, _ = save_fixture(tmp_path, fitted)
    artifact = model_dir / "selected_model.joblib"
    with artifact.open("ab") as file:
        file.write(b"unit-test-corruption")
    with pytest.raises(ModelUnavailableError, match="integrity mismatch"):
        predict(payload, model_dir, games_path)


def test_feature_version_mismatch_requires_retraining(tmp_path, fitted):
    model_dir, games_path, payload, metadata = save_fixture(tmp_path, fitted)
    metadata["feature_code_sha256"] = "incorrect-unit-test-hash"
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(ModelUnavailableError, match="retraining required"):
        predict(payload, model_dir, games_path)


def test_model_trained_with_future_labels_cannot_answer_earlier_as_of(tmp_path, fitted):
    model_dir, games_path, payload, metadata = save_fixture(tmp_path, fitted)
    payload["as_of"] = metadata["label_cutoff"]
    with pytest.raises(ValueError, match="model's label cutoff"):
        predict(payload, model_dir, games_path)


def test_absent_model_never_returns_default_probability(tmp_path):
    payload = payload_for(synthetic_games().iloc[70].to_dict())
    with pytest.raises(ModelUnavailableError, match="No valid trained model"):
        predict(payload, tmp_path / "missing-model", tmp_path / "missing-history.parquet")


def test_request_mapping_keeps_missing_bans_missing():
    payload = payload_for(synthetic_games().iloc[70].to_dict())
    game = request_to_game(payload)
    assert all(game[f"{side}_ban{i}"] is None for side in ("blue", "red") for i in range(1, 6))
    assert game["first_pick_side"] == "blue"
