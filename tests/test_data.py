"""Synthetic structural fixtures only; never used as training/evaluation data."""
import pandas as pd
import pytest

from worlds_predictor.data import import_manual_csv, load_games, normalize_data, normalize_frames, read_aliases, resolve_player_id


def source_fixture(gid="fixture-game", date="2025-01-01 10:00:00"):
    players, teams = [], []
    for side in ("Blue", "Red"):
        common = dict(game_id=gid, date=date, league="fixture_league", patch="25.1", side=side, team_name=f"fixture_{side}", result="TRUE" if side == "Blue" else "FALSE")
        team = dict(common, team_id=f"fixture_team_{side}", first_pick="FALSE" if side == "Blue" else "TRUE", gamelength="1800")
        for i, role in enumerate(("top", "jng", "mid", "bot", "sup"), 1):
            champion = f"fixture_champion_{side}_{i}"
            players.append(dict(common, position=role, playername=f"fixture_player_{side}_{i}", champion=champion))
            team[f"pick{i}"] = champion
            team[f"ban{i}"] = f"fixture_ban_{side}_{i}"
        teams.append(team)
    return pd.DataFrame(players), pd.DataFrame(teams)


def test_composite_join_is_one_row_and_first_pick_is_separate():
    players, teams = source_fixture()
    games, report, registry, stints, quarantine = normalize_frames(players, teams)
    assert len(games) == 1
    assert games.iloc[0].blue_team_id == "fixture_team_Blue"
    assert games.iloc[0].first_pick_side == "red"
    assert games.iloc[0].blue_top_player_name == "fixture_player_Blue_1"
    assert len(registry) == 10 and len(stints) == 10 and quarantine.empty
    assert report["identity_coverage"]["player_rows_by_identity_basis"] == {"source_playername_unverified": 10}
    assert games.iloc[0].available_at == pd.Timestamp("2025-01-02T00:00Z")


@pytest.mark.parametrize("fault", ["team_duplicate", "missing_role", "result", "wrong_side", "duplicate_player", "pick_mismatch", "team_name", "invalid_date", "duplicate_ban", "ban_pick_conflict", "invalid_patch"])
def test_quarantines_bad_game(fault):
    players, teams = source_fixture()
    if fault == "team_duplicate":
        duplicate = teams.iloc[[0]].copy(); duplicate["team_id"] = "conflicting"
        teams = pd.concat([teams, duplicate])
    elif fault == "missing_role":
        players = players.iloc[:-1].copy()
    elif fault == "result":
        players.loc[0, "result"] = "FALSE"
    elif fault == "wrong_side":
        players.loc[0, "side"] = "Red"
    elif fault == "duplicate_player":
        players.loc[0, "playername"] = players.loc[1, "playername"]
    elif fault == "pick_mismatch":
        teams.loc[0, "pick1"] = "wrong_champion"
    elif fault == "team_name":
        players.loc[0, "team_name"] = "wrong_team"
    elif fault == "invalid_date":
        players.loc[0, "date"] = "not-a-time"
    elif fault == "duplicate_ban":
        teams.loc[0, "ban1"] = teams.loc[1, "ban1"]
    elif fault == "ban_pick_conflict":
        teams.loc[0, "ban1"] = players.loc[0, "champion"]
    elif fault == "invalid_patch":
        teams["patch"] = "wrong"
    games, report, _, _, quarantine = normalize_frames(players, teams)
    assert games.empty
    assert report["quarantined_games"] == 1
    assert len(quarantine) == 1


def test_deduplicate_exact_rows_without_double_counting():
    players, teams = source_fixture()
    games, report, *_ = normalize_frames(pd.concat([players, players]), pd.concat([teams, teams]))
    assert len(games) == 1
    assert report["exact_duplicate_player_rows_removed"] == 10
    assert report["exact_duplicate_team_rows_removed"] == 2


