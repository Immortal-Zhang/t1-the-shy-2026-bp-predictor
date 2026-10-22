"""Supplemental pooled-label versus single-league-label training sensitivity.

This intentionally preserves globally computed historical features in both arms.
It measures training-label pooling, not complete region isolation, and never
changes the selected deployment model. No synthetic fallback is permitted.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .evaluation import metrics, paired_day_bootstrap, temporal_split
from .features import feature_columns
from .model import _fit, _logits, dump_json, make_estimator, sha256


def cohort_eligibility(parts: dict[str, pd.DataFrame], calibrated: bool = True) -> tuple[dict, list[str]]:
    summary, blockers = {}, []
    minimum = {"train": 100, "validation": 1, "calibration": 50 if calibrated else 0, "test": 1}
    for name, frame in parts.items():
        summary[name] = {
            "n": len(frame), "blue_wins": int(frame.blue_win.sum()),
            "first_game": frame.date.min() if len(frame) else None,
            "last_game": frame.date.max() if len(frame) else None,
            "latest_result_available": frame.available_at.max() if len(frame) else None,
        }
        if len(frame) < minimum[name]:
            blockers.append(f"{name}: {len(frame)} eligible games, requires {minimum[name]}")
        if minimum[name] and frame.blue_win.nunique() != 2:
            blockers.append(f"{name}: requires both binary outcomes")
    return summary, blockers


def aligned_pooled_predictions(test: pd.DataFrame, pooled: pd.DataFrame, league: str, calibrated: bool) -> np.ndarray:
    """Require an exact one-to-one test-game and outcome match, never inner-drop."""
    pooled = pooled.loc[pooled.league.astype(str) == league].copy()
    if test.game_id.duplicated().any() or pooled.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs in cross-league test comparison")
    if set(test.game_id.astype(str)) != set(pooled.game_id.astype(str)):
        raise ValueError("Pooled and league-only test game ID sets differ")
    indexed = pooled.set_index(pooled.game_id.astype(str)).loc[test.game_id.astype(str)]
    if not np.array_equal(indexed.blue_win.to_numpy(), test.blue_win.to_numpy()):
        raise ValueError("Pooled prediction labels disagree with held-out source outcomes")
    if not np.array_equal(pd.to_datetime(indexed.date, utc=True).to_numpy(), pd.to_datetime(test.date, utc=True).to_numpy()):
        raise ValueError("Pooled prediction dates disagree with held-out source dates")
    return indexed["p_blue" if calibrated else "p_blue_raw"].to_numpy(dtype=float)


def run_cross_league_sensitivity(
    feature_path="reports/features.parquet",
    global_metrics_path="reports/metrics.json",
    global_predictions_path="reports/predictions_C_catboost.csv",
    config_path="configs/train.json",
    report_dir="reports",
    models_dir="models/sensitivity",
    league="LCK",
    calibrated=True,
):
    feature_path, report_dir = Path(feature_path), Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = "cross_league_sensitivity" if calibrated else "cross_league_raw_sensitivity"
    config = json.loads(Path(config_path).read_text())
    global_report = json.loads(Path(global_metrics_path).read_text())
    if global_report["config"] != config:
        raise ValueError("Cached global run configuration does not match sensitivity configuration")
    if global_report.get("status") != "complete" or "C_catboost" not in global_report["models"]:
        raise ValueError("A completed real-data global C_catboost evaluation is required")
    if global_report.get("source_sha256", {}).get("features.py") != sha256(Path(__file__).with_name("features.py")):
        raise ValueError("Feature code changed after the main evaluation; regenerate caches")
    frame = pd.read_parquet(feature_path)
    global_parts = temporal_split(frame, config)
    parts = {name: part.loc[part.league.astype(str) == league].copy() for name, part in global_parts.items()}
    cohorts, blockers = cohort_eligibility(parts, calibrated)
    result = {
        "status": "blocked" if blockers else "running", "evaluation_type": "real_gt",
        "protocol_declared_at": datetime.now(timezone.utc).isoformat(),
        "target_league": league, "global_run_id": global_report["run_id"],
        "data_sha256": global_report["data_sha256"], "feature_cache_sha256": sha256(feature_path),
        "feature_code_sha256": global_report["source_sha256"]["features.py"],
        "global_predictions_sha256": sha256(global_predictions_path),
        "config": {**config, "thread_count": 2}, "cohorts": cohorts,
        "pooled_cohort_counts": {name: len(part) for name, part in global_parts.items()},
        "calibrated_comparison": calibrated,
        "protocol": "Fixed supplemental comparison of pooled C CatBoost labels against target-league-only C CatBoost labels. Same features, chronology, hyperparameters, seed, recency weights, and identical target-league held-out games. No test-driven tuning or deployment selection.",
        "feature_history_scope": "Globally pooled historical features are preserved in both arms. This is pooled training-label sensitivity, not complete region isolation.",
        "limitations": [
            "Single target league, chronological holdout and random seed; results do not establish transport to every region or Worlds.",
            "League-only and pooled models use different training sample sizes and opposition coverage; effects are not causal.",
            "Globally derived team/player/champion history remains available to both models.",
            "This supplemental protocol was fixed before its league-only fit, after the main evaluation; it is exploratory evidence.",
        ],
        "blockers": blockers,
    }
    if not calibrated and cohorts["calibration"]["n"] == 0:
        result["limitations"].append("No target-league games exist in the configured calibration block for this run; this separate raw-vs-raw comparison does not establish calibrated league-specific accuracy.")
    elif not calibrated:
        result["limitations"].append("Both models are evaluated without calibration; this separate comparison does not establish calibrated league-specific accuracy.")
    membership = pd.concat([part[["game_id", "date", "available_at", "blue_win"]].assign(split=name) for name, part in parts.items()])
    membership.to_csv(report_dir / f"{stem}_membership.csv", index=False)
    dump_json(report_dir / f"{stem}.json", result)
    if blockers:
        _write_markdown(result, report_dir / f"{stem}.md")
        return result

    numeric, categorical = feature_columns("C")
    columns = numeric + categorical
    training = parts["train"]
    age = (pd.Timestamp(config["train_end"]) - pd.to_datetime(training.date, utc=True)).dt.total_seconds() / 86400
    weights = np.exp2(-age.to_numpy() / config["half_life_days"]) if config.get("half_life_days") else np.ones(len(training))
    weights /= weights.mean()
    estimator = _fit(make_estimator("catboost", numeric, categorical, result["config"]), "catboost", training[columns], training.blue_win, weights)
    calibrator = None
    if calibrated:
        calibration = parts["calibration"]
        raw = estimator.predict_proba(calibration[columns])[:, 1]
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=config["seed"]).fit(_logits(raw), calibration.blue_win)
    result["validation_raw"] = metrics(parts["validation"].blue_win, estimator.predict_proba(parts["validation"][columns])[:, 1])
    test = parts["test"]
    p_local = estimator.predict_proba(test[columns])[:, 1]
    if calibrator is not None:
        p_local = calibrator.predict_proba(_logits(p_local))[:, 1]
    p_pooled = aligned_pooled_predictions(test, pd.read_csv(global_predictions_path, dtype={"game_id": str}), league, calibrated)
    result["league_only_test"] = metrics(test.blue_win, p_local)
    result["pooled_test_same_games"] = metrics(test.blue_win, p_pooled)
    delta = paired_day_bootstrap(test.blue_win, p_local, p_pooled, test.date, seed=config["seed"])
    delta["metric"] = "log_loss_pooled_minus_league_only"
    delta["interpretation"] = "Negative favors pooled training labels; exploratory day-block interval on one target league and one seed."
    result["paired_comparison"] = delta
    result["test_by_patch"] = {}
    for patch, indices in test.groupby("patch").indices.items():
        result["test_by_patch"][str(patch)] = {"league_only": metrics(test.iloc[indices].blue_win, p_local[indices]),
                                                "pooled": metrics(test.iloc[indices].blue_win, p_pooled[indices])}
    predictions = test[["game_id", "date", "league", "patch", "blue_win"]].copy()
    predictions["p_blue_league_only"], predictions["p_blue_pooled"] = p_local, p_pooled
    predictions.to_csv(report_dir / f"{stem}_predictions.csv", index=False)
    artifact_path = Path(models_dir) / f"{global_report['run_id']}_{league}_{'calibrated' if calibrated else 'raw'}.joblib"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": estimator, "calibrator": calibrator, "columns": columns,
                 "feature_scope": result["feature_history_scope"], "config": result["config"],
                 "target_league": league, "supplemental_only": True}, artifact_path)
    result["artifact_path"] = str(artifact_path)
    result["artifact_sha256"] = sha256(artifact_path)
    result["status"] = "complete"
    dump_json(report_dir / f"{stem}.json", result)
    _write_markdown(result, report_dir / f"{stem}.md")
    return result


def _write_markdown(result, path):
    lines = ["# Supplemental cross-league training-label sensitivity", "", f"Status: **{result['status']}**", "",
             result["protocol"], "", result["feature_history_scope"], "",
             f"Target league: {result['target_league']}; calibrated comparison: {result['calibrated_comparison']}.", "",
             f"Pooled training games: {result['pooled_cohort_counts']['train']}; target-league training games: {result['cohorts']['train']['n']}.", "",
             "| Split | Games | Blue wins |", "|---|---:|---:|"]
    for name, value in result["cohorts"].items():
        lines.append(f"| {name} | {value['n']} | {value['blue_wins']} |")
    if result["status"] == "blocked":
        lines.extend(["", "No model or comparison metrics were fabricated.", ""] + [f"- {item}" for item in result["blockers"]])
    elif result["status"] == "complete":
        lines.extend(["", "| Training labels | Test accuracy | AUC | Log loss | Brier | ECE |", "|---|---:|---:|---:|---:|---:|"])
        for name, key in (("Target league only", "league_only_test"), ("Pooled, same test games", "pooled_test_same_games")):
            score = result[key]
            lines.append(f"| {name} | {score['accuracy']:.5f} | {score['roc_auc']:.5f} | {score['log_loss']:.5f} | {score['brier_score']:.5f} | {score['ece_10']:.5f} |")
        comparison = result["paired_comparison"]
        lines.extend(["", f"Pooled minus league-only log loss: {comparison['point']:.6f}; day-block 95% interval {comparison['day_block_bootstrap_95_interval']}."])
    lines.extend(["", "## Limits", ""] + [f"- {item}" for item in result["limitations"]])
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="LCK")
    parser.add_argument("--raw", action="store_true", help="Separate explicitly uncalibrated sensitivity; never silently substitutes for calibration")
    parser.add_argument("--config", default="configs/train.json")
    arguments = parser.parse_args()
    output = run_cross_league_sensitivity(config_path=arguments.config, league=arguments.league, calibrated=not arguments.raw)
    print(json.dumps({"status": output["status"], "cohorts": output["cohorts"], "blockers": output["blockers"]}, default=str))
