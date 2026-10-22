"""Approved request namespaces must match real model-training categories."""
import pytest

from worlds_predictor.context import enforce_worlds_context, is_worlds_league, model_league, model_patch, public_patch


@pytest.mark.parametrize("name", ["WLDs", "wlds", "WLDS", "WCS", "worlds", "Worlds", "World Championship", "WORLD CHAMPIONSHIP", "Worlds 2026", "2026 Worlds", "League of Legends World Championship"])
def test_worlds_aliases_are_canonical(name):
    assert is_worlds_league(name)
    assert model_league(name) == "WLDs"


@pytest.mark.parametrize("name", ["LCK", "LPL", "MSI", "not worlds", "Other World Championship League"])
def test_other_leagues_not_reclassified(name):
    assert not is_worlds_league(name)
    assert model_league(name) == name


@pytest.mark.parametrize("source,expected", [("26.20", "16.20"), ("16.20", "16.20"), ("16.1", "16.01"), ("16.01", "16.01"), ("14.9", "14.09"), ("15.2", "15.02"), ("26.21", "26.21"), ("27.1", "27.1")])
def test_model_patch_only_uses_approved_namespace_mapping(source, expected):
    assert model_patch(source) == expected


def test_public_patch_has_no_general_year_conversion():
    assert public_patch("16.20") == "26.20"
    assert public_patch("26.20") == "26.20"
    assert public_patch("16.19") == "16.19"
    assert public_patch("15.1") == "15.01"


@pytest.mark.parametrize("league", ["WLDs", "WCS", "Worlds", "world championship"])
@pytest.mark.parametrize("patch", ["26.20", "16.20"])
def test_both_worlds_patch_names_accepted(league, patch):
    enforce_worlds_context({"league": league, "patch": patch, "scheduled_start": "2026-10-23T00:00:00Z"}, {"status": "confirmed", "configured_patch": "26.20"})


@pytest.mark.parametrize("patch", ["16.19", "26.19", "16.21", "26.21"])
def test_source_worlds_alias_cannot_bypass_patch_guard(patch):
    with pytest.raises(ValueError, match="configured patch"):
        enforce_worlds_context({"league": "WLDs", "patch": patch, "scheduled_start": "2026-10-23T00:00:00Z"}, {"status": "confirmed", "configured_patch": "26.20"})


def test_official_mismatch_is_service_error_before_request_error():
    with pytest.raises(RuntimeError, match="official patch"):
        enforce_worlds_context({"league": "WLDs", "patch": "16.19", "scheduled_start": "2026-10-23T00:00:00Z"}, {"status": "mismatch", "configured_patch": "26.20", "official_patch": "26.21"})


def test_inconsistent_verification_status_cannot_hide_official_mismatch():
    with pytest.raises(RuntimeError, match="official patch"):
        enforce_worlds_context({"league": "WLDs", "patch": "26.20", "scheduled_start": "2026-10-23T00:00:00Z"}, {"status": "confirmed", "configured_patch": "26.20", "official_patch": "26.21"})


def test_historical_worlds_uses_own_patch():
    enforce_worlds_context({"league": "WLDs", "patch": "14.18", "scheduled_start": "2024-10-23T00:00:00Z"}, {"status": "confirmed", "configured_patch": "26.20"})
