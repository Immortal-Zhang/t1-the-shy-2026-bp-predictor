"""Auditable ingestion of real professional match CSVs; no generated match data.

ChainCC provides professional display names, NOT immutable player person IDs.
The local ``pro:`` registry is stable but its identity linkage is explicitly
unverified until a dated alias mapping or source player ID is supplied.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
import unicodedata
import uuid

import duckdb
import pandas as pd

ROLES = ("top", "jng", "mid", "bot", "sup")
SIDES = ("blue", "red")
SOURCE_URL = "https://chaincc.lol/free/data/"
SOURCE_LICENSE = "CC BY 4.0; attribution required; underlying Riot rights remain applicable"
ID_NAMESPACE = uuid.UUID("632da0db-a770-5cee-8dd5-21aa1ea368ff")
REQUIRED_PLAYER = {"game_id", "date", "league", "patch", "side", "team_name", "position", "playername", "champion", "result"}
REQUIRED_TEAM = {"game_id", "date", "league", "patch", "side", "team_name", "team_id", "result"}
KEEP_COLS = REQUIRED_PLAYER | REQUIRED_TEAM | {"playerid", "player_id", "first_pick", "gamelength", "split", "game_number", "bo_format", "match_in_series", "game_in_match"} | {f"{kind}{i}" for kind in ("ban", "pick") for i in range(1, 6)}
OE_RENAME = {"gameid": "game_id", "teamname": "team_name", "teamid": "team_id", "firstpick": "first_pick", "game": "game_number"}


def _utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    """TLS-verified curl with a bounded timeout; never accept an HTML error page."""
    temporary = target.with_name(target.name + ".partial")
    subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2", "--connect-timeout", "20", "--max-time", "180", "--output", str(temporary), url], check=True)
    pd.read_csv(temporary, compression="gzip", nrows=1)
    temporary.replace(target)


def download_data(raw_dir: str | Path, years=(2024, 2025, 2026)) -> dict:
    """Download each selected ChainCC season and save provenance, even on failure.

    Existing files are retained and hashed; this supports interrupted downloads.
    Remove/rename a specific local file explicitly to request a newer snapshot.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    old_path = raw_dir / "sources.json"
    old = json.loads(old_path.read_text()) if old_path.exists() else {}
    old_files = {entry["filename"]: entry for entry in old.get("files", [])}

    def one(spec):
        year, kind = spec
        name = f"chaincc-{kind}-{year}.csv.gz"
        url = f"https://chaincc.lol/data/{name}"
        path = raw_dir / name
        entry = {"filename": name, "url": url, "source_page": SOURCE_URL, "license": SOURCE_LICENSE, "attribution": "ChainCC. League of Legends esports match dataset. https://chaincc.lol/free/data/", "checked_at": _now()}
        try:
            reused = path.exists()
            if not reused:
                _download(url, path)
            dates = pd.read_csv(path, usecols=["date"], dtype=str)["date"]
            parsed = pd.to_datetime(dates, utc=True, errors="coerce", format="mixed")
            entry.update(status="available", sha256=_sha256(path), bytes=path.stat().st_size, rows=len(dates), downloaded_at=old_files.get(name, {}).get("downloaded_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()), download_timestamp_basis="previous manifest or local file mtime for preexisting files", reused=reused, date_min=parsed.min().isoformat(), date_max=parsed.max().isoformat())
        except Exception as error:
            entry.update(status="failed", error=str(error))
        return entry

    with ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(one, [(year, kind) for year in years for kind in ("players", "teams")]))
    manifest = {"generated_at": _now(), "source": "ChainCC", "source_page": SOURCE_URL, "license": SOURCE_LICENSE, "source_last_update_advertised": "2026-10-21 (observed 2026-10-22; refresh page to reverify)", "files": files, "fallback": {"url": "https://oracleselixir.com/tools/downloads", "access_observed": "403 on 2026-10-22", "license": "Verify current Oracle's Elixir and underlying Riot/Leaguepedia terms before reuse; no blanket license inferred.", "manual_import": "Place original yearly Oracle's Elixir CSVs in a separate raw directory; import_manual_csv records source URL and license."}}
    _write_json(old_path, manifest)
    return manifest


def import_manual_csv(source: str | Path, raw_dir: str | Path, source_url: str, license_text: str) -> dict:
    """Copy an original CSV and record user-supplied provenance, never invent it."""
    source, raw_dir = Path(source), Path(raw_dir)
    if not source_url.strip() or not license_text.strip():
        raise ValueError("Manual import requires source_url and license_text (use 'unknown' if unverified)")
    if not source.name.endswith((".csv", ".csv.gz")):
        raise ValueError("Expected .csv or .csv.gz")
    pd.read_csv(source, nrows=1)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / source.name
    if source.resolve() != target.resolve():
        if target.exists() and _sha256(target) != _sha256(source):
            raise FileExistsError(f"Refusing to overwrite a different snapshot: {target}")
        shutil.copy2(source, target)
    manifest_path = raw_dir / "sources.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": []}
    entry = {"filename": target.name, "url": source_url, "license": license_text, "downloaded_at": None, "imported_at": _now(), "sha256": _sha256(target), "bytes": target.stat().st_size, "status": "available", "provenance_verified": False, "note": "Manual source attribution supplied by operator; original download time unknown"}
    manifest["files"] = [item for item in manifest["files"] if item["filename"] != target.name] + [entry]
    _write_json(manifest_path, manifest)
    return entry


