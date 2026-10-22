"""Test-only identity fixtures; no fixture is used as model training evidence."""
from copy import deepcopy

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from worlds_predictor import api
from worlds_predictor.lookup import resolve_request_ids, search_players


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "player_registry.csv"
    pd.DataFrame([
        {"player_id": "pro:test-one", "alias": "Known", "identity_basis": "test-only", "first_observed": "2024-01-01T00:00:00Z", "last_observed": "2026-10-01T00:00:00Z", "observed_games": 99},
        {"player_id": "pro:test-two", "alias": "Future", "identity_basis": "test-only", "first_observed": "2026-01-01T00:00:00Z", "last_observed": "2026-10-01T00:00:00Z", "observed_games": 66},
        {"player_id": "pro:test-three", "alias": "Collision", "identity_basis": "test-only", "first_observed": "2024-01-01T00:00:00Z", "last_observed": "2024-05-01T00:00:00Z", "observed_games": 1},
        {"player_id": "pro:test-four", "alias": "Collision", "identity_basis": "test-only", "first_observed": "2024-02-01T00:00:00Z", "last_observed": "2024-06-01T00:00:00Z", "observed_games": 1},
    ]).to_csv(path, index=False)
    return path


def payload(name="Known"):
    return {"as_of": "2025-01-01T00:00:00Z", "blue": {"players": [{"player_id": name}]}, "red": {"players": [{"player_id": "pro:test-unseen"}]}}


def test_exact_alias_resolves_without_mutating_request(registry):
    request = payload()
    original = deepcopy(request)
    result = resolve_request_ids(request, registry)
    assert result["blue"]["players"][0]["player_id"] == "pro:test-one"
    assert result["red"]["players"][0]["player_id"] == "pro:test-unseen"
    assert request == original


@pytest.mark.parametrize("name", ["Unknown", "Future", "Collision", "known"])
def test_unknown_future_ambiguous_and_fuzzy_aliases_rejected(registry, name):
    with pytest.raises(ValueError):
        resolve_request_ids(payload(name), registry)


def test_date_effective_mapping_and_future_mapping_rejected(registry, tmp_path):
    aliases = tmp_path / "aliases.csv"
    pd.DataFrame([
        {"canonical_id": "pro:test-one", "alias": "EarlierName", "valid_from": "2024-01-01", "valid_to": "2025-07-01"},
        {"canonical_id": "pro:test-two", "alias": "LaterName", "valid_from": "2025-07-01", "valid_to": ""},
    ]).to_csv(aliases, index=False)
    assert resolve_request_ids(payload("EarlierName"), registry, aliases)["blue"]["players"][0]["player_id"] == "pro:test-one"
    with pytest.raises(ValueError, match="no active mapping"):
        resolve_request_ids(payload("LaterName"), registry, aliases)


def test_two_aliases_cannot_resolve_to_same_player(registry):
    request = payload()
    request["red"]["players"][0]["player_id"] = "pro:test-one"
    with pytest.raises(ValueError, match="same professional"):
        resolve_request_ids(request, registry)


def test_search_filters_future_names_and_does_not_expose_future_aggregates(registry):
    result = search_players(registry, "", "2025-01-01T00:00:00Z")
    assert all(row["alias"] != "Future" for row in result)
    assert all("last_observed" not in row and "observed_games" not in row for row in result)
    assert search_players(registry, "kno", "2025-01-01T00:00:00Z")[0]["player_id"] == "pro:test-one"


def test_naive_lookup_cutoff_rejected(registry):
    with pytest.raises(ValueError, match="timezone"):
        search_players(registry, "Known", "2025-01-01")


def test_players_endpoint(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "verify_worlds_patch", lambda *args: {"status": "confirmed", "configured_patch": "26.20"})
    app = api.create_app(games_path=registry.parent / "games.parquet", verification_report=tmp_path / "verification.json")
    with TestClient(app) as client:
        response = client.get("/players", params={"query": "Known", "as_of": "2025-01-01T00:00:00Z"})
        assert response.status_code == 200
        assert response.json()["players"][0]["player_id"] == "pro:test-one"
        assert client.get("/players", params={"as_of": "2025-01-01"}).status_code == 422
