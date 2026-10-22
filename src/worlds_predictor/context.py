"""Explicit public/provider context aliases used before model feature creation.

Only the reviewed Worlds 2026 mapping is approved: public 26.20 corresponds to
the source/Data Dragon version 16.20. This is not a rule to subtract ten from
arbitrary public patches. Provenance is in configs/worlds2026.json and
reports/patch_namespace_mapping.json.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import re
from typing import Any


PUBLIC_TO_MODEL_PATCH = {"26.20": "16.20"}
MODEL_TO_PUBLIC_PATCH = {value: key for key, value in PUBLIC_TO_MODEL_PATCH.items()}
SOURCE_MAJOR_VERSIONS = {14, 15, 16}


def is_worlds_league(value: str) -> bool:
    """Recognize exact known aliases, optional year, and case differences."""
    name = " ".join(str(value).strip().casefold().split())
    name = re.sub(r"^20\d{2}\s*", "", name)
    name = re.sub(r"\s*20\d{2}$", "", name)
    return name in {"wlds", "wcs", "worlds", "world championship", "league of legends world championship", "lol world championship"}


def model_league(value: str) -> str:
    """Map the approved Worlds aliases onto the CSV's WLDs category."""
    return "WLDs" if is_worlds_league(value) else str(value).strip()


def model_patch(value: str) -> str:
    """Use reviewed namespace aliases and canonical source minor formatting."""
    value = str(value).strip()
    value = PUBLIC_TO_MODEL_PATCH.get(value, value)
    match = re.fullmatch(r"(\d{2})\.(\d{1,2})", value)
    if match and int(match.group(1)) in SOURCE_MAJOR_VERSIONS:
        return f"{int(match.group(1))}.{int(match.group(2)):02d}"
    return value


def public_patch(value: str) -> str:
    """Expose the official public name only where an explicit mapping exists."""
    canonical = model_patch(value)
    return MODEL_TO_PUBLIC_PATCH.get(canonical, canonical)


def _payload_dict(payload: Any) -> Mapping:
    value = payload.model_dump() if hasattr(payload, "model_dump") else payload
    if not isinstance(value, Mapping):
        raise TypeError("Worlds context payload must be a mapping or request model")
    return value


def enforce_worlds_context(payload: Any, verification: Mapping) -> None:
    """Reject an incompatible Worlds 2026 request before any model is loaded.

    RuntimeError means the official announcement conflicts with configured
    service state (API 503). ValueError means the caller supplied an invalid
    Worlds patch (API 422). The league's source spelling cannot bypass either
    check. A confirmed public patch and its reviewed source alias are equivalent.
    """
    data = _payload_dict(payload)
    if not is_worlds_league(str(data.get("league", ""))):
        return
    scheduled = data.get("scheduled_start")
    try:
        start = scheduled if isinstance(scheduled, datetime) else datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Worlds context requires a valid scheduled_start") from exc
    if start.year != 2026:
        return
    configured = public_patch(str(verification.get("configured_patch", "26.20")))
    official = verification.get("official_patch")
    if verification.get("status") == "mismatch" or (official and public_patch(str(official)) != configured):
        raise RuntimeError("Worlds official patch differs from configuration; update and reverify before predicting")
    requested = public_patch(str(data.get("patch", "")))
    if requested != configured:
        raise ValueError(f"Worlds 2026 configured patch is {configured}; equivalent reviewed source patch is {model_patch(configured)}")
