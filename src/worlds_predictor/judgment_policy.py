"""Auditable decision presentation fitted only on pre-test evidence.

The support index is a signed *rank of a raw-model decision margin*. It is
neither a probability nor a historical success rate. In particular no lower
bound is imposed on a favourite's probability or index. All UI modes use the
same model, rule, index and grade.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

POLICY_VERSION = "margin-percentile-v1"
GRADE_LABELS = {"slight": "轻微优势", "clear": "明显优势", "strong": "强烈倾向"}
GRADE_THRESHOLDS = {"clear": 65.0, "strong": 85.0}
MIN_STRONG_VALIDATION_N = 100
MIN_STRONG_VALIDATION_WILSON_LOW = 0.60


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _timestamp(value: Any) -> pd.Timestamp:
    value = pd.Timestamp(value)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError("Judgment time boundaries must be valid timezone-aware timestamps")
    return value.tz_convert("UTC")


def wilson_interval(correct: int, n: int) -> tuple[float | None, float | None]:
    """Unadjusted 95% Wilson binomial interval, not a performance guarantee."""
    if not isinstance(n, (int, np.integer)) or not isinstance(correct, (int, np.integer)) or not 0 <= correct <= n:
        raise ValueError("Wilson counts must satisfy 0 <= correct <= n")
    if n == 0:
        return None, None
    z = 1.959963984540054
    p = correct / n
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denominator
    distance = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return float(max(0, centre-distance)), float(min(1, centre+distance))


def _finite(value: Any, name: str) -> float:
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _reference(policy: dict) -> np.ndarray:
    values = np.asarray(policy["validation_abs_margins"], dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or (values < 0).any() or (np.diff(values) < 0).any():
        raise ValueError("Invalid validation-only margin reference")
    return values


def _decision(raw_score: float, calibrated_probability: float, policy: dict, *, enforce_gate: bool = True) -> dict:
    raw_score = _finite(raw_score, "raw_score")
    p = _finite(calibrated_probability, "calibrated_probability")
    if not 0 <= p <= 1:
        raise ValueError("Calibrated probability must be within [0, 1]")
    coef = _finite(policy["calibrator_coef"], "calibrator_coef")
    intercept = _finite(policy["calibrator_intercept"], "calibrator_intercept")
    if coef <= 0:
        raise ValueError("A positive calibrator slope is required for the ranking decision")
    boundary = -intercept / coef
    if not np.isclose(boundary, policy["decision_boundary"], atol=1e-12, rtol=1e-12):
        raise ValueError("Calibrator boundary does not match policy")
    margin = raw_score - boundary
    exact_tie = p == 0.5
    # The final calibrated probability chooses the winner. The raw margin must
    # agree: an incompatible artifact must not silently change the decision.
    winner = "blue" if p >= 0.5 else "red"
    if not exact_tie and (margin == 0 or (margin > 0) != (p > 0.5)):
        raise ValueError("Raw score and calibrated winner disagree; incompatible policy/model")
    reference = _reference(policy)
    percentile = 0.0 if exact_tie or margin == 0 else float(np.searchsorted(reference, abs(margin), side="right") / len(reference))
    direction = 0.0 if exact_tie else (1.0 if winner == "blue" else -1.0)
    blue_index = 50.0 + 50.0 * direction * percentile
    winner_index = max(blue_index, 100-blue_index)
    raw_grade = "strong" if winner_index >= GRADE_THRESHOLDS["strong"] else "clear" if winner_index >= GRADE_THRESHOLDS["clear"] else "slight"
    gate = bool(policy.get("strong_validation", {}).get("passed", False))
    grade = "clear" if enforce_gate and raw_grade == "strong" and not gate else raw_grade
    if exact_tie:
        grade = "slight"
    return {
        "winner_side": winner,
        "support_index": {"blue": round(blue_index, 4), "red": round(100-blue_index, 4)},
        "winner_index": round(winner_index, 4),
        "margin": float(margin),
        "raw_score": raw_score,
        "decision_boundary": float(boundary),
        "calibrated_probability": p,
        "empirical_score_percentile": percentile,
        "grade": {"key": grade, "label": GRADE_LABELS[grade], "raw_key": raw_grade,
                  "strong_validated": gate, "downgraded": grade != raw_grade},
        "tie_break": "exact_probability_tie_choose_blue" if exact_tie else None,
        "out_of_reference_range": bool(abs(margin) > reference[-1]),
        "reference_n": len(reference),
        "is_probability": False,
    }


def apply_policy(raw_score: float, calibrated_probability: float, policy: dict) -> dict:
    """Return identical quantitative decisions for standard/aggressive/extreme UI."""
    if policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("Unsupported judgment policy version")
    return _decision(raw_score, calibrated_probability, policy)


def build_policy(validation_frame: pd.DataFrame, *, model_version: str, artifact_sha256: str,
                 calibrator_coef: float, calibrator_intercept: float, label_cutoff: str,
                 source_engine: str, metadata: dict | None = None) -> dict:
    """Fit the index reference and strong-grade gate on validation labels only.

    The calibrator is fitted on a later, separate calibration block. Its final
    boundary is applied here; validation grade accuracy is therefore policy-fit
    evidence, NOT an unbiased held-out performance estimate.
    """
    if validation_frame.empty:
        raise ValueError("A nonempty real validation frame is required")
    required = {"game_id", "date", "available_at", "raw_score", "calibrated_probability", "blue_win"}
    if required.difference(validation_frame.columns):
        raise ValueError("Validation frame misses required evidence columns")
    if validation_frame.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs in support policy reference")
    if not validation_frame.blue_win.isin([0, 1]).all():
        raise ValueError("Support policy requires actual binary labels")
    coef = _finite(calibrator_coef, "calibrator_coef")
    intercept = _finite(calibrator_intercept, "calibrator_intercept")
    if coef <= 0:
        raise ValueError("A positive calibrator slope is required")
    raw = validation_frame.raw_score.to_numpy(dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError("Validation raw scores must be finite")
    cutoff = _timestamp(label_cutoff)
    dates = pd.to_datetime(validation_frame.date, utc=True)
    availability = pd.to_datetime(validation_frame.available_at, utc=True)
    if dates.isna().any() or availability.isna().any() or availability.max() > cutoff:
        raise ValueError("Policy label cutoff does not cover reference labels")
    boundary = -intercept / coef
    policy = {
        "policy_version": POLICY_VERSION,
        "model_version": model_version,
        "artifact_sha256": artifact_sha256,
        "source_engine": source_engine,
        "calibrator_coef": coef,
        "calibrator_intercept": intercept,
        "decision_boundary": float(boundary),
        "label_cutoff": cutoff.isoformat(),
        "validation_reference_n": len(validation_frame),
        "validation_first_game": dates.min().isoformat(),
        "validation_last_game": dates.max().isoformat(),
        "validation_last_result_available": availability.max().isoformat(),
        "validation_game_ids_sha256": hashlib.sha256("\n".join(validation_frame.game_id.astype(str)).encode()).hexdigest(),
        "validation_abs_margins": sorted(np.abs(raw-boundary).tolist()),
        "grade_thresholds": GRADE_THRESHOLDS,
        "formula": "blue_index = 50 + 50 * sign(raw_score - calibrated_0.5_boundary) * validation_ECDF(abs(raw_score - boundary)); red_index = 100 - blue_index",
        "interpretation": "支持指数是原始模型决策间隔在验证样本中的相对位置，不是校准胜率，也不是命中率；无最低胜率。三种展示模式共用同一判断。",
        "fitting_scope": "Validation-only margin reference and label gate, using the final separate-calibration boundary; policy-fit figures are not held-out performance. No test labels fit the policy.",
        "metadata": metadata or {},
    }
    decisions = [_decision(row.raw_score, row.calibrated_probability, policy, enforce_gate=False) for row in validation_frame.itertuples()]
    selected = np.asarray([item["grade"]["raw_key"] == "strong" for item in decisions])
    predicted = np.asarray([item["winner_side"] == "blue" for item in decisions])
    actual = validation_frame.blue_win.to_numpy(dtype=int)
    n = int(selected.sum())
    correct = int((predicted[selected] == actual[selected]).sum())
    low, high = wilson_interval(correct, n)
    policy["strong_validation"] = {
        "n": n, "correct": correct, "accuracy": correct/n if n else None,
        "wilson_low": low, "wilson_high": high, "coverage": n/len(actual),
        "minimum_n": MIN_STRONG_VALIDATION_N,
        "minimum_wilson_low": MIN_STRONG_VALIDATION_WILSON_LOW,
        "passed": bool(n >= MIN_STRONG_VALIDATION_N and low is not None and low >= MIN_STRONG_VALIDATION_WILSON_LOW),
        "scope": "Pre-test policy fitting on validation; not an independent accuracy estimate",
    }
    return policy


def load_policy(path: str | Path, *, as_of: str, model_version: str | None = None,
                artifact_sha256: str | None = None) -> dict:
    """Load a trusted local policy with manifest and strict as_of checks.

    Hashes detect accidental corruption against the local manifest; they are
    not signatures and cannot establish trust in an untrusted model upload.
    """
    path = Path(path)
    try:
        manifest = json.loads(path.with_name("judgment_manifest.json").read_text())
        if file_sha256(path) != manifest["policy_sha256"]:
            raise ValueError("Judgment policy hash mismatch")
        if manifest["policy_code_sha256"] != file_sha256(Path(__file__)):
            raise ValueError("Judgment policy code changed; regenerate the policy report")
        policy = json.loads(path.read_text())
        if policy.get("policy_version") != POLICY_VERSION:
            raise ValueError("Unsupported judgment policy")
        if _timestamp(as_of) <= _timestamp(policy["label_cutoff"]):
            raise ValueError("Judgment policy labels are not strictly before as_of")
        if model_version is not None and model_version != policy["model_version"]:
            raise ValueError("Judgment model version mismatch")
        if artifact_sha256 is not None and artifact_sha256 != policy["artifact_sha256"]:
            raise ValueError("Judgment model artifact mismatch")
        _reference(policy)
        return policy
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Judgment policy unavailable: {exc}") from exc


def load_evaluation(path: str | Path) -> dict:
    path = Path(path)
    try:
        manifest = json.loads(path.with_name("judgment_manifest.json").read_text())
        if file_sha256(path) != manifest["evaluation_sha256"]:
            raise ValueError("Judgment evaluation hash mismatch")
        return json.loads(path.read_text())
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Judgment evaluation unavailable: {exc}") from exc
