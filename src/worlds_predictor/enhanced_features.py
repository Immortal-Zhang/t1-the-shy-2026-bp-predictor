"""Additional observed-history features for the aggressive-mode challenger.

No tactical hero ratings are supplied. All numbers are either earlier outcomes,
sample counts, their time decay, or interactions between those measured values.
The frozen first-generation feature implementation is deliberately unmodified.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Hashable

import numpy as np
import pandas as pd

from .features import HistoricalState, ROLES, SIDES, _prepare, _text, _timestamp, feature_columns

VERSION = "observed-form-pairs-v1"
DECAY_HALF_LIFE_DAYS = 90.0
PAIR_ROLES = {"mid_jungle": ("jng", "mid"), "bot_support": ("bot", "sup")}


class OutcomeCounter:
    def __init__(self, strength: float = 20.0):
        self.strength = strength
        self.counts = defaultdict(lambda: [0.0, 0.0])
        self.recent = defaultdict(lambda: deque(maxlen=20))

    def update(self, key: Hashable, outcome: int):
        self.counts[key][0] += outcome
        self.counts[key][1] += 1
        self.recent[key].append(outcome)

    def get(self, key: Hashable, recent=False):
        if recent:
            values = self.recent.get(key, ())
            wins, count = sum(values), len(values)
        else:
            wins, count = self.counts.get(key, (0, 0))
        return (wins + self.strength / 2) / (count + self.strength), float(count)


class DecayedOutcomeCounter:
    """Effective outcome counts with an exponential 90-day availability decay."""
    def __init__(self, strength=10.0):
        self.strength = strength
        self.values = {}

    def get(self, key, at):
        record = self.values.get(key)
        if record is None:
            return 0.5, 0.0, 3650.0
        wins, count, previous = record
        age = max(0.0, (at - previous).total_seconds() / 86400)
        decay = np.exp2(-age / DECAY_HALF_LIFE_DAYS)
        wins, count = wins * decay, count * decay
        return (wins + self.strength / 2) / (count + self.strength), float(count), age

    def update(self, key, outcome, at):
        record = self.values.get(key)
        if record is None:
            self.values[key] = [float(outcome), 1.0, at]
            return
        wins, count, previous = record
        if at < previous:
            raise ValueError("Decay updates must follow result availability time")
        decay = np.exp2(-(at - previous).total_seconds() / 86400 / DECAY_HALF_LIFE_DAYS)
        self.values[key] = [wins * decay + outcome, count * decay + 1, at]


class EnhancedHistoricalState(HistoricalState):
    def __init__(self):
        super().__init__()
        self.observed = {name: OutcomeCounter(strength) for name, strength in {
            "player_champion": 10.0, "matchup": 20.0, "player_patch": 15.0,
            "player_champion_patch": 20.0, "team_patch": 15.0,
            "duo_champions": 30.0, "duo_patch": 30.0, "duo_players": 20.0,
            "roster": 20.0, "head_to_head": 20.0,
        }.items()}
        self.decayed = {name: DecayedOutcomeCounter() for name in ("team", "player")}

    @staticmethod
    def keys(game, side):
        other = "red" if side == "blue" else "blue"
        patch, team = _text(game.get("patch")), _text(game.get(f"{side}_team_id"))
        yield "team_patch", "team_patch", (team, patch), False
        yield "roster", "roster", (team, tuple(_text(game.get(f"{side}_{r}_player_id")) for r in ROLES)), False
        yield "head_to_head", "head_to_head", (team, _text(game.get(f"{other}_team_id"))), False
        for role in ROLES:
            player, champion = _text(game.get(f"{side}_{role}_player_id")), _text(game.get(f"{side}_{role}_champion"))
            enemy = _text(game.get(f"{other}_{role}_champion"))
            yield f"{role}_player_champion_recent", "player_champion", (role, player, champion), True
            yield f"{role}_matchup_recent", "matchup", (role, champion, enemy), True
            yield f"{role}_player_patch", "player_patch", (patch, role, player), False
            yield f"{role}_player_champion_patch", "player_champion_patch", (patch, role, player, champion), False
        for label, roles in PAIR_ROLES.items():
            champions = tuple((r, _text(game.get(f"{side}_{r}_champion"))) for r in roles)
            players = tuple((r, _text(game.get(f"{side}_{r}_player_id"))) for r in roles)
            yield label, "duo_champions", champions, False
            yield f"{label}_recent", "duo_champions", champions, True
            yield f"{label}_patch", "duo_patch", (patch, champions), False
            yield f"{label}_players", "duo_players", players, False

    def update(self, game):
        super().update(game)
        available_at = _timestamp(game["available_at"])
        for side in SIDES:
            outcome = int(game["blue_win"]) if side == "blue" else 1 - int(game["blue_win"])
            self.decayed["team"].update(_text(game.get(f"{side}_team_id")), outcome, available_at)
            for role in ROLES:
                self.decayed["player"].update((role, _text(game.get(f"{side}_{role}_player_id"))), outcome, available_at)
            updated = set()
            for _, kind, key, _ in self.keys(game, side):
                # The full and recent view of a duo share exactly one observation.
                if (kind, key) not in updated:
                    self.observed[kind].update(key, outcome)
                    updated.add((kind, key))

    def features(self, game):
        row = super().features(game)
        at = _timestamp(game.get("_feature_time", game["date"]))
        for side in SIDES:
            for suffix, value in zip(("win_rate", "effective_games", "inactive_days"), self.decayed["team"].get(_text(game.get(f"{side}_team_id")), at)):
                row[f"{side}_team_decay_{suffix}"] = value
            row[f"{side}_team_form_change"] = row[f"{side}_team_recent_win_rate"] - row[f"{side}_team_win_rate"]
            for role in ROLES:
                key = (role, _text(game.get(f"{side}_{role}_player_id")))
                for suffix, value in zip(("win_rate", "effective_games", "inactive_days"), self.decayed["player"].get(key, at)):
                    row[f"{side}_{role}_player_decay_{suffix}"] = value
                row[f"{side}_{role}_player_form_change"] = row[f"{side}_{role}_player_recent_win_rate"] - row[f"{side}_{role}_player_win_rate"]
            for prefix, kind, key, recent in self.keys(game, side):
                rate, count = self.observed[kind].get(key, recent)
                row[f"{side}_{prefix}_win_rate"] = rate
                row[f"{side}_{prefix}_games"] = count
        row["team_decay_win_rate_diff"] = row["blue_team_decay_win_rate"] - row["red_team_decay_win_rate"]
        row["team_form_change_diff"] = row["blue_team_form_change"] - row["red_team_form_change"]
        for kind in ("player_decay", "player_champion_recent", "matchup_recent", "player_patch", "player_champion_patch"):
            row[f"{kind}_win_rate_diff"] = float(np.mean([row[f"blue_{r}_{kind}_win_rate"] - row[f"red_{r}_{kind}_win_rate"] for r in ROLES]))
        for kind in ("team_patch", "roster", "head_to_head", *PAIR_ROLES, *(f"{p}_recent" for p in PAIR_ROLES), *(f"{p}_patch" for p in PAIR_ROLES), *(f"{p}_players" for p in PAIR_ROLES)):
            row[f"{kind}_win_rate_diff"] = row[f"blue_{kind}_win_rate"] - row[f"red_{kind}_win_rate"]
        return row


def enhanced_columns():
    base_numeric, categorical = feature_columns("C")
    empty_game = {"date": pd.Timestamp("2000-01-01", tz="UTC")}
    all_names = EnhancedHistoricalState().features(empty_game)
    additional = sorted(set(all_names) - set(base_numeric) - set(categorical))
    return base_numeric + additional, categorical


def build_enhanced_table(games, as_of=None):
    data = _prepare(games, as_of)
    events = data.sort_values(["available_at", "game_id"], kind="stable").to_dict("records")
    state, cursor, rows = EnhancedHistoricalState(), 0, []
    for game in data.to_dict("records"):
        while cursor < len(events) and events[cursor]["available_at"] < game["date"]:
            state.update(events[cursor])
            cursor += 1
        row = state.features(game)
        row.update({name: game[name] for name in ("game_id", "date", "available_at", "blue_win")})
        rows.append(row)
    numeric, categorical = enhanced_columns()
    return pd.DataFrame(rows, columns=["game_id", "date", "available_at", "blue_win", *numeric, *categorical])


def enhanced_features_for_game(history, game, as_of):
    cutoff = min(_timestamp(as_of), _timestamp(game["date"]))
    data = _prepare(history, cutoff)
    if game.get("game_id") is not None:
        data = data.loc[data.game_id != str(game["game_id"])]
    state = EnhancedHistoricalState()
    for prior in data.sort_values(["available_at", "game_id"], kind="stable").to_dict("records"):
        state.update(prior)
    target = dict(game, _feature_time=cutoff)
    row = state.features(target)
    coverage = state.coverage(target, row, cutoff)
    coverage.update(enhanced_feature_version=VERSION, decay_half_life_days=DECAY_HALF_LIFE_DAYS,
                    specific_pairs={side: {pair: int(row[f"{side}_{pair}_games"]) for pair in PAIR_ROLES} for side in SIDES},
                    same_roster_games={side: int(row[f"{side}_roster_games"]) for side in SIDES})
    return row, coverage
