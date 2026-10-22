"""Real-model integration plus isolated structural/time-boundary checks.

Unit fixtures exercise arithmetic only; product predictions in this module
always come from the saved phase-one models, never hand-crafted probabilities.
"""
from copy import deepcopy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from worlds_predictor.analysis import (
    AnalysisRequest, _sample_status, analyze, historical_analysis, prepare_request,
)
from worlds_predictor.analysis_api import create_analysis_router
from worlds_predictor.features import ROLES
from worlds_predictor.model import ModelUnavailableError

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models/latest"
GAMES = ROOT / "data/processed/games.parquet"


@pytest.fixture
def real_request():
    path = ROOT / "examples/real_match_replay.json"
    if not path.exists():
        pytest.skip("Real source replay is not installed")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def real_analysis():
    if not GAMES.exists() or not (MODELS / "selected_model.joblib").exists() or not (ROOT / "data/catalog/champion-en_US.json").exists():
        pytest.skip("Real model/history/catalog artifacts are not installed")
    payload = json.loads((ROOT / "examples/real_match_replay.json").read_text())
    return analyze(payload, MODELS, GAMES)


def test_real_models_probability_and_comparison(real_analysis):
    result = real_analysis
    before, after = result["comparison"]["pre_bp"], result["comparison"]["post_bp"]
    assert before["model"].endswith("/B_catboost")
    assert after["model"].endswith("/C_catboost_uniform")
    for item in (before, after):
        assert 0 < item["blue_probability"] < 1
        assert item["blue_probability"] + item["red_probability"] == pytest.approx(1)
    assert after["blue_probability"] == result["prediction"]["blue_win_probability"]
    assert result["comparison"]["delta_blue"] == pytest.approx(after["blue_probability"]-before["blue_probability"])
    assert "因果" in result["comparison"]["limitation"]


def test_real_shap_reconstructs_raw_formula(real_analysis):
    shap = real_analysis["explanation"]
    assert shap["method"] == "CatBoost SHAP"
    assert shap["space"] == "raw_log_odds"
    assert shap["base_value"] + sum(item["contribution"] for item in shap["contributions"]) + shap["other_contribution"] == pytest.approx(shap["raw_prediction"], abs=1e-6)
    assert shap["reconstruction_error"] < 1e-6
    assert shap["feature_count"] == 184
    assert "百分点" in shap["notice"]


def test_actual_stats_have_no_fake_zero_sample_rates(real_analysis):
    assert len(real_analysis["players"]) == 10
    assert len(real_analysis["matchups"]) == 5
    assert len(real_analysis["synergies"]) == 20
    for player in real_analysis["players"]:
        assert player["games"] >= player["wins"] >= 0
        if player["games"]:
            assert player["win_rate"] == pytest.approx(player["wins"] / player["games"])
            assert pd.Timestamp(player["last_played"]) < pd.Timestamp(real_analysis["prediction"]["as_of"])
        else:
            assert player["win_rate"] is None
            assert player["recent_win_rate"] is None
            assert player["last_played"] is None
            assert player["sample_status"] == "none"
    for matchup in real_analysis["matchups"]:
        if matchup["games"] == 0:
            assert matchup["blue_win_rate"] is None


def test_real_evaluation_and_no_unverified_strength_scores(real_analysis):
    assert real_analysis["evaluation"]["n"] == 9309
    assert real_analysis["evaluation"]["worlds_target"]["n"] == 22
    assert real_analysis["evaluation"]["accuracy"] == pytest.approx(0.6394886668815125)
    unsupported = real_analysis["supported_analysis"]["early_late_damage_engage_protection_cc"]
    assert unsupported["available"] is False
    assert "strength_score" not in real_analysis


def test_chinese_and_english_normalize_same_request(real_request):
    en = json.loads((ROOT / "data/catalog/champion-en_US.json").read_text())["data"]
    zh = json.loads((ROOT / "data/catalog/champion-zh_CN.json").read_text())["data"]
    by_en = {value["name"]: key for key, value in en.items()}
    translated = deepcopy(real_request)
    for side in ("blue", "red"):
        for player in translated[side]["players"]:
            player["champion"] = zh[by_en[player["champion"]]]["name"]
    first, _ = prepare_request(real_request, GAMES)
    second, _ = prepare_request(translated, GAMES)
    assert first == second