def test_aliases_are_date_effective_and_ambiguous_intervals_fail(tmp_path):
    path = tmp_path / "aliases.csv"
    path.write_text("canonical_id,alias,valid_from,valid_to\npro:verified,fixture_player_Blue_1,2025-01-02,2025-02-01\n")
    aliases = read_aliases(path)
    assert resolve_player_id("fixture_player_Blue_1", "2025-01-03", aliases) == "pro:verified"
    assert resolve_player_id("fixture_player_Blue_1", "2025-01-01", aliases) != "pro:verified"
    assert resolve_player_id("fixture_player_Blue_1", "2025-02-01", aliases) != "pro:verified"
    with path.open("a") as stream:
        stream.write("pro:conflict,fixture_player_Blue_1,2025-01-03,2025-02-02\n")
    with pytest.raises(ValueError, match="overlapping"):
        read_aliases(path)


def test_unknown_bans_and_first_pick_are_explicit():
    players, teams = source_fixture()
    teams["first_pick"] = ""
    teams["ban1"] = "None"
    games, report, *_ = normalize_frames(players, teams)
    assert games.iloc[0].first_pick_side == "unknown"
    assert report["missing_ban_slots"] == 2


def test_as_of_strict_storage_filter_excludes_unavailable_and_future(tmp_path):
    p1, t1 = source_fixture("fixture-1", "2025-01-01 10:00:00")
    p2, t2 = source_fixture("fixture-2", "2025-01-02 10:00:00")
    games, *_ = normalize_frames(pd.concat([p1, p2]), pd.concat([t1, t2]))
    path = tmp_path / "games.parquet"
    games.to_parquet(path)
    assert load_games(path, as_of="2025-01-02T00:00Z").empty  # strict available_at
    selected = load_games(path, as_of="2025-01-02T00:00:01Z")
    assert list(selected.game_id) == ["fixture-1"]
    truncated, report, *_ = normalize_frames(pd.concat([p1, p2]), pd.concat([t1, t2]), as_of="2025-01-02T00:00Z")
    assert list(truncated.game_id) == ["fixture-1"]
    assert report["excluded_at_or_after_as_of_games"] == 1


def test_source_pro_id_preferred_over_local_name():
    players, teams = source_fixture()
    players["playerid"] = [f"oe:player:{i}" for i in range(10)]
    games, report, *_ = normalize_frames(players, teams)
    assert games.iloc[0].blue_top_player_id == "oe:player:0"
    assert report["identity_coverage"]["player_rows_by_identity_basis"] == {"source_player_id": 10}


def test_no_current_game_postmatch_statistics_survive():
    players, teams = source_fixture()
    players["kills"] = 999
    players["goldat15"] = 999999
    teams["dragons"] = 999
    games, *_ = normalize_frames(players, teams)
    assert not any(any(token in col for token in ("kills", "gold", "damage", "dragon", "gamelength")) for col in games.columns)


def test_original_oe_manual_import_and_duckdb_roundtrip(tmp_path):
    players, teams = source_fixture()
    players["playerid"] = [f"oe:player:{i}" for i in range(10)]
    players["team_id"] = players.side.map({"Blue": "fixture_team_Blue", "Red": "fixture_team_Red"})
    teams["position"] = "team"
    original = pd.concat([players, teams], ignore_index=True).rename(columns={"game_id": "gameid", "team_name": "teamname", "team_id": "teamid", "first_pick": "firstpick"})
    csv_path = tmp_path / "fixture_original_oe.csv"
    original.to_csv(csv_path, index=False)
    raw, out = tmp_path / "manual", tmp_path / "processed"
    provenance = import_manual_csv(csv_path, raw, "https://example.test/fixture-only", "fixture-only; no real match data")
    assert provenance["downloaded_at"] is None
    assert provenance["provenance_verified"] is False
    report = normalize_data(raw, out)
    assert report["accepted_games"] == 1
    assert list(load_games(out / "games.duckdb").game_id) == ["fixture-game"]
    assert (out / "player_registry.csv").exists()


def test_alias_override_is_not_applied_before_effective_date(tmp_path):
    path = tmp_path / "aliases.csv"
    path.write_text("canonical_id,alias,valid_from,valid_to\npro:verified,fixture_player_Blue_1,2025-01-02,\n")
    p1, t1 = source_fixture("fixture-1", "2025-01-01 10:00:00")
    p2, t2 = source_fixture("fixture-2", "2025-01-03 10:00:00")
    games, *_ = normalize_frames(pd.concat([p1, p2]), pd.concat([t1, t2]), alias_path=path)
    assert games.iloc[0].blue_top_player_id != "pro:verified"
    assert games.iloc[1].blue_top_player_id == "pro:verified"
