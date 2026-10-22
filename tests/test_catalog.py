"""Catalog invariants. Tiny synthetic rows are unit fixtures, never predictions."""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from worlds_predictor.catalog import (
    CATALOG_DIR, ROLES, canonical_champion, catalog_payload, game_request,
    get_worlds_rules, match_list, team_list, team_roster,
)
from worlds_predictor.catalog_api import create_catalog_router
from worlds_predictor.schemas import PredictionRequest
from worlds_predictor import catalog as catalog_module


def rows():
    result = []
    champions = ["Aatrox", "Lee Sin", "Ahri", "Ashe", "Leona", "Gnar", "Vi", "Orianna", "Jinx", "Nautilus"]
    for i in range(3):
        date = pd.Timestamp("2026-10-16T12:00:00Z") + pd.Timedelta(days=i)
        row = {"game_id": f"SYNTHETIC_UNIT_CATALOG_{i}", "date": date,
               "available_at": date.normalize() + pd.Timedelta(days=1), "league": "WLDs",
               "patch": "16.20", "blue_win": i % 2, "first_pick_side": "blue"}
        for side_index, side in enumerate(("blue", "red")):
            row[f"{side}_team_id"] = f"unit-team-{side}"
            row[f"{side}_team_name"] = f"UNIT TEST {side}"
            for role_index, role in enumerate(ROLES):
                row[f"{side}_{role}_player_id"] = f"unit-pro-{side}-{role}"
                row[f"{side}_{role}_player_name"] = f"Unit {side} {role}"
                row[f"{side}_{role}_champion"] = champions[5 * side_index + role_index]
            for ban in range(1, 6):
                row[f"{side}_ban{ban}"] = "unknown"
        result.append(row)
    return pd.DataFrame(result)


@pytest.fixture
def history(tmp_path):
    path = tmp_path / "test-only-games.parquet"
    rows().to_parquet(path, index=False)
    return path


@pytest.mark.parametrize("alias", ["Ahri", "ahri", "阿狸", "九尾妖狐"])
def test_champion_exact_bilingual_aliases(alias):
    assert canonical_champion(alias) == "Ahri"


def test_data_dragon_id_resolves_source_english_name():
    assert canonical_champion("MonkeyKing") == "Wukong"


def test_unknown_champion_does_not_get_synthetic_identity():
    with pytest.raises(ValueError, match="Unknown"):
        canonical_champion("nonexistent made-up champion")


def test_roster_is_observed_and_excludes_unavailable_results(history):
    roster = team_roster("unit-team-blue", "2026-10-18T00:00:00Z", history)
    assert roster["roster_status"] == "observed_last_match"
    assert roster["observed_at"] == "2026-10-16T12:00:00+00:00"
    assert "不是当前首发" in roster["notice"]
    assert all(p["history_games"] == 1 for p in roster["players"])
    assert all(p["recent_games"] == 1 for p in roster["players"])
    assert len(roster["players"]) == 5


def test_future_roster_change_cannot_change_past_roster(tmp_path, history):
    reference = team_roster("unit-team-blue", "2026-10-18T00:00:00Z", history)
    modified = rows()
    modified.loc[2, "blue_top_player_id"] = "unit-unseen-future-player"
    modified.loc[2, "blue_top_player_name"] = "FUTURE NAME"
    modified.loc[2, "blue_win"] = 1
    altered = tmp_path / "future-mutated-only.parquet"
    modified.to_parquet(altered, index=False)
    assert team_roster("unit-team-blue", "2026-10-18T00:00:00Z", altered) == reference


def test_unknown_team_never_invents_roster(history):
    with pytest.raises(LookupError):
        team_roster("unknown-team", "2026-10-22T00:00:00Z", history)


def test_team_search_and_counts_are_cutoff_bounded(history):
    result = team_list("2026-10-18T00:00:00Z", history, worlds_only=False, query="blue")
    assert result["returned"] == 1
    assert result["teams"][0]["history_games"] == 1
    assert result["teams"][0]["participation_status"] == "historical_observed"
    assert result["teams"][0]["logo_url"] is None


def test_catalog_roles_are_empirical_before_cutoff(history):
    result = catalog_payload("2026-10-18T00:00:00Z", history)
    ahri = next(c for c in result["champions"] if c["name_en"] == "Ahri")
    assert ahri["roles"] == ["mid"]
    assert ahri["role_counts"]["mid"] == 1
    assert len(result["champions"]) == 173
    assert result["provenance"]["history_games"] == 1


def test_match_replay_never_contains_actual_result(history):
    result = match_list("2026-10-22T00:00:00Z", history)
    assert result["returned"] == 3
    row = result["matches"][0]
    assert row["blue_win"] in [0, 1]
    assert "blue_win" not in row["request"]
    assert "result" not in row["request"]
    assert len(row["player_names"]) == 10
    PredictionRequest.model_validate(row["request"])