def _read_sources(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    players, teams, evidence = [], [], []
    paths = sorted(set(raw_dir.glob("*.csv")) | set(raw_dir.glob("*.csv.gz")))
    for path in paths:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        if not ({"game_id", "gameid"} & set(header)):
            continue
        names = {col for col in header if OE_RENAME.get(col, col) in KEEP_COLS or col == "position"}
        df = pd.read_csv(path, usecols=list(names), dtype=str, keep_default_na=False).rename(columns=OE_RENAME)
        if "gameid" in header:
            if "position" not in df:
                raise ValueError(f"OE file missing position: {path}")
            team = df[df.position.str.lower().eq("team")].copy()
            player = df[~df.position.str.lower().eq("team")].copy()
            players.append(player); teams.append(team)
            provider = "oracles_elixir"
        elif "position" in df and "playername" in df:
            players.append(df); provider = "chaincc_players"
        else:
            teams.append(df); provider = "chaincc_teams"
        evidence.append({"path": str(path), "sha256": _sha256(path), "rows": len(df), "columns": header, "format": provider})
    if not players or not teams:
        raise ValueError("Need both player and team records. Download ChainCC player+team CSVs, or import an original OE CSV containing both position=team and player rows.")
    return pd.concat(players, ignore_index=True).fillna(""), pd.concat(teams, ignore_index=True).fillna(""), evidence


def _bool(value: Any) -> int | None:
    return {"true": 1, "1": 1, "1.0": 1, "false": 0, "0": 0, "0.0": 0}.get(str(value).strip().lower())


def _clean_name(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def _identity_key(name: str) -> str:
    return "pro:" + str(uuid.uuid5(ID_NAMESPACE, _clean_name(name)))


def read_aliases(alias_path: str | Path | None) -> pd.DataFrame:
    cols = ["canonical_id", "alias", "valid_from", "valid_to"]
    if alias_path is None:
        return pd.DataFrame(columns=cols)
    aliases = pd.read_csv(alias_path, dtype=str, keep_default_na=False)
    missing = set(cols) - set(aliases)
    if missing:
        raise ValueError(f"Alias CSV missing columns: {sorted(missing)}")
    if (aliases.canonical_id.str.strip().eq("") | aliases.alias.str.strip().eq("")).any():
        raise ValueError("Alias and canonical_id must be nonempty")
    aliases["alias"] = aliases.alias.map(_clean_name)
    aliases["valid_from"] = pd.to_datetime(aliases.valid_from.replace("", "1900-01-01"), utc=True, errors="raise", format="mixed")
    aliases["valid_to"] = pd.to_datetime(aliases.valid_to.replace("", "2200-01-01"), utc=True, errors="raise", format="mixed")
    if (aliases.valid_to <= aliases.valid_from).any():
        raise ValueError("Alias intervals are half-open [valid_from, valid_to) and must be nonempty")
    for name, group in aliases.groupby("alias"):
        rows = list(group.sort_values("valid_from").itertuples())
        for previous, current in zip(rows, rows[1:]):
            if current.valid_from < previous.valid_to:
                raise ValueError(f"Ambiguous overlapping alias intervals: {name}")
    return aliases


def resolve_player_id(alias: str, as_of: Any, aliases: pd.DataFrame | None = None, known_ids: set[str] | None = None) -> str:
    """Resolve exact, date-effective aliases; no fuzzy merges or solo-queue IDs."""
    alias, date = _clean_name(alias), _utc(as_of)
    if known_ids is not None and alias in known_ids:
        return alias
    if aliases is not None and not aliases.empty:
        rows = aliases[(aliases.alias == alias) & (aliases.valid_from <= date) & (date < aliases.valid_to)]
        if len(rows) > 1:
            raise ValueError(f"Ambiguous player alias {alias!r}")
        if len(rows) == 1:
            return str(rows.iloc[0].canonical_id)
    # An opaque canonical ID is accepted verbatim; a name becomes a documented
    # local identity, NOT an assertion of globally verified personhood.
    if alias.startswith(("pro:", "oe:player:", "source:")):
        return alias
    if not alias:
        raise ValueError("Empty player identifier")
    return _identity_key(alias)


def normalize_frames(players: pd.DataFrame, teams: pd.DataFrame, as_of=None, alias_path=None) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Normalize already-read source frames. Useful for tested manual adapters."""
    players, teams = players.copy().fillna(""), teams.copy().fillna("")
    for label, df, required in (("players", players, REQUIRED_PLAYER), ("teams", teams, REQUIRED_TEAM)):
        missing = required - set(df)
        if missing:
            raise ValueError(f"{label} missing required source fields: {sorted(missing)}")
        for col in df.select_dtypes(include=["object", "string"]):
            df[col] = df[col].astype(str).str.strip()
        df["side"] = df.side.str.lower().replace({"100": "blue", "200": "red"})
        df["date"] = pd.to_datetime(df.date, utc=True, errors="coerce", format="mixed")
        df["result"] = df.result.map(_bool)
    raw_players, raw_teams = len(players), len(teams)
    raw_game_ids = set(players.game_id) | set(teams.game_id)
    quarantined: dict[str, set[str]] = {}

    def mark(ids, reason):
        for gid in ids:
            quarantined.setdefault(str(gid), set()).add(reason)

    for label, df in (("player", players), ("team", teams)):
        mark(df.loc[df.date.isna(), "game_id"], f"invalid_{label}_date")
        mark(df.loc[~df.side.isin(SIDES), "game_id"], f"invalid_{label}_side")
        mark(df.loc[df.result.isna(), "game_id"], f"invalid_{label}_result")
        mark(df.loc[~df.patch.astype(str).str.fullmatch(r"\d{2}\.\d{1,2}"), "game_id"], f"invalid_{label}_patch")
        required_nonempty = ["game_id", "league", "patch", "team_name"] + (["team_id"] if label == "team" else ["playername", "champion", "position"])
        mark(df.loc[df[required_nonempty].eq("").any(axis=1), "game_id"], f"missing_{label}_required_value")
    future_games = set()
    if as_of is not None:
        cutoff = _utc(as_of)
        future_games = set(players.loc[players.date >= cutoff, "game_id"]) | set(teams.loc[teams.date >= cutoff, "game_id"])
        players = players[~players.game_id.isin(future_games)].copy()
        teams = teams[~teams.game_id.isin(future_games)].copy()
    before_p, before_t = len(players), len(teams)
    players, teams = players.drop_duplicates().copy(), teams.drop_duplicates().copy()
    duplicate_players_removed, duplicate_teams_removed = before_p - len(players), before_t - len(teams)
    players["position"] = players.position.str.lower().replace({"jungle": "jng", "adc": "bot", "bottom": "bot", "support": "sup", "middle": "mid"})
    mark(teams.loc[teams.duplicated(["game_id", "side"], keep=False), "game_id"], "duplicate_conflicting_team_side")
    mark(players.loc[players.duplicated(["game_id", "side", "position"], keep=False), "game_id"], "duplicate_conflicting_player_slot")
    mark(players.loc[~players.position.isin(ROLES), "game_id"], "invalid_role")
    pcounts = players.groupby("game_id").size(); tcounts = teams.groupby("game_id").size()
    mark(pcounts[pcounts != 10].index, "not_ten_players")
    mark(tcounts[tcounts != 2].index, "not_two_teams")
    mark(set(players.game_id) ^ set(teams.game_id), "missing_player_or_team_records")
    sides = teams.groupby("game_id").side.nunique()
    mark(sides[sides != 2].index, "missing_blue_or_red")
    for side in SIDES:
        counts = players[players.side == side].groupby("game_id").position.nunique()
        mark(counts[counts != 5].index, "not_five_distinct_roles_per_side")
    players = players[~players.game_id.isin(quarantined)].copy()
    teams = teams[~teams.game_id.isin(quarantined)].copy()
    # The composite key and relationship check are mandatory: game_id alone
    # would silently duplicate every player onto the opposing side.
    team_cols = ["game_id", "side", "team_id", "team_name", "result", "date", "patch", "league"]
    joined = players.merge(teams[team_cols], on=["game_id", "side"], how="left", validate="many_to_one", suffixes=("", "_team"), indicator=True)
    mark(joined.loc[joined._merge != "both", "game_id"], "unmatched_player_team_side")
    for field in ("team_name", "result", "date", "patch", "league"):
        mark(joined.loc[joined[field] != joined[f"{field}_team"], "game_id"], f"inconsistent_player_team_{field}")
    # OE includes team_id on player rows; verify it rather than discard it.
    if "team_id_team" in joined:
        mark(joined.loc[(joined.team_id != "") & (joined.team_id != joined.team_id_team), "game_id"], "inconsistent_player_team_id")
        joined["team_id"] = joined.team_id_team
    aliases = read_aliases(alias_path)
    joined["playername"] = joined.playername.map(_clean_name)
    source_ids = joined.get("player_id", joined.get("playerid", pd.Series("", index=joined.index))).astype(str)
    joined["player_id"] = [value if value.startswith(("oe:player:", "pro:", "source:")) else "source:" + value if value else _identity_key(name) for value, name in zip(source_ids, joined.playername)]
    joined["identity_basis"] = ["source_player_id" if value else "source_playername_unverified" for value in source_ids]
    for alias in aliases.itertuples():
        mask = (joined.playername == alias.alias) & (joined.date >= alias.valid_from) & (joined.date < alias.valid_to)
        joined.loc[mask, "player_id"] = alias.canonical_id
        joined.loc[mask, "identity_basis"] = "operator_dated_alias_mapping"
    unique_players = joined.groupby("game_id").player_id.nunique()
    unique_champs = joined.groupby("game_id").champion.nunique()
    mark(unique_players[unique_players != 10].index, "duplicate_player_identity_within_game")
    mark(unique_champs[unique_champs != 10].index, "duplicate_champion_within_game")
    games = []
    first_pick_contradictory = 0
    groups = {gid: frame for gid, frame in joined.groupby("game_id", sort=False)}
    for gid, team in teams.groupby("game_id", sort=False):
        if gid in quarantined:
            continue
        group = groups.get(gid)
        if group is None:
            continue
        team = team.set_index("side")
        if sum(team.result) != 1:
            mark([gid], "opponent_results_not_complementary"); continue
        if team.team_id.nunique() != 2:
            mark([gid], "same_team_on_both_sides"); continue
        if any(team[col].nunique() != 1 for col in ("date", "league", "patch")):
            mark([gid], "inconsistent_game_context"); continue
        date = team.iloc[0].date
        lengths = pd.to_numeric(team.get("gamelength", pd.Series(dtype=float)), errors="coerce")
        length = float(lengths.max()) if len(lengths) and lengths.notna().any() else 0
        # Result availability is deliberately conservative: no same UTC-day
        # result enters any history; long games crossing midnight add a buffer.
        available = max(date.normalize() + pd.Timedelta(days=1), date + pd.Timedelta(seconds=max(0, length) + 3600))
        first = [_bool(team.loc[side].get("first_pick", "")) for side in SIDES]
        first_pick = "blue" if first == [1, 0] else "red" if first == [0, 1] else "unknown"
        if first in ([0, 0], [1, 1]):
            first_pick_contradictory += 1
        game = {"game_id": gid, "date": date, "available_at": available, "league": team.iloc[0].league, "patch": team.iloc[0].patch, "blue_win": int(team.loc["blue"].result), "first_pick_side": first_pick}
        for side in SIDES:
            row = team.loc[side]
            game[f"{side}_team_id"], game[f"{side}_team_name"] = row.team_id, row.team_name
            side_players = group[group.side == side].set_index("position")
            for role in ROLES:
                player = side_players.loc[role]
                for output, source in (("player_id", "player_id"), ("player_name", "playername"), ("champion", "champion")):
                    game[f"{side}_{role}_{output}"] = player[source]
            # Validate team pick sets when provided; never infer role from pick order.
            picks = [row.get(f"pick{i}", "") for i in range(1, 6)]
            if all(picks) and sorted(picks) != sorted(side_players.champion):
                mark([gid], "team_pick_player_champion_mismatch")
            for i in range(1, 6):
                value = str(row.get(f"ban{i}", "")).strip()
                game[f"{side}_ban{i}"] = "unknown" if value.lower() in {"", "none", "null", "nan", "n/a", "na", "unknown"} else value
        bans = [game[f"{side}_ban{i}"] for side in SIDES for i in range(1, 6) if game[f"{side}_ban{i}"] != "unknown"]
        picks = {game[f"{side}_{role}_champion"] for side in SIDES for role in ROLES}
        if len(bans) != len(set(bans)):
            mark([gid], "duplicate_known_ban")
        if set(bans) & picks:
            mark([gid], "banned_champion_picked")
        if gid not in quarantined:
            games.append(game)
    result = pd.DataFrame(games)
    if len(result):
        result = result.sort_values(["date", "game_id"]).reset_index(drop=True)
    else:
        result = pd.DataFrame(columns=["game_id", "date", "available_at", "league", "patch", "blue_win", "first_pick_side"])
    eligible = joined[joined.game_id.isin(set(result.game_id))].copy()
    registry = eligible.groupby(["player_id", "playername", "identity_basis"], as_index=False).agg(first_observed=("date", "min"), last_observed=("date", "max"), observed_games=("game_id", "nunique")).rename(columns={"playername": "alias"})
    # Stints are contiguous observed team sequences, not fabricated contract dates.
    stints = []
    for pid, group in eligible.sort_values(["date", "game_id"]).groupby("player_id"):
        active = None
        for row in group.itertuples():
            if active is None or active["team_id"] != row.team_id:
                if active is not None:
                    stints.append(active)
                active = {"player_id": pid, "team_id": row.team_id, "team_name": row.team_name, "observed_from": row.date, "last_observed": row.date, "observed_games": 0, "date_basis": "observations_only_not_official_transfer_dates"}
            active["last_observed"] = row.date; active["observed_games"] += 1
        if active is not None:
            stints.append(active)
    quarantine = pd.DataFrame([{"game_id": key, "reasons": "|".join(sorted(value))} for key, value in sorted(quarantined.items()) if key not in future_games], columns=["game_id", "reasons"])
    reason_counts = {}
    for value in quarantine.reasons:
        for reason in value.split("|"):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    ban_cols = [f"{side}_ban{i}" for side in SIDES for i in range(1, 6)]
    report = {"generated_at": _now(), "raw_player_rows": raw_players, "raw_team_rows": raw_teams, "raw_distinct_games": len(raw_game_ids), "as_of": str(_utc(as_of)) if as_of is not None else None, "excluded_at_or_after_as_of_games": len(future_games), "exact_duplicate_player_rows_removed": duplicate_players_removed, "exact_duplicate_team_rows_removed": duplicate_teams_removed, "accepted_games": len(result), "quarantined_games": len(quarantine), "quarantine_reasons": reason_counts, "data_start": str(result.date.min()) if len(result) else None, "data_cutoff": str(result.date.max()) if len(result) else None, "results_available_through": str(result.available_at.max()) if len(result) else None, "league_counts": result.league.value_counts().to_dict(), "year_counts": result.date.dt.year.value_counts().sort_index().to_dict() if len(result) else {}, "patch_counts": result.patch.value_counts().to_dict(), "missing_ban_slots": int(result[ban_cols].eq("unknown").sum().sum()) if len(result) else 0, "unknown_first_pick_games": int(result.first_pick_side.eq("unknown").sum()), "contradictory_first_pick_pairs_seen": first_pick_contradictory, "identity_coverage": {"unique_local_or_source_ids": int(registry.player_id.nunique()), "player_rows_by_identity_basis": eligible.identity_basis.value_counts().to_dict(), "limitation": "ChainCC exports display names without immutable player IDs. pro: UUIDs are persistent deterministic local IDs; exact-name continuity is unverified across people/renames. No fuzzy merging. Dated aliases require external verification."}, "availability_policy": "max(next UTC midnight, source date + gamelength seconds + 1 hour); history must satisfy date < as_of and available_at < as_of", "timestamp_caveat": "Source date timezone/start/end semantics and original publication timestamps are not guaranteed; UTC interpretation plus conservative availability is a retrospective approximation, not point-in-time vendor archive.", "postgame_columns": "Only result retained as target. gamelength used solely for conservative label availability; no KDA/gold/damage/objective statistics enter current-game features."}
    return result, report, registry, pd.DataFrame(stints), quarantine


def normalize_data(raw_dir: str | Path, output_dir: str | Path, as_of=None, alias_path=None) -> dict:
    raw_dir, output_dir = Path(raw_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    players, teams, evidence = _read_sources(raw_dir)
    games, report, registry, stints, quarantine = normalize_frames(players, teams, as_of=as_of, alias_path=alias_path)
    report["sources"] = evidence
    manifest_path = raw_dir / "sources.json"
    report["source_manifest"] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"status": "unverified_manual_files", "warning": "No sources.json: original source/license/download provenance not verified"}
    report["dataset_hash"] = hashlib.sha256("\n".join(entry["sha256"] for entry in evidence).encode()).hexdigest()
    report["alias_mapping_sha256"] = _sha256(Path(alias_path)) if alias_path else None
    games.to_parquet(output_dir / "games.parquet", index=False)
    registry.to_csv(output_dir / "player_registry.csv", index=False)
    stints.to_csv(output_dir / "player_team_stints.csv", index=False)
    quarantine.to_csv(output_dir / "quarantine.csv", index=False)
    _write_json(output_dir / "quality_report.json", report)
    db = duckdb.connect(str(output_dir / "games.duckdb"))
    try:
        for name, frame in (("games", games), ("player_registry", registry), ("player_team_stints", stints), ("quarantine", quarantine)):
            if not len(frame.columns):
                continue
            db.register("incoming", frame)
            db.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM incoming")
            db.unregister("incoming")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS game_id_unique ON games(game_id)")
    finally:
        db.close()
    return report


def load_games(path: str | Path, as_of=None) -> pd.DataFrame:
    """Read only records strictly earlier than as_of using a storage predicate."""
    path = Path(path)
    if path.is_dir():
        path = path / "games.parquet"
    params = [] if as_of is None else [_utc(as_of).to_pydatetime(), _utc(as_of).to_pydatetime()]
    where = "" if as_of is None else " WHERE date < ? AND available_at < ?"
    if path.suffix == ".duckdb":
        db = duckdb.connect(str(path), read_only=True)
        try:
            result = db.execute("SELECT * FROM games" + where + " ORDER BY date, game_id", params).fetchdf()
        finally:
            db.close()
    else:
        with duckdb.connect() as db:
            result = db.execute("SELECT * FROM read_parquet(?)" + where + " ORDER BY date, game_id", [str(path)] + params).fetchdf()
    for col in ("date", "available_at"):
        result[col] = pd.to_datetime(result[col], utc=True)
    if result.game_id.duplicated().any():
        raise ValueError("Canonical game table contains duplicate game_id")
    return result
