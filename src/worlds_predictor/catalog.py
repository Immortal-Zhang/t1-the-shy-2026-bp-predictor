"""Verified static champion metadata and point-in-time professional observations.

Official event participation is a dated source snapshot. A roster assembled from
match observations is deliberately never labelled a current official starting
roster. No table here supplies a synthetic prediction or skill rating.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import unicodedata

import pandas as pd

from .context import public_patch
from .data import load_games

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = PROJECT_ROOT / "data" / "catalog"
DEFAULT_GAMES = PROJECT_ROOT / "data" / "processed" / "games.parquet"
PARTICIPANTS = PROJECT_ROOT / "configs" / "worlds2026_participants.json"
ROLES = ("top", "jng", "mid", "bot", "sup")
SOURCE_URL = "https://chaincc.lol/free/data/"


def _cutoff(value) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError("as_of must be a valid timezone-aware timestamp")
    return result.tz_convert("UTC")


def _key(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


@lru_cache(maxsize=8)
def _games_cached(path: str, mtime: int, cutoff: str) -> pd.DataFrame:
    return load_games(path, as_of=cutoff)


def historical_games(games_path=DEFAULT_GAMES, as_of=None) -> pd.DataFrame:
    if as_of is None:
        raise ValueError("Explicit as_of required")
    path = Path(games_path)
    return _games_cached(str(path.resolve()), path.stat().st_mtime_ns, _cutoff(as_of).isoformat())


@lru_cache(maxsize=4)
def _champions_cached(en_mtime: int, zh_mtime: int) -> list[dict]:
    en = json.loads((CATALOG_DIR / "champion-en_US.json").read_text())["data"]
    zh = json.loads((CATALOG_DIR / "champion-zh_CN.json").read_text())["data"]
    result = []
    for champion_id, row in en.items():
        chinese = zh.get(champion_id, {})
        result.append({"id": champion_id, "key": row["key"], "name_en": row["name"],
                       "name_zh": chinese.get("name", row["name"]), "title_zh": chinese.get("title", ""),
                       "image_url": f"https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/{row['image']['full']}",
                       "tags": row.get("tags", []), "roles": [], "role_counts": {},
                       "role_source": "historical professional role observations strictly before as_of"})
    return result


def champion_rows() -> list[dict]:
    return _champions_cached((CATALOG_DIR / "champion-en_US.json").stat().st_mtime_ns,
                             (CATALOG_DIR / "champion-zh_CN.json").stat().st_mtime_ns)


def canonical_champion(value: str) -> str:
    """Resolve exact English, Chinese, title or Data Dragon ID; never guess."""
    lookup = {}
    for row in champion_rows():
        for alias in (row["id"], row["name_en"], row["name_zh"], row["title_zh"]):
            if alias:
                lookup.setdefault(_key(alias), set()).add(row["name_en"])
    matches = lookup.get(_key(value), set())
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous champion: {value}")
    return next(iter(matches))


def get_worlds_rules() -> dict:
    path = CATALOG_DIR / "worlds_rules.json"
    if not path.exists():
        return {"verified": False, "fearless_mode": None, "source_url": None,
                "description": "尚未取得可核验的规则快照，不能自动执行 Fearless 限制。"}
    return json.loads(path.read_text())


def _participants() -> dict:
    return json.loads(PARTICIPANTS.read_text())


def _participation_availability(official: dict, as_of) -> dict:
    """Do not reveal official qualification before its dated announcement.

    The source currently provides a day, not a clock time. The next UTC midnight
    is therefore a conservative availability boundary, with the same strict
    before-as_of convention as historical results. This remains a current
    snapshot, not proof that its content never changed after publication.
    """
    boundary = official.get("qualification_available_at")
    if boundary is None:
        published = official.get("source_published_at")
        if published:
            boundary = _cutoff(published)
        elif official.get("source_published_date"):
            boundary = pd.Timestamp(official["source_published_date"], tz="UTC") + pd.Timedelta(days=1)
        else:
            boundary = _cutoff(official["retrieved_at"])
    available_at = _cutoff(boundary)
    available = available_at < _cutoff(as_of)
    return {"qualification_available_at": available_at.isoformat(),
            "qualification_status": "current_official_snapshot" if available else "not_available_before_publication",
            "qualification_available": available,
            "qualification_notice": (
                "官方参赛公告已到发布时间；这仍是当前内容快照，不能证明公告发布后未曾修订。"
                if available else "指定 as_of 尚未晚于官方参赛公告的可用时间，不展示未来参赛资格。")}


def catalog_payload(as_of, games_path=DEFAULT_GAMES) -> dict:
    games = historical_games(games_path, as_of)
    role_counts = {role: Counter() for role in ROLES}
    for role in ROLES:
        for side in ("blue", "red"):
            role_counts[role].update(games[f"{side}_{role}_champion"].astype(str))
    champions = []
    for original in champion_rows():
        row = dict(original)
        row["role_counts"] = {role: int(role_counts[role][row["name_en"]]) for role in ROLES}
        row["roles"] = [role for role in ROLES if row["role_counts"][role] > 0]
        champions.append(row)
    manifest = json.loads((CATALOG_DIR / "manifest.json").read_text())
    official = _participants()
    qualification = _participation_availability(official, as_of)
    return {"as_of": _cutoff(as_of).isoformat(), "champions": champions,
            "worlds": {"event": "Worlds 2026", "patch": "26.20", "rules": get_worlds_rules(),
                       "participant_count": len(official["teams"]) if qualification["qualification_available"] else 0,
                       **qualification},
            "provenance": {**manifest, "history_games": len(games),
                           "history_cutoff": games.date.max().isoformat() if len(games) else None,
                           "identity_notice": "选手 ID 是来源职业名称映射的本地稳定标识，并非已全部核验的官方人物 ID。"}}


def _team_observations(games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side in ("blue", "red"):
        frame = games[["game_id", "date", "league", f"{side}_team_id", f"{side}_team_name"]].rename(
            columns={f"{side}_team_id": "team_id", f"{side}_team_name": "name"})
        rows.append(frame)
    return pd.concat(rows, ignore_index=True).sort_values(["date", "game_id"])


def team_list(as_of, games_path=DEFAULT_GAMES, worlds_only=True, query="") -> dict:
    games = historical_games(games_path, as_of)
    observations = _team_observations(games)
    official = _participants()
    qualification = _participation_availability(official, as_of)
    known = {row["team_id"]: row for row in official["teams"] if row.get("team_id")} if qualification["qualification_available"] else {}
    teams = []
    for team_id, group in observations.groupby("team_id", sort=False):
        entry = known.get(team_id)
        if worlds_only and entry is None:
            continue
        last = group.iloc[-1]
        name = entry["name"] if entry else str(last["name"])
        region = entry["region"] if entry else str(group.league.mode().iloc[0])
        # For unregistered teams a neutral short label is a UI abbreviation,
        # never represented as an officially licensed team mark.
        code = entry["code"] if entry else "".join(word[0] for word in name.split())[:5].upper()
        if query and _key(query) not in _key(" ".join([name, code, team_id, str(last["name"])])):
            continue
        teams.append({"team_id": team_id, "name": name, "source_name": str(last["name"]),
                      "code": code, "region": region, "logo_url": None,
                      "logo_notice": "未取得可复用的战队标志授权来源，显示中性文字缩写。",
                      "worlds_2026": entry is not None,
                      "participation_status": "official_confirmed" if entry else "historical_observed",
                      "source_url": official["source_url"] if entry else SOURCE_URL,
                      "updated_at": official["retrieved_at"] if entry else last.date.isoformat(),
                      "history_games": int(group.game_id.nunique()), "last_observed": last.date.isoformat()})
    teams.sort(key=lambda row: (row["region"], row["code"]))
    return {"as_of": _cutoff(as_of).isoformat(), "teams": teams, "returned": len(teams),
            "participation_source": official["source_url"], "participation_updated_at": official["retrieved_at"],
            **qualification,
            "notice": ("参赛资格使用当前官方公告快照；历史场次、阵容及表现严格截断至 as_of。公告快照不是历史时点资格归档。"
                       if qualification["qualification_available"] else qualification["qualification_notice"])}


def _player_observations(games: pd.DataFrame, player_id: str, role: str) -> pd.DataFrame:
    frames = []
    for side in ("blue", "red"):
        mask = games[f"{side}_{role}_player_id"].eq(player_id)
        frame = games.loc[mask, ["game_id", "date", "blue_win", f"{side}_{role}_champion"]].copy()
        frame["win"] = frame.blue_win if side == "blue" else 1 - frame.blue_win
        frame = frame.rename(columns={f"{side}_{role}_champion": "champion"})
        frames.append(frame[["game_id", "date", "win", "champion"]])
    return pd.concat(frames).sort_values(["date", "game_id"], kind="stable")


def team_roster(team_id: str, as_of, games_path=DEFAULT_GAMES) -> dict:
    games = historical_games(games_path, as_of)
    candidates = games[games.blue_team_id.eq(team_id) | games.red_team_id.eq(team_id)]
    if candidates.empty:
        raise LookupError("该战队在 as_of 前没有可用阵容记录。")
    game = candidates.iloc[-1]
    side = "blue" if game.blue_team_id == team_id else "red"
    players = []
    for role in ROLES:
        player_id = game[f"{side}_{role}_player_id"]
        observations = _player_observations(games, player_id, role)
        recent = observations.tail(20)
        champions = observations.groupby("champion").win.agg(["size", "mean"]).sort_values(["size", "mean"], ascending=False).head(5)
        players.append({"role": role, "player_id": player_id, "name": game[f"{side}_{role}_player_name"],
                        "team_id": team_id, "history_games": len(observations), "recent_games": len(recent),
                        "recent_win_rate": float(recent.win.mean()) if len(recent) else None,
                        "best_champions": [{"champion": name, "games": int(row["size"]), "win_rate": float(row["mean"])} for name, row in champions.iterrows()],
                        "identity_basis": "source_playername_unverified"})
    return {"team_id": team_id, "as_of": _cutoff(as_of).isoformat(), "roster_status": "observed_last_match",
            "observed_at": game.date.isoformat(), "game_id": game.game_id, "source_url": SOURCE_URL,
            "notice": "这是截止时间前最近一场实际出场阵容，不是当前首发或世界赛注册名单确认；请核实并按需更换选手。",
            "players": players}


def game_request(row) -> dict:
    """Replay includes draft context only, never the actual result."""
    date = row["date"].isoformat()
    result = {"game_id": row["game_id"], "as_of": date, "scheduled_start": date,
              "league": "Worlds" if row["league"] == "WLDs" else row["league"],
              "patch": public_patch(row["patch"]), "first_pick_side": row["first_pick_side"]}
    for side in ("blue", "red"):
        result[side] = {"team_id": row[f"{side}_team_id"], "players": [
            {"role": role, "player_id": row[f"{side}_{role}_player_id"], "champion": row[f"{side}_{role}_champion"]} for role in ROLES],
            "bans": [None if row[f"{side}_ban{i}"] in ("unknown", "__UNKNOWN__", "") else row[f"{side}_ban{i}"] for i in range(1, 6)]}
    return result


def match_list(as_of, games_path=DEFAULT_GAMES, worlds_only=True, limit=100) -> dict:
    games = historical_games(games_path, as_of)
    if worlds_only:
        # Source WLDs also contains regional qualifier games. The event patch
        # and official start date are both required for actual Worlds games.
        games = games[games.league.eq("WLDs") & games.patch.eq("16.20") & (games.date >= pd.Timestamp("2026-10-15T00:00:00Z"))]
    selected = games.sort_values(["date", "game_id"], ascending=False).head(limit)
    matches = []
    for _, row in selected.iterrows():
        matches.append({"game_id": row.game_id, "date": row.date.isoformat(), "league": row.league,
                        "patch": public_patch(row.patch), "blue_team_id": row.blue_team_id,
                        "blue_team_name": row.blue_team_name, "red_team_id": row.red_team_id,
                        "red_team_name": row.red_team_name, "blue_win": int(row.blue_win),
                        "player_names": {row[f"{side}_{role}_player_id"]: row[f"{side}_{role}_player_name"] for side in ("blue", "red") for role in ROLES},
                        "source_url": SOURCE_URL, "request": game_request(row)})
    return {"as_of": _cutoff(as_of).isoformat(), "matches": matches, "returned": len(matches),
            "available_games": len(games), "source_url": SOURCE_URL,
            "notice": "历史实际结果仅用于展示和赛后对比，重放请求不包含结果；Worlds 列表排除了同标签的地区资格赛。"}
