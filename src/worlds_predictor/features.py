"""Point-in-time features derived exclusively from previously available results.

The only Bayesian prior below is the symmetric Beta prior used to regularize
small samples. It is not a manually scored champion rating or a prediction.
Every feature is a statistic learned from real earlier games, or a pre-game ID.
"""

from __future__ import annotations

from collections import defaultdict, deque
from itertools import combinations
from typing import Any, Hashable

import numpy as np
import pandas as pd

ROLES = ("top", "jng", "mid", "bot", "sup")
SIDES = ("blue", "red")
UNKNOWN = "__UNKNOWN__"
FEATURE_VERSION = "point-in-time-v1"
RECENT_WINDOW = 20
SMOOTHING = {
    "team": 10.0,
    "player": 10.0,
    "champion": 20.0,
    "player_champion": 10.0,
    "matchup": 20.0,
    "synergy": 30.0,
    "patch_champion": 20.0,
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value) or not str(value).strip():
        return UNKNOWN
    text = str(value).strip()
    return UNKNOWN if text.casefold() in {"unknown", "__unknown__"} else text


def _timestamp(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("A valid point-in-time timestamp is required")
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def feature_columns(level: str) -> tuple[list[str], list[str]]:
    """Return numeric and categorical columns; A is nested in B, B in C."""
    level = level.upper()
    if level not in {"A", "B", "C"}:
        raise ValueError("Feature level must be A, B or C")
    numeric = ["historical_blue_win_rate", "historical_game_count"]
    categorical = ["league", "blue_team_id", "red_team_id", "first_pick_side"]
    for side in SIDES:
        numeric.extend(
            f"{side}_team_{suffix}"
            for suffix in ("win_rate", "games", "recent_win_rate", "recent_games")
        )
    numeric.extend(["team_win_rate_diff", "team_recent_win_rate_diff"])
    if level in {"B", "C"}:
        for side in SIDES:
            for role in ROLES:
                prefix = f"{side}_{role}"
                categorical.append(f"{prefix}_player_id")
                numeric.extend(
                    f"{prefix}_player_{suffix}"
                    for suffix in ("win_rate", "games", "recent_win_rate", "recent_games")
                )
        numeric.extend(["player_win_rate_diff", "player_recent_win_rate_diff"])
    if level == "C":
        categorical.append("patch")
        for side in SIDES:
            categorical.extend(f"{side}_ban{i}" for i in range(1, 6))
            numeric.append(f"{side}_known_bans")
            for role in ROLES:
                prefix = f"{side}_{role}"
                categorical.append(f"{prefix}_champion")
                for kind in ("champion", "player_champion", "matchup", "patch_champion"):
                    numeric.extend([f"{prefix}_{kind}_win_rate", f"{prefix}_{kind}_games"])
            numeric.extend(
                f"{side}_synergy_{suffix}"
                for suffix in ("mean_win_rate", "mean_games", "min_games", "known_pairs")
            )
        numeric.extend(f"{kind}_win_rate_diff" for kind in ("champion", "player_champion", "matchup", "patch_champion", "synergy"))
    return numeric, categorical


class _Counters:
    def __init__(self, prior_strength: float, recent: bool = False):
        self.strength = prior_strength
        self.values: dict[Hashable, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.recent = defaultdict(lambda: deque(maxlen=RECENT_WINDOW)) if recent else None

    def update(self, key: Hashable, outcome: float) -> None:
        wins_count = self.values[key]
        wins_count[0] += outcome
        wins_count[1] += 1.0
        if self.recent is not None:
            self.recent[key].append(outcome)

    def get(self, key: Hashable) -> tuple[float, float]:
        wins, count = self.values.get(key, (0.0, 0.0))
        return (wins + self.strength / 2.0) / (count + self.strength), count

    def get_recent(self, key: Hashable) -> tuple[float, float]:
        values = self.recent.get(key, ()) if self.recent is not None else ()
        return (sum(values) + self.strength / 2.0) / (len(values) + self.strength), float(len(values))


class HistoricalState:
    """State updated only by the caller's strict availability-time sweep."""

    def __init__(self):
        self.counters = {
            name: _Counters(strength, recent=name in {"team", "player"})
            for name, strength in SMOOTHING.items()
        }
        self.games = 0
        self.blue_wins = 0
        self.latest_available_at: pd.Timestamp | None = None
        self.latest_date: pd.Timestamp | None = None
        self.league_counts: dict[str, int] = defaultdict(int)
        self.patch_counts: dict[str, int] = defaultdict(int)

    @staticmethod
    def _synergy_key(role1: str, champion1: str, role2: str, champion2: str) -> tuple:
        return tuple(sorted(((role1, champion1), (role2, champion2))))

    def update(self, game: dict) -> None:
        outcome = int(game["blue_win"])
        if outcome not in {0, 1}:
            raise ValueError("Historical blue_win must be binary")
        self.games += 1
        self.blue_wins += outcome
        available_at = _timestamp(game["available_at"])
        date = _timestamp(game["date"])
        self.latest_available_at = max(self.latest_available_at, available_at) if self.latest_available_at else available_at
        self.latest_date = max(self.latest_date, date) if self.latest_date else date
        patch = _text(game.get("patch"))
        self.league_counts[_text(game.get("league"))] += 1
        self.patch_counts[patch] += 1
        for side in SIDES:
            other_side = "red" if side == "blue" else "blue"
            win = outcome if side == "blue" else 1 - outcome
            self.counters["team"].update(_text(game.get(f"{side}_team_id")), win)
            for role in ROLES:
                player = _text(game.get(f"{side}_{role}_player_id"))
                champion = _text(game.get(f"{side}_{role}_champion"))
                enemy = _text(game.get(f"{other_side}_{role}_champion"))
                self.counters["player"].update((role, player), win)
                self.counters["champion"].update((role, champion), win)
                self.counters["player_champion"].update((role, player, champion), win)
                self.counters["matchup"].update((role, champion, enemy), win)
                self.counters["patch_champion"].update((patch, role, champion), win)
            for role1, role2 in combinations(ROLES, 2):
                key = self._synergy_key(role1, _text(game.get(f"{side}_{role1}_champion")), role2, _text(game.get(f"{side}_{role2}_champion")))
                self.counters["synergy"].update(key, win)

    def features(self, game: dict) -> dict:
        # Explicit allowlist: result, KDA, gold, damage and other post-game fields
        # in the input cannot enter the current feature vector.
        row: dict[str, Any] = {
            "league": _text(game.get("league")),
            "patch": _text(game.get("patch")),
            "first_pick_side": _text(game.get("first_pick_side", "unknown")),
            "historical_blue_win_rate": (self.blue_wins + 10.0) / (self.games + 20.0),
            "historical_game_count": float(self.games),
        }
        for side in SIDES:
            other_side = "red" if side == "blue" else "blue"
            team = _text(game.get(f"{side}_team_id"))
            row[f"{side}_team_id"] = team
            row[f"{side}_team_win_rate"], row[f"{side}_team_games"] = self.counters["team"].get(team)
            row[f"{side}_team_recent_win_rate"], row[f"{side}_team_recent_games"] = self.counters["team"].get_recent(team)
            for role in ROLES:
                prefix = f"{side}_{role}"
                player = _text(game.get(f"{prefix}_player_id"))
                champion = _text(game.get(f"{prefix}_champion"))
                enemy = _text(game.get(f"{other_side}_{role}_champion"))
                row[f"{prefix}_player_id"] = player
                row[f"{prefix}_champion"] = champion
                row[f"{prefix}_player_win_rate"], row[f"{prefix}_player_games"] = self.counters["player"].get((role, player))
                row[f"{prefix}_player_recent_win_rate"], row[f"{prefix}_player_recent_games"] = self.counters["player"].get_recent((role, player))
                keys = {
                    "champion": (role, champion),
                    "player_champion": (role, player, champion),
                    "matchup": (role, champion, enemy),
                    "patch_champion": (row["patch"], role, champion),
                }
                for kind, key in keys.items():
                    row[f"{prefix}_{kind}_win_rate"], row[f"{prefix}_{kind}_games"] = self.counters[kind].get(key)
            synergies = [
                self.counters["synergy"].get(self._synergy_key(role1, row[f"{side}_{role1}_champion"], role2, row[f"{side}_{role2}_champion"]))
                for role1, role2 in combinations(ROLES, 2)
            ]
            row[f"{side}_synergy_mean_win_rate"] = float(np.mean([v[0] for v in synergies]))
            counts = [v[1] for v in synergies]
            row[f"{side}_synergy_mean_games"] = float(np.mean(counts))
            row[f"{side}_synergy_min_games"] = float(min(counts))
            row[f"{side}_synergy_known_pairs"] = float(sum(c > 0 for c in counts))
            for i in range(1, 6):
                row[f"{side}_ban{i}"] = _text(game.get(f"{side}_ban{i}"))
            row[f"{side}_known_bans"] = float(sum(row[f"{side}_ban{i}"] != UNKNOWN for i in range(1, 6)))
        row["team_win_rate_diff"] = row["blue_team_win_rate"] - row["red_team_win_rate"]
        row["team_recent_win_rate_diff"] = row["blue_team_recent_win_rate"] - row["red_team_recent_win_rate"]
        for kind in ("player", "player_recent", "champion", "player_champion", "matchup", "patch_champion"):
            row[f"{kind}_win_rate_diff"] = float(np.mean([row[f"blue_{r}_{kind}_win_rate"] - row[f"red_{r}_{kind}_win_rate"] for r in ROLES]))
        row["synergy_win_rate_diff"] = row["blue_synergy_mean_win_rate"] - row["red_synergy_mean_win_rate"]
        return row

    def coverage(self, game: dict, features: dict, cutoff: pd.Timestamp) -> dict:
        players = [f"{s}_{r}" for s in SIDES for r in ROLES]
        return {
            "history_games": self.games,
            "effective_as_of": cutoff.isoformat(),
            "latest_history_game_time": self.latest_date.isoformat() if self.latest_date is not None else None,
            "latest_history_available_at": self.latest_available_at.isoformat() if self.latest_available_at is not None else None,
            "league_history_games": self.league_counts.get(_text(game.get("league")), 0),
            "patch_history_games": self.patch_counts.get(_text(game.get("patch")), 0),
            "unknown_teams": [features[f"{s}_team_id"] for s in SIDES if features[f"{s}_team_games"] == 0],
            "unknown_players_in_role": [features[f"{p}_player_id"] for p in players if features[f"{p}_player_games"] == 0],
            "unknown_champions_in_role": [features[f"{p}_champion"] for p in players if features[f"{p}_champion_games"] == 0],
            "player_champion_games": {p: int(features[f"{p}_player_champion_games"]) for p in players},
            "matchup_games": {p: int(features[f"{p}_matchup_games"]) for p in players},
            "missing_ban_slots": int(10 - features["blue_known_bans"] - features["red_known_bans"]),
            "first_pick_side_observed": features["first_pick_side"] not in {UNKNOWN, "unknown"},
            "smoothing": SMOOTHING,
            "recent_window_games": RECENT_WINDOW,
            "feature_version": FEATURE_VERSION,
        }


def _prepare(games: pd.DataFrame, as_of: Any = None) -> pd.DataFrame:
    required = {"game_id", "date", "available_at", "blue_win"}
    missing = required - set(games.columns)
    if missing:
        raise ValueError(f"Missing required history columns: {sorted(missing)}")
    data = games.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True, errors="raise")
    data["available_at"] = pd.to_datetime(data["available_at"], utc=True, errors="raise")
    if as_of is not None:
        cutoff = _timestamp(as_of)
        data = data.loc[(data["date"] < cutoff) & (data["available_at"] < cutoff)].copy()
    if data[["date", "available_at"]].isna().any().any():
        raise ValueError("Missing history timestamps are not safe for pre-game features")
    if (data["available_at"] < data["date"]).any():
        raise ValueError("A result cannot be available before its game date")
    if data["game_id"].isna().any() or data["game_id"].astype(str).duplicated().any():
        raise ValueError("History must contain exactly one row per unique game_id")
    if not data["blue_win"].isin([0, 1]).all():
        raise ValueError("Historical blue_win must be binary")
    data["game_id"] = data["game_id"].astype(str)
    return data.sort_values(["date", "game_id"], kind="stable").reset_index(drop=True)


def build_feature_table(games: pd.DataFrame, as_of: Any = None) -> pd.DataFrame:
    """Emit one vector per game, before ingesting results available at that time.

    A game at time T cannot see results whose availability is T, including games
    with the same timestamp. as_of also excludes labels not yet available then.
    Later test-window outcomes can inform still-later test games once observed:
    this is chronological, rolling-origin pre-game evaluation, not frozen-history.
    """
    data = _prepare(games, as_of)
    events = data.sort_values(["available_at", "game_id"], kind="stable").to_dict("records")
    state = HistoricalState()
    cursor = 0
    rows = []
    for game in data.to_dict("records"):
        date = _timestamp(game["date"])
        while cursor < len(events) and events[cursor]["available_at"] < date:
            state.update(events[cursor])
            cursor += 1
        features = state.features(game)
        features.update({name: game[name] for name in ("game_id", "date", "available_at", "blue_win")})
        rows.append(features)
    numeric, categorical = feature_columns("C")
    return pd.DataFrame(rows, columns=["game_id", "date", "available_at", "blue_win", *numeric, *categorical])


def features_for_game(history: pd.DataFrame, game: dict, as_of: Any) -> tuple[dict, dict]:
    """Generate inference features without using the target's outcome or future."""
    cutoff = _timestamp(as_of)
    if game.get("date") is not None:
        cutoff = min(cutoff, _timestamp(game["date"]))
    data = _prepare(history, cutoff)
    if game.get("game_id") is not None:
        data = data.loc[data["game_id"] != str(game["game_id"])]
    state = HistoricalState()
    for prior in data.sort_values(["available_at", "game_id"], kind="stable").to_dict("records"):
        state.update(prior)
    features = state.features(game)
    return features, state.coverage(game, features, cutoff)