def test_chinese_duplicate_pick_alias_is_rejected(real_request):
    en = json.loads((ROOT / "data/catalog/champion-en_US.json").read_text())["data"]
    zh = json.loads((ROOT / "data/catalog/champion-zh_CN.json").read_text())["data"]
    name = real_request["blue"]["players"][0]["champion"]
    key = next(key for key, value in en.items() if value["name"] == name)
    real_request["red"]["players"][0]["champion"] = zh[key]["name"]
    with pytest.raises(ValueError, match="distinct champion"):
        prepare_request(real_request, GAMES)


def test_unknown_champion_rejected(real_request):
    real_request["blue"]["players"][0]["champion"] = "not-a-real-champion-unit-test"
    with pytest.raises(ValueError):
        prepare_request(real_request, GAMES)


def test_unknown_canonical_player_disclosed_as_zero_history(real_request):
    if not GAMES.is_file():
        pytest.skip("Real historical games are not installed; run the documented data preparation commands")
    from worlds_predictor.data import load_games
    from worlds_predictor.model import request_to_game
    real_request["blue"]["players"][0]["player_id"] = "pro:unseen-test-identity"
    normalized, _ = prepare_request(real_request, GAMES)
    history = load_games(GAMES, as_of=normalized["as_of"])
    players, _, _ = historical_analysis(history, request_to_game(normalized))
    unknown = players[0]
    assert unknown["player_id"] == "pro:unseen-test-identity"
    assert unknown["games"] == 0 and unknown["player_history_games"] == 0
    assert unknown["win_rate"] is None


def test_missing_model_never_returns_probability(tmp_path, real_request):
    with pytest.raises(ModelUnavailableError):
        analyze(real_request, tmp_path, GAMES)


def test_before_training_cutoff_rejected(real_request):
    if not GAMES.is_file() or not (MODELS / "selected_model.joblib").is_file():
        pytest.skip("Real model/history artifacts are not installed; run the documented training commands")
    real_request["as_of"] = real_request["scheduled_start"] = "2025-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="label cutoff"):
        analyze(real_request, MODELS, GAMES)


def test_future_rows_cannot_change_real_analysis(tmp_path, real_request, real_analysis):
    from worlds_predictor.data import load_games
    history = load_games(GAMES)
    future = history.iloc[[0]].copy()
    future["game_id"] = "explicit-future-perturbation-test-only"
    future["date"] = pd.Timestamp("2027-01-01T12:00:00Z")
    future["available_at"] = pd.Timestamp("2027-01-02T00:00:00Z")
    future["blue_win"] = 1-future.blue_win
    augmented = tmp_path / "games.parquet"
    pd.concat([history, future], ignore_index=True).to_parquet(augmented)
    result = analyze(real_request, MODELS, augmented)
    assert result["prediction"]["blue_win_probability"] == real_analysis["prediction"]["blue_win_probability"]
    assert result["comparison"] == real_analysis["comparison"]
    assert result["players"] == real_analysis["players"]
    assert result["matchups"] == real_analysis["matchups"]
    assert result["synergies"] == real_analysis["synergies"]


def test_first_pick_is_separate_and_context_not_model_feature(real_request):
    normalized, validation = prepare_request(dict(real_request, first_pick_side="red", draft_context={"enabled": False, "format": "bo3", "previous_games": []}), GAMES)
    assert normalized["first_pick_side"] == "red"
    assert "draft_context" not in normalized
    assert validation["enabled"] is False


def test_fearless_uses_verified_global_rules(monkeypatch, real_request):
    import worlds_predictor.analysis as module
    from worlds_predictor.catalog import canonical_champion
    monkeypatch.setattr(module, "_catalog_functions", lambda: (canonical_champion, lambda: {"verified": True, "fearless_mode": "global", "source_url": "https://official.example/test-fixture", "applicable_formats": ["bo3", "bo5"]}))
    prior = {f"{side}_champions": [player["champion"] for player in real_request[side]["players"]] for side in ("blue", "red")}
    request = dict(real_request, draft_context={"enabled": True, "format": "bo3", "previous_games": [prior]})
    with pytest.raises(ValueError, match="blocks previously picked"):
        prepare_request(request, GAMES)


