"""Date-bounded professional player lookup and exact alias resolution.

Registry display-name matches are only a convenience over the documented local
identity registry. They do not independently verify that two names are the same
person. No unknown name is silently converted into a synthetic identity here.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unicodedata

import pandas as pd

from .data import read_aliases, resolve_player_id

CANONICAL_PREFIXES = ("pro:", "oe:player:", "source:")


def _clean(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _cutoff(as_of) -> pd.Timestamp:
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    return cutoff.tz_convert("UTC")


def _registry_at(registry_path: str | Path, as_of) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype=str, keep_default_na=False)
    required = {"player_id", "alias", "identity_basis", "first_observed"}
    if not required.issubset(registry.columns):
        raise ValueError(f"Player registry missing columns: {sorted(required - set(registry.columns))}")
    registry["alias"] = registry.alias.map(_clean)
    registry["first_observed"] = pd.to_datetime(registry.first_observed, utc=True, errors="raise", format="mixed")
    return registry[registry.first_observed <= _cutoff(as_of)].copy()


def resolve_request_ids(payload: dict, registry_path: Path, aliases_path: Path | None = None) -> dict:
    """Return a copy with exact professional aliases resolved at ``as_of``.

    Opaque canonical IDs can be supplied for unseen players; downstream model
    coverage must disclose their lack of history. Unknown human-readable names
    and ambiguous names fail with ValueError rather than inventing identities.
    """
    result = deepcopy(payload)
    cutoff = _cutoff(result["as_of"])
    registry = _registry_at(registry_path, cutoff)
    known_ids = set(registry.player_id)
    aliases = read_aliases(aliases_path)
    resolved_ids = []
    for side in ("blue", "red"):
        for player in result[side]["players"]:
            value = _clean(player["player_id"])
            if value in known_ids or any(value.startswith(prefix) and len(value) > len(prefix) for prefix in CANONICAL_PREFIXES):
                canonical = value
            else:
                active = aliases[(aliases.alias == value) & (aliases.valid_from <= cutoff) & (cutoff < aliases.valid_to)] if not aliases.empty else aliases
                if len(active):
                    canonical = resolve_player_id(value, cutoff, aliases, known_ids)
                elif not aliases.empty and value in set(aliases.alias):
                    raise ValueError(f"Player alias {value!r} has no active mapping at as_of")
                else:
                    matches = registry.loc[registry.alias == value, "player_id"].unique()
                    if len(matches) != 1:
                        state = "Ambiguous" if len(matches) > 1 else "Unknown"
                        raise ValueError(f"{state} professional player alias {value!r} at as_of; provide a canonical ID or dated alias mapping")
                    canonical = str(matches[0])
            player["player_id"] = canonical
            resolved_ids.append(canonical)
    if len(set(resolved_ids)) != len(resolved_ids):
        raise ValueError("Multiple input aliases resolve to the same professional player ID")
    return result


def search_players(registry_path: str | Path, query: str, as_of, limit: int = 50) -> list[dict]:
    """Search aliases/IDs already observed by cutoff, without future aggregates.

    ``last_observed`` and ``observed_games`` from the full registry are omitted:
    their aggregate values may contain observations after the requested cutoff.
    Search is case-insensitive substring matching; identity resolution remains
    exact, case-sensitive, Unicode-normalized and ambiguity rejecting.
    """
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    registry = _registry_at(registry_path, as_of)
    query = _clean(query)
    if query:
        registry = registry[registry.alias.str.contains(query, case=False, regex=False) | registry.player_id.str.contains(query, case=False, regex=False)]
    columns = ["player_id", "alias", "identity_basis", "first_observed"]
    rows = registry[columns].drop_duplicates().sort_values(["alias", "player_id", "first_observed"]).head(limit)
    return [{**row, "first_observed": row["first_observed"].isoformat()} for row in rows.to_dict("records")]
