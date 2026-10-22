#!/usr/bin/env python3
"""Fit pre-test support-index policy and report actual historical decisions.

Run after scripts/train_aggressive.py. The frozen 2026 test is reused for a
retrospective research comparison, never advertised as fresh confirmatory data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from worlds_predictor.evaluation import metrics
from worlds_predictor.judgment_policy import (GRADE_LABELS, apply_policy, build_policy,
                                             file_sha256, wilson_interval)
from worlds_predictor.model import dump_json
import worlds_predictor.judgment_policy as policy_module

SCOPE = "真实标签、按时间保留的 2026 测试段；该测试段已在前阶段查看，本次属于回顾性研究比较，不是全新确认性证据。"


def _summary(correct: np.ndarray, mask: np.ndarray, total: int) -> dict:
    n = int(mask.sum())
    hits = int(correct[mask].sum())
    low, high = wilson_interval(hits, n)
    return {"n": n, "correct": hits, "accuracy": hits/n if n else None, "coverage": n/total if total else 0.,
            "wilson_low": low, "wilson_high": high}


def evaluate_frame(frame: pd.DataFrame, policy: dict) -> tuple[dict, pd.DataFrame]:
    if frame.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs in decision evaluation")
    if not frame.blue_win.isin([0, 1]).all():
        raise ValueError("Evaluation targets must be actual binary match outcomes")
    decisions = [apply_policy(row.raw_score, row.calibrated_probability, policy) for row in frame.itertuples()]
    records = frame.copy()
    records["actual_side"] = np.where(records.blue_win.eq(1), "blue", "red")
    records["predicted_side"] = [item["winner_side"] for item in decisions]
    records["blue_support_index"] = [item["support_index"]["blue"] for item in decisions]
    records["red_support_index"] = [item["support_index"]["red"] for item in decisions]
    records["grade"] = [item["grade"]["key"] for item in decisions]
    records["grade_label"] = [item["grade"]["label"] for item in decisions]
    records["raw_margin"] = [item["margin"] for item in decisions]
    records["empirical_score_percentile"] = [item["empirical_score_percentile"] for item in decisions]
    records["out_of_reference_range"] = [item["out_of_reference_range"] for item in decisions]
    records["exact_tie"] = [item["tie_break"] is not None for item in decisions]
    records["correct"] = records.actual_side.eq(records.predicted_side)
    records["decision_model_version"] = policy["model_version"]
    correct = records.correct.to_numpy(bool)
    n = len(records)
    all_rows = np.ones(n, dtype=bool)
    output = {**_summary(correct, all_rows, n), "grades": [], "scope": SCOPE,
              "probability_metrics": metrics(frame.blue_win, frame.calibrated_probability),
              "raw_probability_metrics": metrics(frame.blue_win, frame.p_blue_raw),
              "out_of_reference_range_n": int(records.out_of_reference_range.sum()),
              "tie_n": int(records.exact_tie.sum()),
              "interval_note": "95% Wilson 区间按小局二项分布计算，未校正同日/同系列相关性；不是单局获胜概率。"}
    for key, label in GRADE_LABELS.items():
        mask = records.grade.eq(key).to_numpy()
        output["grades"].append({"key": key, "label": label, **_summary(correct, mask, n)})
    output["strong"] = _summary(correct, records.grade.eq("strong").to_numpy(), n)
    return output, records


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"game_id": str, "league": str, "patch": str})
    frame["date"] = pd.to_datetime(frame.date, utc=True)
    frame["available_at"] = pd.to_datetime(frame.available_at, utc=True)
    return frame


def _make_policy(name: str, score: dict, report: dict, reports: Path, source_engine: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    frames = {segment: _load_frame(reports / f"experiment_predictions_{name}_{segment}.csv") for segment in ("validation", "calibration", "test")}
    sets = [set(part.game_id) for part in frames.values()]
    if any(a & b for i, a in enumerate(sets) for b in sets[i+1:]):
        raise ValueError("A game appears across validation, calibration or test")
    config = report["config"]
    for segment, lower, upper in (("validation", config["train_end"], config["validation_end"]),
                                  ("calibration", config["validation_end"], config["calibration_end"]),
                                  ("test", config["calibration_end"], config["as_of"])):
        part = frames[segment]
        if not ((part.date >= pd.Timestamp(lower)) & (part.date < pd.Timestamp(upper)) & (part.available_at < pd.Timestamp(upper))).all():
            raise ValueError(f"{segment} contains an out-of-range or not-yet-available result")
    cutoff = max(pd.Timestamp(report["splits"][segment]["last_result_available"]) for segment in ("train", "validation", "calibration"))
    policy = build_policy(frames["validation"], model_version=score["model_version"], artifact_sha256=score["artifact_sha256"],
                          calibrator_coef=score["calibrator"]["coefficient"], calibrator_intercept=score["calibrator"]["intercept"],
                          label_cutoff=cutoff.isoformat(), source_engine=source_engine,
                          metadata={"prediction_source": name, "data_sha256": report["data_sha256"], "selection_rule": report["selection_rule"],
                                    "test_not_used_for_policy_fit": True, "experiment_run_id": report["run_id"]})
    return policy, frames


def run(reports_dir: Path) -> dict:
    reports = Path(reports_dir)
    report = json.loads((reports / "experiment_metrics.json").read_text())
    if report["status"] != "complete":
        raise ValueError("Training and held-out predictions must be complete before policy evaluation")
    selected = report["selected_source"]
    frozen_policy, frozen_frames = _make_policy("frozen_C", report["baseline"], report, reports, "frozen")
    if selected == "frozen_C":
        selected_policy, selected_frames = frozen_policy, frozen_frames
    else:
        if not report["enhanced_available"] or report["selected_candidate"] != selected:
            raise ValueError("Inconsistent validation-only model selection metadata")
        selected_policy, selected_frames = _make_policy(selected, report["models"][selected], report, reports, "enhanced")
    if not selected_frames["test"].game_id.equals(frozen_frames["test"].game_id) or not selected_frames["test"].blue_win.equals(frozen_frames["test"].blue_win):
        raise ValueError("Selected and original test IDs/labels differ")
    selected_test, records = evaluate_frame(selected_frames["test"], selected_policy)
    frozen_test, frozen_records = evaluate_frame(frozen_frames["test"], frozen_policy)
    records["original_calibrated_probability"] = frozen_frames["test"].calibrated_probability.to_numpy()
    records["original_predicted_side"] = frozen_records.predicted_side.to_numpy()
    records["original_correct"] = frozen_records.correct.to_numpy()
    records.to_csv(reports / "judgment_predictions.csv", index=False)
    frozen_records.to_csv(reports / "judgment_baseline_predictions.csv", index=False)
    target = records.league.str.casefold().isin(["wlds", "worlds"]) & records.patch.isin(["16.20", "26.20"])
    target_summary, target_records = evaluate_frame(selected_frames["test"].loc[target], selected_policy)
    target_records.to_csv(reports / "judgment_worlds_predictions.csv", index=False)
    same_patch = records.patch.isin(["16.20", "26.20"])
    same_patch_summary, _ = evaluate_frame(selected_frames["test"].loc[same_patch], selected_policy)
    by_league = {str(league): evaluate_frame(part, selected_policy)[0] for league, part in selected_frames["test"].groupby("league")}
    by_patch = {str(patch): evaluate_frame(part, selected_policy)[0] for patch, part in selected_frames["test"].groupby("patch")}
    summary = {
        "status": "complete", "generated_at": datetime.now(timezone.utc).isoformat(), "evaluation_type": "real_gt",
        "source_engine": selected_policy["source_engine"], "selected_source": selected,
        "model_version": selected_policy["model_version"], "artifact_sha256": selected_policy["artifact_sha256"],
        "policy_version": selected_policy["policy_version"], "label_cutoff": selected_policy["label_cutoff"],
        "data_cutoff": str(selected_frames["test"].date.max()), "scope": SCOPE,
        "deployment_test": selected_test, "baseline_test": frozen_test,
        "original_model": {"version": report["baseline"]["model_version"],
                           "test_calibrated": report["baseline"]["test_calibrated"],
                           "test_raw": report["baseline"]["test_raw"], "artifact_unchanged": True},
        "validation_policy_fit": selected_policy["strong_validation"],
        "target_worlds_test": target_summary, "same_patch_test": same_patch_summary,
        "test_by_league": by_league, "test_by_patch": by_patch,
        "winner_disagreement_with_original_n": int((records.predicted_side != records.original_predicted_side).sum()),
        "aggressive_extreme_quantitative_decisions_identical": True,
        "standard_uses_frozen_probability": True,
        "mode_definition": "Standard keeps the frozen calibrated probability. Aggressive/extreme share this judgment source, support index and thresholds; extreme changes wording only. The standard model can disagree when the enhanced source is selected.",
        "support_index_definition": selected_policy["interpretation"],
        "strong_grade_gate": {"minimum_index": 85, "validation_minimum_n": 100, "validation_minimum_wilson_low": .60,
                              "passed": selected_policy["strong_validation"]["passed"],
                              "scope": "Gate and ECDF fitted before test; validation gate performance is not unbiased held-out evidence."},
        "limitations": ["Index is not a calibrated probability and must not be displayed with a percent sign.",
                        "The 2026 test has already been inspected; this is a retrospective research comparison.",
                        "Only 22 target-patch Worlds maps, insufficient to establish event-specific reliability.",
                        "Wilson intervals ignore within-day and series dependence; use experiment paired day-block results for model comparison.",
                        "The final calibrator was fit after validation. Validation decisions are policy-fitting evidence, never independent accuracy claims.",
                        "Strength labels express model margin rank; sample coverage and deployment reliability are reported separately."],
        "evidence_files": {p.name: {"sha256": file_sha256(p), "bytes": p.stat().st_size} for p in sorted(reports.glob("experiment_predictions_*.csv"))},
    }
    dump_json(reports / "judgment_policy.json", selected_policy)
    dump_json(reports / "judgment_baseline_policy.json", frozen_policy)
    dump_json(reports / "judgment_evaluation.json", summary)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_sha256": file_sha256(reports / "judgment_policy.json"),
        "evaluation_sha256": file_sha256(reports / "judgment_evaluation.json"),
        "policy_code_sha256": file_sha256(Path(policy_module.__file__)),
        "evaluation_code_sha256": file_sha256(Path(__file__)),
        "experiment_report_sha256": file_sha256(reports / "experiment_metrics.json"),
        "artifact_sha256": selected_policy["artifact_sha256"], "model_version": selected_policy["model_version"],
        "prediction_csv_sha256": file_sha256(reports / "judgment_predictions.csv"),
        "baseline_prediction_csv_sha256": file_sha256(reports / "judgment_baseline_predictions.csv"),
        "worlds_prediction_csv_sha256": file_sha256(reports / "judgment_worlds_predictions.csv"),
    }
    dump_json(reports / "judgment_manifest.json", manifest)
    def pct(value):
        return "无样本" if value is None else f"{value*100:.2f}%"
    lines = ["# 激进判断：真实历史评估", "", f"判断来源：`{selected_policy['model_version']}`；原校准模型保持不变。", "", SCOPE, "",
             "支持指数是原始模型决策间隔相对验证集分布的百分位，不是胜率。极限模式不改变数值、胜者或阈值。", "",
             f"原模型：Log Loss {frozen_test['probability_metrics']['log_loss']:.6f}；Brier {frozen_test['probability_metrics']['brier_score']:.6f}；准确率 {pct(frozen_test['accuracy'])}。",
             f"当前判断：{selected_test['n']} 局；准确率 {pct(selected_test['accuracy'])}；强倾向 {selected_test['strong']['n']} 局，命中率 {pct(selected_test['strong']['accuracy'])}，覆盖 {pct(selected_test['strong']['coverage'])}。", "",
             "| 优势等级 | 场次 | 命中率 | 覆盖比例 | Wilson 95% 区间 |", "|---|---:|---:|---:|---|" ]
    for row in selected_test["grades"]:
        interval = "无样本" if row["n"] == 0 else f"{pct(row['wilson_low'])}–{pct(row['wilson_high'])}"
        lines.append(f"| {row['label']} | {row['n']} | {pct(row['accuracy'])} | {pct(row['coverage'])} | {interval} |")
    lines += ["", f"Worlds 目标版本：{target_summary['n']} 局，判断准确率 {pct(target_summary['accuracy'])}；样本太少，不能声称赛事专项可靠。", "",
              "强倾向阈值固定为支持指数 ≥85，且验证样本中该组至少100局、Wilson下界≥60%。验证组用于拟合规则，不是独立测试命中率。", "",
              "统计区间没有校正系列赛与同日相关性。逐局真实赛果对照见 `judgment_predictions.csv`；目标世界赛见 `judgment_worlds_predictions.csv`。", "",
              "## 复现", "", "```bash", ".venv/bin/python scripts/train_aggressive.py", ".venv/bin/python scripts/evaluate_aggressive.py", "```", ""]
    (reports / "judgment_evaluation.md").write_text("\n".join(lines))
    print(json.dumps({"selected": selected, "source_engine": selected_policy["source_engine"], "test_n": selected_test["n"],
                      "accuracy": selected_test["accuracy"], "strong": selected_test["strong"], "worlds_n": target_summary["n"]}, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/aggressive"))
    run(parser.parse_args().reports_dir)
