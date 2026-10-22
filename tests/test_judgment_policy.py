"""Policy unit fixtures are synthetic logic cases, never product training data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import worlds_predictor.judgment_policy as module
from worlds_predictor.judgment_policy import apply_policy, build_policy, load_evaluation, load_policy, wilson_interval


def frame(n=1000, correct=True):
    raw = np.linspace(-2.0, 2.0, n)
    labels = (raw >= 0).astype(int)
    if not correct:
        labels = 1-labels
    return pd.DataFrame({"game_id": [f"explicit-unit-only-{i}" for i in range(n)],
                         "date": ["2025-08-01T12:00:00Z"]*n,
                         "available_at": ["2025-08-02T00:00:00Z"]*n,
                         "raw_score": raw, "calibrated_probability": 1/(1+np.exp(-raw)), "blue_win": labels})


def make_policy(data=None):
    return build_policy(frame() if data is None else data, model_version="unit-fixture-only", artifact_sha256="a"*64,
                        calibrator_coef=1., calibrator_intercept=0., label_cutoff="2025-12-30T00:00:00Z",
                        source_engine="frozen")


def write_bundle(tmp_path, policy):
    path = tmp_path / "judgment_policy.json"
    path.write_text(json.dumps(policy))
    evaluation = tmp_path / "judgment_evaluation.json"
    evaluation.write_text(json.dumps({"test_only": True}))
    manifest = {"policy_sha256": module.file_sha256(path), "evaluation_sha256": module.file_sha256(evaluation),
                "policy_code_sha256": module.file_sha256(Path(module.__file__))}
    (tmp_path / "judgment_manifest.json").write_text(json.dumps(manifest))
    return path


def test_support_rank_is_not_probability_and_has_no_minimum():
    policy = make_policy()
    result = apply_policy(0.04, 1/(1+np.exp(-0.04)), policy)
    assert result["calibrated_probability"] < 0.511
    assert 50 < result["support_index"]["blue"] < 52
    assert result["support_index"]["blue"] + result["support_index"]["red"] == pytest.approx(100)
    assert result["is_probability"] is False
    assert result["grade"]["key"] == "slight"
    assert result["winner_side"] == "blue"


def test_index_uses_distance_from_calibrated_boundary_not_zero():
    data = frame()
    data["calibrated_probability"] = 1/(1+np.exp(-(data.raw_score-0.8)))
    policy = build_policy(data, model_version="unit", artifact_sha256="x", calibrator_coef=1, calibrator_intercept=-0.8,
                          label_cutoff="2025-12-30T00:00:00Z", source_engine="frozen")
    result = apply_policy(0.4, 1/(1+np.exp(0.4)), policy)
    assert result["winner_side"] == "red"
    assert result["support_index"]["red"] > 50
    assert result["decision_boundary"] == pytest.approx(0.8)


def test_exact_tie_explicit_and_not_strong():
    result = apply_policy(0., 0.5, make_policy())
    assert result["winner_side"] == "blue"
    assert result["support_index"] == {"blue": 50., "red": 50.}
    assert result["tie_break"] == "exact_probability_tie_choose_blue"
    assert result["grade"]["key"] == "slight"


def test_strong_grade_needs_real_pretest_validation_gate():
    good = make_policy()
    bad = make_policy(frame(correct=False))
    assert good["strong_validation"]["passed"] is True
    assert bad["strong_validation"]["passed"] is False
    assert apply_policy(1.8, 1/(1+np.exp(-1.8)), good)["grade"]["key"] == "strong"
    downgraded = apply_policy(1.8, 1/(1+np.exp(-1.8)), bad)
    assert downgraded["grade"]["raw_key"] == "strong"
    assert downgraded["grade"]["key"] == "clear"
    assert downgraded["grade"]["downgraded"] is True


def test_too_few_validation_rows_cannot_certify_strong():
    policy = make_policy(frame(n=10))
    assert policy["strong_validation"]["passed"] is False
    assert policy["strong_validation"]["n"] < 100


def test_outside_reference_range_clipped_and_flagged():
    decision = apply_policy(20., 1-1e-8, make_policy())
    assert decision["support_index"]["blue"] == 100
    assert decision["out_of_reference_range"] is True
    assert decision["empirical_score_percentile"] == 1


@pytest.mark.parametrize("raw,p", [(float("nan"), .7), (float("inf"), .7), (1., float("nan")), (1., 1.1), (1., -0.1), (1., .1)])
def test_invalid_or_incompatible_outputs_rejected(raw, p):
    with pytest.raises(ValueError):
        apply_policy(raw, p, make_policy())


def test_inverted_calibrator_cannot_flip_ranking_silently():
    policy = make_policy()
    policy["calibrator_coef"] = -1
    with pytest.raises(ValueError, match="positive"):
        apply_policy(1., .7, policy)


def test_validation_identity_and_time_boundaries():
    bad = frame()
    bad.loc[1, "game_id"] = bad.loc[0, "game_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        make_policy(bad)
    future = frame()
    future.loc[1, "available_at"] = "2027-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="cutoff"):
        make_policy(future)


def test_loader_strict_cutoff_hash_model_and_feature_code(tmp_path):
    path = write_bundle(tmp_path, make_policy())
    assert load_policy(path, as_of="2026-01-01T00:00:00Z", model_version="unit-fixture-only", artifact_sha256="a"*64)["source_engine"] == "frozen"
    for stamp in ("2025-12-30T00:00:00Z", "2025-12-29T00:00:00Z", "2026-01-01"):
        with pytest.raises(ValueError):
            load_policy(path, as_of=stamp)
    with pytest.raises(ValueError, match="version"):
        load_policy(path, as_of="2026-01-01T00:00:00Z", model_version="wrong")
    with pytest.raises(ValueError, match="artifact"):
        load_policy(path, as_of="2026-01-01T00:00:00Z", artifact_sha256="wrong")
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash"):
        load_policy(path, as_of="2026-01-01T00:00:00Z")


def test_evaluation_loader_requires_unchanged_real_report(tmp_path):
    write_bundle(tmp_path, make_policy())
    report = tmp_path / "judgment_evaluation.json"
    assert load_evaluation(report) == {"test_only": True}
    report.write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        load_evaluation(report)


def test_empty_grade_has_no_fabricated_success_rate():
    assert wilson_interval(0, 0) == (None, None)
    low, high = wilson_interval(70, 100)
    assert low == pytest.approx(0.6041514536665332)
    assert high == pytest.approx(0.7810511470506724)
    with pytest.raises(ValueError):
        wilson_interval(101, 100)


def test_reference_changes_are_not_hidden():
    policy = make_policy()
    policy["validation_abs_margins"] = [2., 1.]
    with pytest.raises(ValueError, match="reference"):
        apply_policy(1, .7, policy)


def test_actual_result_comparison_and_empty_groups_are_explicit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("evaluate_aggressive_for_test", Path(__file__).parents[1] / "scripts/evaluate_aggressive.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    data = frame(n=4)
    data["p_blue_raw"] = data.calibrated_probability
    data.loc[0, "blue_win"] = 1-data.loc[0, "blue_win"]
    summary, rows = script.evaluate_frame(data, make_policy())
    assert summary["n"] == 4 and summary["correct"] == 3
    assert summary["accuracy"] == .75
    assert rows.loc[0, "predicted_side"] == "red"
    assert rows.loc[0, "actual_side"] == "blue"
    assert not bool(rows.loc[0, "correct"])
    assert sum(item["n"] for item in summary["grades"]) == 4
    empty, _ = script.evaluate_frame(data.iloc[0:0], make_policy())
    assert empty["n"] == 0 and empty["accuracy"] is None
    assert len(empty["grades"]) == 3
    assert all(item["accuracy"] is None for item in empty["grades"])