def test_unverified_fearless_rejects_instead_of_guessing(monkeypatch, real_request):
    import worlds_predictor.analysis as module
    from worlds_predictor.catalog import canonical_champion
    monkeypatch.setattr(module, "_catalog_functions", lambda: (canonical_champion, lambda: {"verified": False}))
    request = dict(real_request, draft_context={"enabled": True, "format": "bo3", "previous_games": []})
    with pytest.raises(ModelUnavailableError, match="not verified"):
        prepare_request(request, GAMES)


def test_bo1_fearless_context_rejected(real_request):
    request = dict(real_request, draft_context={"enabled": True, "format": "bo1", "previous_games": []})
    with pytest.raises(ValueError, match="Bo3 or Bo5"):
        prepare_request(request, GAMES)


@pytest.mark.parametrize("league,scheduled", [("Custom", "2026-10-22T12:00:00Z"), ("LCK", "2026-10-22T12:00:00Z"), ("Worlds", "2027-10-22T12:00:00Z")])
def test_fearless_rules_do_not_claim_other_event_verification(real_request, league, scheduled):
    request = dict(real_request, league=league, scheduled_start=scheduled,
                   draft_context={"enabled": True, "format": "bo3", "previous_games": []})
    with pytest.raises(ValueError, match="verified only for Worlds 2026"):
        prepare_request(request, GAMES)


def test_fearless_previous_picks_cannot_be_banned_now(monkeypatch, real_request):
    import worlds_predictor.analysis as module
    from worlds_predictor.catalog import canonical_champion, champion_rows
    monkeypatch.setattr(module, "_catalog_functions", lambda: (canonical_champion, lambda: {"verified": True, "fearless_mode": "global", "source_url": "https://official.example/test-fixture", "formats": ["bo3", "bo5"]}))
    current_picks = {player["champion"] for side in ("blue", "red") for player in real_request[side]["players"]}
    banned = real_request["blue"]["bans"][0]
    previous = [banned] + [row["name_en"] for row in champion_rows() if row["name_en"] not in current_picks and row["name_en"] != banned][:9]
    request = dict(real_request, draft_context={"enabled": True, "format": "bo3", "previous_games": [{"blue_champions": previous[:5], "red_champions": previous[5:]}]})
    with pytest.raises(ValueError, match="unavailable as bans"):
        prepare_request(request, GAMES)


def test_analyze_router_invalid_input_and_missing_model(tmp_path, real_request):
    app = FastAPI()
    app.state.worlds_verification = {"status": "confirmed", "configured_patch": "26.20", "official_patch": "26.20"}
    app.include_router(create_analysis_router(tmp_path, GAMES))
    with TestClient(app) as client:
        result = client.post("/analyze", json=real_request)
        assert result.status_code == 503
        assert "probability" not in result.json()
        invalid = deepcopy(real_request)
        invalid["blue"]["players"].pop()
        assert client.post("/analyze", json=invalid).status_code == 422
        assert client.post("/analyze", json=dict(real_request, patch="16.19", league="WLDs")).status_code == 422


def test_real_router_probability_is_consistent_with_same_input(real_request, real_analysis):
    app = FastAPI()
    app.state.worlds_verification = {"status": "confirmed", "configured_patch": "26.20", "official_patch": "26.20"}
    app.include_router(create_analysis_router(MODELS, GAMES))
    with TestClient(app) as client:
        response = client.post("/analyze", json=real_request)
        assert response.status_code == 200
        result = response.json()
        assert result["comparison"] == real_analysis["comparison"]
        assert result["prediction"]["blue_win_probability"] == real_analysis["prediction"]["blue_win_probability"]
        assert result["prediction"]["worlds_patch_verification"]["status"] == "confirmed"


def test_sample_status_thresholds():
    assert [_sample_status(n) for n in (0, 1, 19, 20)] == ["none", "limited", "limited", "sufficient"]
