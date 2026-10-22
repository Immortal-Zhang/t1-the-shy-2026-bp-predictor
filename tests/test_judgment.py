"""Decision integration and explanation invariants, with real inference fixtures."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from worlds_predictor.analysis import _load_artifacts, analyze
from worlds_predictor.judgment import _category, build_judgment, explain_judgment, group_contributions
from worlds_predictor.model import predict

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real():
    required = ["reports/aggressive/judgment_manifest.json", "data/processed/games.parquet",
                "models/latest/selected_model.joblib", "models/latest/metadata.json",
                "models/aggressive-experiment/latest/selected_model.joblib",
                "models/aggressive-experiment/latest/metadata.json"]
    if not all((ROOT / name).is_file() for name in required):
        pytest.skip("Real model/history artifacts not installed; run the documented data and training commands")
    payload = json.loads((ROOT / "examples/real_match_replay.json").read_text())
    result = analyze(payload, ROOT / "models/latest", ROOT / "data/processed/games.parquet")
    assert result["judgment"]["available"], result["judgment"]
    return payload, result


@pytest.mark.parametrize("feature,kind", [
    ("red_bot_support_patch_games", "bot_lane"),
    ("red_bot_support_players_games", "players"),
    ("mid_jungle_players_win_rate_diff", "players"),
    ("blue_mid_jungle_win_rate", "mid_jungle"),
    ("red_head_to_head_games", "teams"),
    ("blue_mid_player_champion_recent_games", "proficiency"),
    ("blue_mid_player_champion_patch_games", "patch"),
])
def test_evidence_group_semantics(feature, kind):
    assert _category(feature)[0] == kind


def test_full_attribution_partition_conserves_mass():
    # Structural arithmetic fixture only, not product data or claimed performance.
    items = [{"feature": f, "contribution": v, "value": 1} for f, v in
             [("blue_bot_support_win_rate", .4), ("red_bot_support_win_rate", -.3),
              ("blue_mid_player_id", .2), ("league", -.1)]]
    grouped = group_contributions(items)
    assert sum(g["contribution"] for g in grouped) == pytest.approx(.2)
    assert sum(g["absolute_contribution"] for g in grouped) == pytest.approx(1)
    assert sum(len(g["features"]) for g in grouped) == len(items)
    with pytest.raises(ValueError, match="Non-finite"):
        group_contributions([{"feature": "league", "contribution": np.nan}])


def test_standard_calibrated_probability_unchanged(real):
    payload, result = real
    original = predict(payload, ROOT / "models/latest", ROOT / "data/processed/games.parquet")
    assert result["prediction"] == original
    assert original["blue_win_probability"] == pytest.approx(0.30217792358429685)


def test_real_decision_evidence_and_probability_distinction(real):
    _, result = real
    judgment = result["judgment"]
    assert judgment["winner"]["side"] == "red"
    assert judgment["engine"] == "enhanced"
    assert judgment["support"]["blue"] + judgment["support"]["red"] == pytest.approx(100)
    assert "不是获胜概率" in judgment["support"]["definition"]
    assert judgment["support"]["judgment_calibrated_probability"] == pytest.approx(0.3390241676901847)
    assert judgment["support"]["reference_n"] == 2968
    assert len(judgment["reasons"]) == 3 and len(judgment["risks"]) == 2
    assert all(item["contribution"] < 0 for item in judgment["reasons"] if item["contribution"] is not None)
    assert all(item["contribution"] > 0 for item in judgment["risks"] if item["contribution"] is not None)
    assert judgment["reliability"]["level"] == "low"
    assert judgment["driver"]["bp_share"] + judgment["driver"]["players_teams_share"] + judgment["driver"]["context_share"] == pytest.approx(1)
    assert "未证明整体效果提升" in judgment["evaluation"]["comparison_note"]
    assert judgment["evaluation"]["n"] == 9309


def test_zero_evidence_never_invents_three_advantages(real):
    _, result = real
    output = explain_judgment(result, [], 0, {"winner_side": "blue", "out_of_reference_range": False}, {"engine": "frozen"})
    assert len(output["reasons"]) == 3 and len(output["risks"]) == 2
    assert len({item["title"] for item in output["risks"]}) == 2
    assert all(e["evidence_status"] == "unavailable" and e["contribution"] is None for e in output["reasons"])
    assert output["bp_assessment"]["favored_side"] is None
    assert output["driver"]["primary"] == "context"


def test_missing_decision_artifacts_preserve_standard_result(monkeypatch, tmp_path, real):
    payload, result = real
    before = deepcopy(result)
    monkeypatch.setenv("WORLDS_JUDGMENT_DIR", str(tmp_path))
    judgment = build_judgment(payload, result, {}, {}, {}, ROOT / "data/processed/games.parquet")
    assert judgment["available"] is False
    assert "标准校准预测仍然保留" in judgment["reason"]
    assert result == before


def test_corrupted_policy_fails_closed_before_inference(monkeypatch, tmp_path, real):
    payload, result = real
    source = ROOT / "reports/aggressive"
    for name in ("judgment_policy.json", "judgment_evaluation.json", "judgment_manifest.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    with (tmp_path / "judgment_policy.json").open("a") as stream:
        stream.write(" ")
    monkeypatch.setenv("WORLDS_JUDGMENT_DIR", str(tmp_path))
    judgment = build_judgment(payload, result, {}, {}, {}, ROOT / "data/processed/games.parquet")
    assert judgment["available"] is False
    assert "integrity mismatch" in judgment["reason"]


def test_unknown_history_downgrades_reliability(real):
    _, original = real
    result = deepcopy(original)
    result["prediction"]["sample_coverage"]["unknown_players_in_role"] = ["unit-test-unknown"]
    result["prediction"]["sample_coverage"]["patch_history_games"] = 0
    output = explain_judgment(result, [], 0, {"winner_side": "blue", "out_of_reference_range": False}, {"engine": "frozen"})
    assert output["reliability"]["level"] == "low"
    assert any("没有历史覆盖" in text for text in output["reliability"]["details"])


def test_exact_policy_cutoff_unavailable_without_fake_decision(real):
    payload, result = real
    metadata, _, selected, _ = _load_artifacts(ROOT / "models/latest")
    changed = dict(payload, as_of=metadata["label_cutoff"])
    judgment = build_judgment(changed, result, selected, {}, metadata, ROOT / "data/processed/games.parquet")
    assert judgment["available"] is False
    assert "winner" not in judgment and "support" not in judgment