def test_regional_qualifiers_not_shown_as_worlds(tmp_path):
    frame = rows()
    frame.loc[0, "patch"] = "16.17"
    frame.loc[1, "league"] = "LCK"
    path = tmp_path / "test-mixed-event.parquet"
    frame.to_parquet(path, index=False)
    result = match_list("2026-10-22T00:00:00Z", path)
    assert result["returned"] == 1
    assert result["matches"][0]["game_id"] == frame.iloc[2].game_id


def test_verified_rules_have_precise_source_and_no_series_probability():
    rules = get_worlds_rules()
    assert rules["verified"] and rules["fearless_mode"] == "global"
    assert rules["source_url"].startswith("https://cdn.sanity.io/")
    assert rules["series_prediction_supported"] is False
    assert rules["standard_bans_carry_over"] is False


def test_readonly_catalog_router_errors(history):
    app = FastAPI()
    app.include_router(create_catalog_router(history))
    with TestClient(app) as client:
        assert client.get("/teams", params={"as_of": "2026-10-22"}).status_code == 422
        assert client.get("/teams/no-such-team/roster", params={"as_of": "2026-10-22T00:00:00Z"}).status_code == 404
        response = client.get("/matches", params={"as_of": "2026-10-22T00:00:00Z"})
        assert response.status_code == 200 and response.json()["returned"] == 3


def test_participant_snapshot_and_catalog_hashes_are_real_files():
    root = Path(__file__).resolve().parents[1]
    participants = json.loads((root / "configs/worlds2026_participants.json").read_text())
    assert len(participants["teams"]) == 19
    assert len({team["team_id"] for team in participants["teams"]}) == 19
    assert participants["source_url"].startswith("https://lolesports.com/")
    assert (CATALOG_DIR / "champion-en_US.json").is_file()


@pytest.fixture
def september_history_and_official_snapshot(tmp_path, monkeypatch):
    frame = rows()
    frame["date"] = frame["date"] - pd.Timedelta(days=40)
    frame["available_at"] = frame["available_at"] - pd.Timedelta(days=40)
    path = tmp_path / "september-unit-history.parquet"
    frame.to_parquet(path, index=False)
    participants = {"source_published_date": "2026-10-05", "source_published_at": None,
                    "qualification_available_at": "2026-10-06T00:00:00Z",
                    "retrieved_at": "2026-10-22T12:00:00Z", "source_url": "https://lolesports.com/unit-test-only",
                    "teams": [{"team_id": "unit-team-blue", "name": "FUTURE OFFICIAL NAME",
                               "code": "FUT", "region": "FUTURE REGION"}]}
    config = tmp_path / "unit-participants.json"
    config.write_text(json.dumps(participants))
    monkeypatch.setattr(catalog_module, "PARTICIPANTS", config)
    return path


@pytest.mark.parametrize("cutoff", ["2026-10-04T23:59:59Z", "2026-10-05T23:59:59Z", "2026-10-06T00:00:00Z"])
def test_worlds_qualification_not_revealed_before_publication(september_history_and_official_snapshot, cutoff):
    result = team_list(cutoff, september_history_and_official_snapshot, worlds_only=True)
    assert result["teams"] == [] and result["returned"] == 0
    assert result["qualification_status"] == "not_available_before_publication"
    assert "不展示未来参赛资格" in result["notice"]


def test_all_team_search_cannot_reveal_future_qualification_or_names(september_history_and_official_snapshot):
    result = team_list("2026-10-04T00:00:00Z", september_history_and_official_snapshot, worlds_only=False)
    assert result["returned"] == 2
    assert all(not team["worlds_2026"] for team in result["teams"])
    assert all(team["participation_status"] == "historical_observed" for team in result["teams"])
    assert all("FUTURE" not in team["name"] for team in result["teams"])
    assert all(team["history_games"] == 3 for team in result["teams"])


def test_catalog_does_not_reveal_future_participant_count(september_history_and_official_snapshot):
    result = catalog_payload("2026-10-04T00:00:00Z", september_history_and_official_snapshot)
    assert result["worlds"]["participant_count"] == 0
    assert result["worlds"]["qualification_available"] is False
    assert "teams" not in result["worlds"]


def test_qualification_available_only_after_conservative_boundary(september_history_and_official_snapshot):
    result = team_list("2026-10-06T00:00:01Z", september_history_and_official_snapshot, worlds_only=True)
    assert result["returned"] == 1
    assert result["teams"][0]["name"] == "FUTURE OFFICIAL NAME"
    assert result["teams"][0]["worlds_2026"] is True
    assert result["qualification_status"] == "current_official_snapshot"


def test_real_worlds_snapshot_publication_has_date_but_no_invented_time():
    participants = catalog_module._participants()
    assert participants["source_published_date"] == "2026-10-05"
    assert participants["source_published_at"] is None
    assert participants["qualification_available_at"] == "2026-10-06T00:00:00+00:00"
