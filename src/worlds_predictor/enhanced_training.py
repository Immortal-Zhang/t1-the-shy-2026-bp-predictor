"""Reproducible challenger experiment, with frozen temporal splits and real labels."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys

from catboost import CatBoostClassifier
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from .data import load_games
from .enhanced_features import VERSION, build_enhanced_table, enhanced_columns
from .evaluation import metrics, paired_day_bootstrap, temporal_split
from .model import _logits, _split_summary, dump_json, sha256


def paired_ranking_bootstrap(y, baseline, candidate, dates, seed=2026, repetitions=500):
    y, baseline, candidate = map(np.asarray, (y, baseline, candidate))
    days = pd.to_datetime(pd.Series(dates), utc=True).dt.floor("D")
    groups = [np.asarray(index) for index in pd.DataFrame({"day": days}).groupby("day").indices.values()]
    rng = np.random.default_rng(seed)
    auc, accuracy = [], []
    for _ in range(repetitions):
        ids = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if len(np.unique(y[ids])) > 1:
            auc.append(roc_auc_score(y[ids], candidate[ids]) - roc_auc_score(y[ids], baseline[ids]))
        accuracy.append(np.mean((candidate[ids] >= .5) == y[ids]) - np.mean((baseline[ids] >= .5) == y[ids]))
    return {
        "roc_auc_delta": float(roc_auc_score(y, candidate) - roc_auc_score(y, baseline)),
        "roc_auc_day_block_95_interval": np.quantile(auc, [.025, .975]).tolist(),
        "accuracy_delta": float(np.mean((candidate >= .5) == y) - np.mean((baseline >= .5) == y)),
        "accuracy_day_block_95_interval": np.quantile(accuracy, [.025, .975]).tolist(),
        "days": len(groups), "repetitions": repetitions,
        "limitation": "Retrospective paired diagnostic on a previously inspected holdout, one seed; not a new confirmatory test.",
    }


def choose_candidate(baseline, candidates, tolerance):
    eligible = {name: score for name, score in candidates.items()
                if score["validation_raw"]["log_loss"] <= baseline["validation_raw"]["log_loss"] + tolerance
                and score["validation_raw"]["roc_auc"] > baseline["validation_raw"]["roc_auc"]
                and score["calibrator"]["coefficient"] > 0}
    if not eligible:
        return None
    return max(eligible, key=lambda name: (eligible[name]["validation_raw"]["roc_auc"], -eligible[name]["validation_raw"]["log_loss"]))


def _evaluate(name, artifact, splits, reports):
    scores = {"calibrator": {"coefficient": float(artifact["calibrator"].coef_[0, 0]), "intercept": float(artifact["calibrator"].intercept_[0])}}
    predictions = {}
    for segment in ("validation", "calibration", "test"):
        frame = splits[segment]
        x = frame[artifact["columns"]]
        raw_score = artifact["estimator"].predict(x, prediction_type="RawFormulaVal")
        raw_p = artifact["estimator"].predict_proba(x)[:, 1]
        p = artifact["calibrator"].predict_proba(_logits(raw_p))[:, 1]
        scores[segment + "_raw"] = metrics(frame.blue_win, raw_p)
        scores[segment + "_calibrated"] = metrics(frame.blue_win, p)
        record = frame[["game_id", "date", "available_at", "league", "patch", "blue_win"]].copy()
        record["raw_score"], record["p_blue_raw"], record["calibrated_probability"] = raw_score, raw_p, p
        record["predicted_blue"] = p >= .5
        record["correct"] = record.predicted_blue.astype(int) == record.blue_win
        record.to_csv(reports / f"experiment_predictions_{name}_{segment}.csv", index=False)
        predictions[segment] = p
        if segment == "test":
            target = frame.league.eq("WLDs") & frame.patch.eq("16.20")
            scores["test_worlds_2026_target_patch"] = metrics(frame.loc[target].blue_win, p[target])
            for category in ("league", "patch"):
                scores["test_by_" + category] = {str(value): metrics(frame.iloc[index].blue_win, p[index]) for value, index in frame.groupby(category).indices.items()}
    scores["validation_calibrated_caveat"] = "Retrospective policy-reference scores use the later calibration block; model selection uses ONLY raw validation AUC and log loss. Calibration scores are in-sample, never test claims."
    return scores, predictions


def train_enhanced(config, games_path=Path("data/processed/games.parquet"), models_dir=Path("models/aggressive-experiment"), reports_dir=Path("reports/aggressive")):
    games_path, models_dir, reports_dir = map(Path, (games_path, models_dir, reports_dir))
    reports_dir.mkdir(parents=True, exist_ok=True)
    # Write protocol BEFORE reading new evaluation outcomes or fitting candidates.
    dump_json(reports_dir / "experiment_protocol.json", {"declared_at": datetime.now(timezone.utc).isoformat(), "config": config,
        "scope": "Real-data retrospective challenger experiment. The 2026 holdout has already been inspected in prior project stages; it is not fresh confirmatory evidence.",
        "selection": config["selection"], "feature_version": VERSION,
        "unsupported": ["No curated crowd-control/engage rating", "No early/mid/late power curve", "No team play-style causal matchup", "No postgame statistics as current input"],
        "future_results": "Feature history rolls forward only after strict available_at and date cutoffs; fitted estimators and calibrators remain frozen."})
    baseline_dir = Path(config["baseline_model_dir"])
    baseline_metadata = json.loads((baseline_dir / "metadata.json").read_text())
    if sha256(baseline_dir / "selected_model.joblib") != baseline_metadata["artifact_sha256"]:
        raise ValueError("Frozen baseline artifact hash mismatch")
    if sha256(Path(__file__).with_name("features.py")) != baseline_metadata["feature_code_sha256"]:
        raise ValueError("Frozen baseline feature hash mismatch")
    baseline_artifact = joblib.load(baseline_dir / "selected_model.joblib")
    games = load_games(games_path, as_of=config["as_of"])
    print(f"Building strict history features for {len(games)} real games", flush=True)
    frame = build_enhanced_table(games, as_of=config["as_of"])
    frame.to_parquet(reports_dir / "experiment_features.parquet", index=False)
    splits = temporal_split(frame, config)
    pd.concat([part[["game_id", "date", "available_at", "blue_win"]].assign(split=segment) for segment, part in splits.items()]).to_csv(reports_dir / "experiment_split_membership.csv", index=False)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-enhanced"
    run_dir = models_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    baseline_scores, baseline_predictions = _evaluate("frozen_C", baseline_artifact, splits, reports_dir)
    baseline_scores["artifact_sha256"] = baseline_metadata["artifact_sha256"]
    baseline_scores["model_version"] = baseline_metadata["model_version"]
    source_hashes = {name: sha256(Path(__file__).with_name(name)) for name in ("features.py", "enhanced_features.py", "enhanced_training.py", "enhanced.py", "evaluation.py")}
    summary = {"status": "running", "run_id": run_id, "evaluation_type": "real_gt", "config": config,
        "data_sha256": sha256(games_path), "feature_version": VERSION, "source_sha256": source_hashes,
        "splits": _split_summary(splits), "baseline": baseline_scores, "models": {},
        "scope": "Retrospective research holdout, previously inspected in phase 1; not fresh confirmatory evidence."}
    numeric, categorical = enhanced_columns()
    columns = numeric + categorical
    train = splits["train"]
    age = (pd.Timestamp(config["train_end"]) - train.date).dt.total_seconds().to_numpy() / 86400
    predictions = {}
    for candidate in config["candidates"]:
        name = candidate["name"]
        print(f"Training {name}: {len(columns)} features, {len(train)} real training games", flush=True)
        weights = np.exp2(-age / candidate["half_life_days"]) if candidate["half_life_days"] else np.ones(len(train))
        weights /= weights.mean()
        estimator = CatBoostClassifier(iterations=candidate["iterations"], depth=candidate["depth"], learning_rate=candidate["learning_rate"],
            l2_leaf_reg=candidate["l2_leaf_reg"], thread_count=config["thread_count"], random_seed=config["seed"], cat_features=categorical,
            loss_function="Logloss", has_time=True, allow_writing_files=False, verbose=False)
        estimator.fit(train[columns], train.blue_win, sample_weight=weights)
        cal = splits["calibration"]
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=config["seed"]).fit(_logits(estimator.predict_proba(cal[columns])[:, 1]), cal.blue_win)
        artifact = {"estimator": estimator, "calibrator": calibrator, "columns": columns, "numeric": numeric, "categorical": categorical,
                    "kind": "catboost", "level": "enhanced", "model_version": run_id + "/" + name}
        artifact_path = run_dir / f"{name}.joblib"
        joblib.dump(artifact, artifact_path)
        scores, predictions[name] = _evaluate(name, artifact, splits, reports_dir)
        scores.update(artifact_sha256=sha256(artifact_path), model_version=artifact["model_version"], parameters=candidate, n_features=len(columns))
        summary["models"][name] = scores
        pd.DataFrame({"feature": columns, "importance": estimator.feature_importances_}).sort_values("importance", ascending=False).to_csv(reports_dir / f"experiment_importance_{name}.csv", index=False)
        dump_json(reports_dir / "experiment_metrics.json", summary)
        print(f"{name}: validation AUC={scores['validation_raw']['roc_auc']:.6f}, LL={scores['validation_raw']['log_loss']:.6f}; test AUC={scores['test_calibrated']['roc_auc']:.6f}, accuracy={scores['test_calibrated']['accuracy']:.6f}", flush=True)
    chosen = choose_candidate(baseline_scores, summary["models"], config["validation_log_loss_tolerance"])
    best = max(summary["models"], key=lambda name: summary["models"][name]["validation_raw"]["roc_auc"])
    summary.update(status="complete", selected_candidate=chosen, best_candidate_by_validation_auc=best,
        selected_on_validation=chosen is not None, enhanced_available=chosen is not None, selected_source=chosen or "frozen_C",
        selection_rule=config["selection"], standard_model_changed=False)
    summary["paired_test_comparisons"] = {}
    test = splits["test"]
    for name in summary["models"]:
        summary["paired_test_comparisons"][name] = {
            **paired_ranking_bootstrap(test.blue_win, baseline_predictions["test"], predictions[name]["test"], test.date, config["seed"], config["bootstrap_repetitions"]),
            "log_loss": paired_day_bootstrap(test.blue_win, baseline_predictions["test"], predictions[name]["test"], test.date, seed=config["seed"], repetitions=config["bootstrap_repetitions"])}
    metadata = {"status": "trained", "run_id": run_id, "enhanced_available": chosen is not None,
        "selected_model": chosen, "model_version": run_id + "/" + chosen if chosen else None,
        "label_cutoff": max(splits[s].available_at.max() for s in ("train", "validation", "calibration")),
        "training_as_of": config["as_of"], "evaluation_data_cutoff": games.date.max(),
        "data_sha256": summary["data_sha256"], "feature_code_sha256": {k: v for k, v in source_hashes.items() if k in {"features.py", "enhanced_features.py"}},
        "splits": summary["splits"], "config": config, "selected_test_metrics": summary["models"][chosen]["test_calibrated"] if chosen else None,
        "selected_worlds_metrics": summary["models"][chosen]["test_worlds_2026_target_patch"] if chosen else None,
        "selection_rule": config["selection"], "evaluation_scope": summary["scope"],
        "environment": {"python": sys.version, "platform": platform.platform()},
        "unsupported_features": ["crowd control", "engage", "early/mid/late power curve", "team play style"],
        "limitations": ["The standardized source lacks these validated tactical descriptors; none was invented.", "Only 22 target-patch Worlds games; no reliable event-specific calibration claim.", "Local professional IDs retain unverified display-name-to-person linkage."]}
    if chosen:
        metadata["artifact_sha256"] = summary["models"][chosen]["artifact_sha256"]
        metadata["calibrator"] = summary["models"][chosen]["calibrator"]
    latest = models_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    if chosen:
        shutil.copyfile(run_dir / f"{chosen}.joblib", latest / "selected_model.joblib")
    dump_json(latest / "metadata.json", metadata)
    dump_json(run_dir / "metadata.json", metadata)
    dump_json(run_dir / "evaluation.json", summary)
    dump_json(reports_dir / "experiment_metrics.json", summary)
    print(f"Selected aggressive judgment source: {summary['selected_source']}; frozen standard model unchanged", flush=True)
    return summary
