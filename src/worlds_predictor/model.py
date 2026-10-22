"""Chronological training, held-out evaluation, and fail-closed prediction."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .evaluation import metrics, paired_day_bootstrap, temporal_split
from .features import build_feature_table, feature_columns, features_for_game


class ModelUnavailableError(RuntimeError):
    """Missing, incompatible, or temporally invalid artifact; never fabricate odds."""


def dump_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _logits(p):
    p = np.clip(np.asarray(p), 1e-6, 1-1e-6)
    return np.log(p / (1-p)).reshape(-1, 1)


def make_estimator(kind, numeric, categorical, config):
    if kind == "logistic":
        return Pipeline([
            ("features", ColumnTransformer([
                ("numeric", StandardScaler(), numeric),
                ("categorical", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=5), categorical),
            ])),
            ("classifier", LogisticRegression(C=0.15, max_iter=1200, solver="liblinear", random_state=config["seed"]))
        ])
    return CatBoostClassifier(iterations=config["iterations"], depth=config["depth"],
                              learning_rate=config["learning_rate"], l2_leaf_reg=config["l2_leaf_reg"],
                              random_seed=config["seed"], thread_count=config["thread_count"],
                              loss_function="Logloss", cat_features=categorical, has_time=True,
                              allow_writing_files=False, verbose=False)


def _fit(estimator, kind, x, y, weights):
    if kind == "logistic":
        estimator.fit(x, y, classifier__sample_weight=weights)
    else:
        estimator.fit(x, y, sample_weight=weights)
    return estimator


def _split_summary(splits):
    return {k: {"n": len(v), "first_game": v.date.min(), "last_game": v.date.max(),
                "last_result_available": v.available_at.max(), "blue_wins": int(v.blue_win.sum())}
            for k, v in splits.items()}


def _cohort_metrics(frame, p, field):
    result = {}
    for value, indices in frame.groupby(field, dropna=False).indices.items():
        result[str(value)] = metrics(frame.iloc[indices].blue_win, p[indices])
    return result


def train(games_path, config, models_dir="models", reports_dir="reports"):
    from .data import load_games
    games_path, models_dir, reports_dir = Path(games_path), Path(models_dir), Path(reports_dir)
    games = load_games(games_path, as_of=config["as_of"])
    if games.empty:
        raise ValueError("No validated real historical games available")
    print(f"Generating causal features for {len(games)} real games", flush=True)
    frame = build_feature_table(games, as_of=config["as_of"])
    splits = temporal_split(frame, config)
    source_hashes = {str(p.name): sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    fingerprint = hashlib.sha256(json.dumps({"config": config, "source": source_hashes,
                                             "games_sha256": sha256(games_path)}, sort_keys=True).encode()).hexdigest()[:12]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + fingerprint
    run_dir = models_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    reports_dir.mkdir(parents=True, exist_ok=True)
    split_records = pd.concat([part[["game_id", "date", "available_at", "blue_win"]].assign(split=name)
                               for name, part in splits.items()], ignore_index=True)
    split_records.to_csv(reports_dir / "split_membership.csv", index=False)
    frame.to_parquet(reports_dir / "features.parquet", index=False)
    summary = {"run_id": run_id, "status": "running", "config": config,
               "evaluation_type": "real_gt", "data_sha256": sha256(games_path),
               "source_sha256": source_hashes, "splits": _split_summary(splits),
               "protocol": "Frozen estimators; sequential historical features updated only after earlier results become available. Separate validation model selection, calibration and independent test.",
               "models": {}, "selected_model": None}
    candidates = [(level, kind, config["half_life_days"]) for kind in ("logistic", "catboost") for level in "ABC"]
    if config.get("run_sensitivity", True):
        candidates.append(("C", "catboost", None))
    test_predictions = {}
    artifacts = {}
    for level, kind, half_life in candidates:
        name = f"{level}_{kind}" + ("_uniform" if half_life is None else "")
        numeric, categorical = feature_columns(level)
        cols = numeric + categorical
        print(f"Training {name}: {len(cols)} features; train={len(splits['train'])}", flush=True)
        train_frame = splits["train"]
        age = (pd.Timestamp(config["train_end"]) - pd.to_datetime(train_frame.date, utc=True)).dt.total_seconds() / 86400
        weights = np.exp2(-age.to_numpy() / half_life) if half_life else np.ones(len(train_frame))
        weights = weights / weights.mean()
        estimator = _fit(make_estimator(kind, numeric, categorical, config), kind,
                         train_frame[cols], train_frame.blue_win, weights)
        calibration_frame = splits["calibration"]
        raw_calibration = estimator.predict_proba(calibration_frame[cols])[:, 1]
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=config["seed"])
        calibrator.fit(_logits(raw_calibration), calibration_frame.blue_win)
        scores = {"level": level, "kind": kind, "half_life_days": half_life,
                  "n_features": len(cols), "calibration_method": "regularized sigmoid on separate chronological calibration block"}
        for segment in ("validation", "calibration", "test"):
            part = splits[segment]
            p_raw = estimator.predict_proba(part[cols])[:, 1]
            scores[segment + "_raw"] = metrics(part.blue_win, p_raw)
            # Calibration is fitted later than validation. Do not report later-calibrated validation as selection evidence.
            if segment != "validation":
                p = calibrator.predict_proba(_logits(p_raw))[:, 1]
                scores[segment + "_calibrated"] = metrics(part.blue_win, p)
            if segment == "test":
                test_predictions[name] = p
                pred = part[["game_id", "date", "league", "patch", "blue_win"]].copy()
                pred["p_blue_raw"], pred["p_blue"] = p_raw, p
                pred.to_csv(reports_dir / f"predictions_{name}.csv", index=False)
                scores["test_by_patch"] = _cohort_metrics(part, p, "patch")
                scores["test_by_league"] = _cohort_metrics(part, p, "league")
                target_worlds = part.league.eq("WLDs") & part.patch.eq("16.20")
                scores["test_worlds_2026_target_patch"] = metrics(part.loc[target_worlds].blue_win, p[target_worlds])
                seen = set(train_frame.league.astype(str))
                scores["test_seen_leagues"] = metrics(part.loc[part.league.isin(seen)].blue_win, p[part.league.isin(seen)])
                scores["test_unseen_leagues"] = metrics(part.loc[~part.league.isin(seen)].blue_win, p[~part.league.isin(seen)])
                part = part.assign(month=pd.to_datetime(part.date, utc=True).dt.strftime("%Y-%m"))
                scores["test_by_month"] = _cohort_metrics(part, p, "month")
        artifact = {"estimator": estimator, "calibrator": calibrator, "columns": cols,
                    "numeric": numeric, "categorical": categorical, "level": level, "kind": kind,
                    "model_version": run_id + "/" + name}
        artifact_path = run_dir / f"{name}.joblib"
        joblib.dump(artifact, artifact_path)
        artifacts[name] = artifact_path
        scores["artifact_sha256"] = sha256(artifact_path)
        if kind == "logistic":
            names = estimator.named_steps["features"].get_feature_names_out()
            pd.DataFrame({"feature": names, "coefficient": estimator.named_steps["classifier"].coef_[0]}).sort_values("coefficient").to_csv(reports_dir / f"coefficients_{name}.csv", index=False)
            scores["intercept"] = estimator.named_steps["classifier"].intercept_.tolist()
        else:
            pd.DataFrame({"feature": cols, "importance": estimator.feature_importances_}).sort_values("importance", ascending=False).to_csv(reports_dir / f"importance_{name}.csv", index=False)
        summary["models"][name] = scores
        dump_json(reports_dir / "metrics.json", summary)
        print(f"{name}: test logloss={scores['test_calibrated']['log_loss']:.5f} AUC={scores['test_calibrated']['roc_auc']:.5f}", flush=True)
    # Selection is intentionally based ONLY on pre-calibration validation log loss.
    chosen = min(summary["models"], key=lambda n: summary["models"][n]["validation_raw"]["log_loss"])
    summary["selected_model"] = chosen
    summary["selection_rule"] = "Minimum raw validation log loss across predeclared candidates. Test metrics never select models."
    summary["bp_comparison"] = {kind: paired_day_bootstrap(splits["test"].blue_win,
                                   test_predictions[f"B_{kind}"], test_predictions[f"C_{kind}"],
                                   splits["test"].date, seed=config["seed"])
                                for kind in ("logistic", "catboost")}
    if config.get("run_sensitivity", True):
        summary["recency_comparison"] = {
            "weighted_C_test": summary["models"]["C_catboost"]["test_calibrated"],
            "uniform_C_test": summary["models"]["C_catboost_uniform"]["test_calibrated"],
            "note": "The uniform-weight model is a predeclared selection candidate and recency sensitivity arm; deployment selected on validation only."}
    summary["status"] = "complete"
    summary["limitations"] = [
        "One chronological holdout and one training seed; no accuracy guarantee or causal BP effect.",
        "Current downloadable snapshot cannot prove historical publication times; available_at is a conservative assumed outcome-availability boundary.",
        "Name-based local pro IDs are stable within registry, but source lacks independent player IDs; unresolved real-person ambiguities remain.",
        "C minus B bundles BP and patch; association is confounded by skill, opponent and draft selection.",
        "Per-league and unseen-league cohorts assess transport descriptively, not a dedicated leave-region-out experiment.",
        "Historical bans/first-pick values are used only as pregame metadata; timestamp availability of final BP is the caller's responsibility."]
    dump_json(reports_dir / "metrics.json", summary)
    dump_json(run_dir / "evaluation.json", summary)
    label_cutoff = max(splits[k].available_at.max() for k in ("train", "validation", "calibration"))
    quality_file = games_path.parent / "quality_report.json"
    quality = json.loads(quality_file.read_text()) if quality_file.exists() else {}
    metadata = {"status": "trained", "run_id": run_id, "selected_model": chosen,
                "model_version": run_id + "/" + chosen, "label_cutoff": label_cutoff,
                "training_as_of": config["as_of"], "evaluation_data_cutoff": games.date.max(),
                "data_sha256": summary["data_sha256"], "artifact_sha256": summary["models"][chosen]["artifact_sha256"],
                "feature_code_sha256": source_hashes.get("features.py"),
                "identity_limitation": summary["limitations"][2], "splits": summary["splits"],
                "config": config, "selected_test_metrics": summary["models"][chosen]["test_calibrated"],
                "environment": {"python": sys.version, "platform": platform.platform()},
                "quality_report_available": bool(quality)}
    dump_json(run_dir / "metadata.json", metadata)
    latest = models_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    # A local trusted joblib artifact, never an artifact uploaded through the API.
    shutil.copyfile(artifacts[chosen], latest / "selected_model.joblib")
    dump_json(latest / "metadata.json", metadata)
    _write_results_markdown(summary, reports_dir / "RESULTS.md")
    return summary


def _write_results_markdown(result, path):
    lines = ["# Program-generated real-data evaluation", "", f"Run: `{result['run_id']}`", "",
             result["protocol"], "", "| Model | Validation LL | Test accuracy | Test AUC | Test LL | Test Brier | Test ECE |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, value in result["models"].items():
        m = value["test_calibrated"]
        lines.append(f"| {name} | {value['validation_raw']['log_loss']:.5f} | {m['accuracy']:.5f} | {m['roc_auc']:.5f} | {m['log_loss']:.5f} | {m['brier_score']:.5f} | {m['ece_10']:.5f} |")
    lines.extend(["", f"Deployment: **{result['selected_model']}**, chosen using validation only.", "", "## B versus C"])
    for name, comparison in result["bp_comparison"].items():
        lines.append(f"- {name}: C−B test log loss {comparison['point']:.6f}; day-block 95% interval {comparison['day_block_bootstrap_95_interval']}.")
    selected = result["models"][result["selected_model"]]
    lines.extend(["", "## Event and patch coverage", ""])
    for field, key, label in (("test_by_league", "WLDs", "Worlds 2026"), ("test_by_patch", "16.20", "Source 16.20 / public 26.20, all leagues")):
        cohort = selected[field].get(key)
        if cohort:
            lines.append(f"- {label}: n={cohort['n']}, accuracy={cohort['accuracy']:.5f}, AUC={cohort['roc_auc']}, Log Loss={cohort['log_loss']:.5f}. Small cohorts are descriptive only.")
    target = selected["test_worlds_2026_target_patch"]
    if target["n"]:
        lines.append(f"- Target intersection WLDs + source 16.20/public 26.20: n={target['n']}, accuracy={target['accuracy']:.5f}, AUC={target['roc_auc']}, Log Loss={target['log_loss']:.5f}, Brier={target['brier_score']:.5f}, ECE={target['ece_10']:.5f}. This is too small to support reliable Worlds-specific accuracy or calibration.")
    lines.extend(["", "## Limits", ""] + ["- " + x for x in result["limitations"]])
    Path(path).write_text("\n".join(lines) + "\n")


def request_to_game(payload):
    from .context import model_league, model_patch
    game = {"game_id": payload.get("game_id") or "__request__", "date": pd.Timestamp(payload["scheduled_start"]),
            "league": model_league(payload["league"]), "patch": model_patch(payload["patch"]), "first_pick_side": payload.get("first_pick_side", "unknown")}
    for side in ("blue", "red"):
        team = payload[side]
        game[f"{side}_team_id"] = team["team_id"]
        game[f"{side}_team_name"] = team.get("team_name") or team["team_id"]
        for player in team["players"]:
            for suffix, key in (("player_id", "player_id"), ("player_name", "player_id"), ("champion", "champion")):
                game[f"{side}_{player['role']}_{suffix}"] = player[key]
        bans = team.get("bans", [])
        for i in range(5):
            game[f"{side}_ban{i+1}"] = bans[i] if i < len(bans) else None
    return game


def predict(payload, model_dir=Path("models/latest"), games_path=Path("data/processed/games.parquet")):
    from .data import load_games
    from .schemas import PredictionRequest
    payload = PredictionRequest.model_validate(payload).model_dump(mode="json")
    model_dir, games_path = Path(model_dir), Path(games_path)
    artifact_path, metadata_path = model_dir / "selected_model.joblib", model_dir / "metadata.json"
    if not artifact_path.is_file() or not metadata_path.is_file() or not games_path.is_file():
        raise ModelUnavailableError("No valid trained model/history. Import real CSVs and run worlds-bp train first.")
    try:
        metadata = json.loads(metadata_path.read_text())
        if metadata["status"] != "trained" or sha256(artifact_path) != metadata["artifact_sha256"]:
            raise ValueError("Artifact integrity mismatch")
        if sha256(Path(__file__).with_name("features.py")) != metadata["feature_code_sha256"]:
            raise ValueError("Feature implementation changed: retraining required")
    except (KeyError, ValueError) as exc:
        raise ModelUnavailableError(str(exc)) from exc
    cutoff = pd.Timestamp(payload["as_of"])
    if cutoff <= pd.Timestamp(metadata["label_cutoff"]):
        raise ValueError(f"as_of must be later than this model's label cutoff {metadata['label_cutoff']}; train an earlier artifact for historical backtests")
    registry_path = games_path.parent / "player_registry.csv"
    if registry_path.exists():
        from .lookup import resolve_request_ids
        alias_path = os.environ.get("WORLDS_ALIASES_PATH")
        payload = resolve_request_ids(payload, registry_path, Path(alias_path) if alias_path else None)
        payload = PredictionRequest.model_validate(payload).model_dump(mode="json")
    history = load_games(games_path, as_of=cutoff.isoformat())
    if history.empty:
        raise ModelUnavailableError("No history strictly before as_of")
    game = request_to_game(payload)
    feature, coverage = features_for_game(history, game, as_of=cutoff.isoformat())
    try:
        artifact = joblib.load(artifact_path)
        x = pd.DataFrame([feature])[artifact["columns"]]
        p_raw = artifact["estimator"].predict_proba(x)[:, 1]
        p = float(artifact["calibrator"].predict_proba(_logits(p_raw))[0, 1])
    except Exception as exc:
        raise ModelUnavailableError(f"Model artifact cannot predict: {exc}") from exc
    if not np.isfinite(p) or not 0 <= p <= 1:
        raise ModelUnavailableError("Invalid model probability")
    return {"blue_win_probability": p, "red_win_probability": 1-p,
            "model_version": metadata["model_version"], "selected_model": metadata["selected_model"],
            "as_of": cutoff.isoformat(), "scheduled_start": payload["scheduled_start"],
            "model_label_cutoff": metadata["label_cutoff"], "data_cutoff": history.date.max().isoformat(),
            "history_result_available_cutoff": history.available_at.max().isoformat(),
            "sample_coverage": coverage,
            "training_samples": {key: metadata["splits"][key] for key in ("train", "validation", "calibration") if key in metadata["splits"]},
            "first_pick_side": payload["first_pick_side"],
            "input_league": payload["league"], "model_league": game["league"],
            "input_patch": payload["patch"], "model_patch": game["patch"],
            "patch_namespace_note": "Explicit Worlds 2026 public 26.20 corresponds to source/Data Dragon 16.20; raw training source patch values are preserved.",
            "warnings": [metadata["identity_limitation"], "Probabilities are calibrated estimates, not guaranteed outcomes. Final BP must already be known at as_of."]}
