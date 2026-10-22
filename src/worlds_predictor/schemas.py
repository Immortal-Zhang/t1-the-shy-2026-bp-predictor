"""Validated, pre-match-only public request contract.

Player IDs identify a professional competitor in the imported source registry;
they are never Riot solo queue account IDs.  This contract intentionally has no
current-game kills, gold, damage or other post-start statistics.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Role = Literal["top", "jng", "mid", "bot", "sup"]
ROLES = {"top", "jng", "mid", "bot", "sup"}


class PlayerPick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    player_id: NonEmpty
    champion: NonEmpty


class TeamDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: NonEmpty
    players: list[PlayerPick] = Field(min_length=5, max_length=5)
    bans: list[NonEmpty | None] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def exactly_one_per_role(self) -> "TeamDraft":
        if {p.role for p in self.players} != ROLES:
            raise ValueError("Each side must contain exactly one top, jng, mid, bot and sup")
        return self


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    scheduled_start: datetime
    league: NonEmpty
    patch: Annotated[str, StringConstraints(pattern=r"^\d{2}\.\d{1,2}$")]
    blue: TeamDraft
    red: TeamDraft
    first_pick_side: Literal["blue", "red", "unknown"] = "unknown"
    game_id: NonEmpty | None = None
    series_context: dict[str, Any] | None = None

    @field_validator("as_of", "scheduled_start")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone, for example 2026-10-22T12:00:00Z")
        return value

    @model_validator(mode="after")
    def check_single_game(self) -> "PredictionRequest":
        if self.as_of > self.scheduled_start:
            raise ValueError("as_of must be at or before scheduled_start")
        if self.blue.team_id.casefold() == self.red.team_id.casefold():
            raise ValueError("Blue and red must be distinct teams")
        picks = self.blue.players + self.red.players
        if len({p.player_id.casefold() for p in picks}) != 10:
            raise ValueError("Ten distinct professional player IDs are required")
        champions = [p.champion.casefold() for p in picks]
        if len(set(champions)) != 10:
            raise ValueError("Ten distinct champion picks are required")
        bans = [b.casefold() for b in self.blue.bans + self.red.bans if b is not None]
        if len(set(bans)) != len(bans):
            raise ValueError("A champion may not appear in multiple ban slots")
        if set(champions) & set(bans):
            raise ValueError("A picked champion may not also be banned")
        if self.series_context:
            raise ValueError("Series/Fearless Draft context is reserved; this version predicts one independent map")
        return self
