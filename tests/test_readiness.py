"""Integrity checks use temporary fixture bytes, never production model files."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worlds_predictor import api


@pytest.fixture
def readiness_fixture(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    artifact = b"explicit test-only serialization placeholder"
    (model_dir / "selected_model.joblib").write_bytes(artifact)
    metadata = {
        "status": "trained", "label_cutoff": "2025-01-01T00:00:00Z",
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "feature_code_sha256": hashlib.sha256(Path(api.__file__).with_name("features.py").read_bytes()).hexdigest(),
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    games_path = tmp_path / "games.parquet"
    games_path.write_bytes(b"explicit test-only data placeholder")
    return model_dir, games_path, metadata


@pytest.mark.parametrize("damage", ["artifact_bytes", "feature_hash", "missing_hash", "invalid_cutoff", "naive_cutoff", "non_object_metadata"])
def test_health_marks_damaged_artifact_or_metadata_unavailable(readiness_fixture, monkeypatch, damage):
    model_dir, games_path, metadata = readiness_fixture
    if damage == "artifact_bytes":
        (model_dir / "selected_model.joblib").write_bytes(b"changed after training")
    elif damage == "feature_hash":
        metadata["feature_code_sha256"] = "0" * 64
    elif damage == "missing_hash":
        del metadata["artifact_sha256"]
    elif damage == "invalid_cutoff":
        metadata["label_cutoff"] = "not a date"
    elif damage == "naive_cutoff":
        metadata["label_cutoff"] = "2025-01-01T00:00:00"
    elif damage == "non_object_metadata":
        metadata = []
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    monkeypatch.setattr(api, "verify_worlds_patch", lambda *args: {"status": "confirmed", "configured_patch": "26.20"})
    app = api.create_app(model_dir, games_path)
    with TestClient(app) as client:
        model = client.get("/health").json()["model"]
        assert model["available"] is False
        assert model["reason"]


def test_corrupted_model_predict_returns_503_before_deserializing(readiness_fixture, monkeypatch):
    model_dir, games_path, _ = readiness_fixture
    (model_dir / "selected_model.joblib").write_bytes(b"corrupted")
    monkeypatch.setattr(api, "verify_worlds_patch", lambda *args: {"status": "confirmed", "configured_patch": "26.20"})
    monkeypatch.setattr(api, "run_prediction", lambda *args: pytest.fail("Corrupted artifact reached deserialization"))
    champions = ["Gnar", "Vi", "Ahri", "Ashe", "Nautilus", "Renekton", "Viego", "Orianna", "Jhin", "Rell"]
    roles = ["top", "jng", "mid", "bot", "sup"]
    payload = {"as_of": "2026-10-22T00:00:00Z", "scheduled_start": "2026-10-23T00:00:00Z", "league": "Worlds", "patch": "26.20"}
    for index, side in enumerate(("blue", "red")):
        payload[side] = {"team_id": f"test-only-{side}", "players": [{"role": role, "player_id": f"test-only-{side}-{role}", "champion": champions[index * 5 + i]} for i, role in enumerate(roles)]}
    with TestClient(api.create_app(model_dir, games_path)) as client:
        response = client.post("/predict", json=payload)
        assert response.status_code == 503
        assert "SHA256" in response.json()["detail"]
