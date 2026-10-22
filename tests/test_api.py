"""Schema and routing tests use explicit test-only fixtures, never model evidence."""
import json
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from worlds_predictor import api
from worlds_predictor.schemas import PredictionRequest


@pytest.fixture
def request_body():
    roles = ["top", "jng", "mid", "bot", "sup"]
    return {
        "as_of": "2026-10-22T00:00:00Z",
        "scheduled_start": "2026-10-23T00:00:00Z",
        "league": "Worlds",
        "patch": "26.20",
        "first_pick_side": "red",
        "blue": {"team_id": "test-only-blue", "players": [{"role": role, "player_id": f"test-only-blue-{role}", "champion": champ} for role, champ in zip(roles, ["Gnar", "Vi", "Ahri", "Ashe", "Nautilus"])]},
        "red": {"team_id": "test-only-red", "players": [{"role": role, "player_id": f"test-only-red-{role}", "champion": champ} for role, champ in zip(roles, ["Renekton", "Viego", "Orianna", "Jhin", "Rell"])]},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "verify_worlds_patch", lambda *args: {"status": "confirmed", "configured_patch": "26.20", "official_patch": "26.20"})
    return api.create_app(model_dir=tmp_path / "missing-model", games_path=tmp_path / "missing-games.parquet", verification_report=tmp_path / "verification.json")


def test_missing_model_never_returns_probability(app, request_body):
    with TestClient(app) as client:
        response = client.post("/predict", json=request_body)
        assert response.status_code == 503
        assert "probability" not in response.json()
        assert client.get("/health").json()["model"]["available"] is False


def test_first_pick_independent_from_side(request_body):
    assert PredictionRequest.model_validate(request_body).first_pick_side == "red"
    del request_body["first_pick_side"]
    assert PredictionRequest.model_validate(request_body).first_pick_side == "unknown"


@pytest.mark.parametrize("bad_field", ["kills", "gold", "blue_win", "result", "damage"])
def test_current_postgame_inputs_rejected(request_body, bad_field):
    request_body[bad_field] = 1
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate(request_body)


def test_duplicate_role_rejected(app, request_body):
    request_body["blue"]["players"][0]["role"] = "mid"
    with TestClient(app) as client:
        assert client.post("/predict", json=request_body).status_code == 422


@pytest.mark.parametrize("mutation", ["timestamp", "timezone", "players", "champions", "teams", "bans", "ban_pick", "series"])
def test_invalid_request_rejected(request_body, mutation):
    if mutation == "timestamp":
        request_body["as_of"] = "2026-10-24T00:00:00Z"
    elif mutation == "timezone":
        request_body["as_of"] = "2026-10-22T00:00:00"
    elif mutation == "players":
        request_body["red"]["players"][0]["player_id"] = request_body["blue"]["players"][0]["player_id"]
    elif mutation == "champions":
        request_body["red"]["players"][0]["champion"] = "Gnar"
    elif mutation == "teams":
        request_body["red"]["team_id"] = request_body["blue"]["team_id"]
    elif mutation == "bans":
        request_body["blue"]["bans"] = ["Azir", "Azir"]
    elif mutation == "ban_pick":
        request_body["blue"]["bans"] = ["Gnar"]
    elif mutation == "series":
        request_body["series_context"] = {"map_number": 2}
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate(request_body)


@pytest.mark.parametrize("league", ["Worlds", "WLDs", "WCS", "World Championship"])
@pytest.mark.parametrize("patch", ["26.19", "16.19"])
def test_worlds_wrong_patch_rejected(app, request_body, league, patch):
    request_body["league"] = league
    request_body["patch"] = patch
    with TestClient(app) as client:
        assert client.post("/predict", json=request_body).status_code == 422


@pytest.mark.parametrize("league", ["Worlds", "WLDs", "WCS", "World Championship"])
@pytest.mark.parametrize("patch", ["26.20", "16.20", "16.19"])
def test_worlds_official_mismatch_fails_closed(app, request_body, league, patch):
    request_body["league"] = league
    request_body["patch"] = patch
    with TestClient(app) as client:
        app.state.worlds_verification["status"] = "mismatch"
        response = client.post("/predict", json=request_body)
        assert response.status_code == 503
        assert "official patch" in response.json()["detail"]


@pytest.mark.parametrize("league,patch", [("Worlds", "26.20"), ("WLDs", "16.20"), ("WCS", "26.20"), ("World Championship", "16.20")])
def test_prediction_routes_valid_request_and_keeps_provenance(tmp_path, monkeypatch, request_body, league, patch):
    request_body["league"] = league
    request_body["patch"] = patch
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fixture_bytes = b"not a model: API routing fixture"
    (model_dir / "selected_model.joblib").write_bytes(fixture_bytes)
    (model_dir / "metadata.json").write_text(json.dumps({
        "status": "trained", "label_cutoff": "2026-01-01T00:00:00Z",
        "artifact_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "feature_code_sha256": hashlib.sha256(Path(api.__file__).with_name("features.py").read_bytes()).hexdigest(),
    }))
    games_path = tmp_path / "games.parquet"
    games_path.write_bytes(b"not a dataset: API routing fixture")
    monkeypatch.setattr(api, "verify_worlds_patch", lambda *args: {"status": "unverified", "configured_patch": "26.20"})
    seen = {}

    def fixture_prediction(payload, model_path, data_path):
        seen.update(payload)
        return {"test_only_route_sentinel": True, "model_version": "test-only-mock"}

    monkeypatch.setattr(api, "run_prediction", fixture_prediction)
    app = api.create_app(model_dir, games_path, verification_report=tmp_path / "verification.json")
    with TestClient(app) as client:
        response = client.post("/predict", json=request_body)
        assert response.status_code == 200
        assert seen["first_pick_side"] == "red"
        assert response.json()["model_version"] == "test-only-mock"
        assert response.json()["worlds_patch_verification"]["status"] == "unverified"
        assert response.json()["warnings"]
