"""Render actual chronological holdout metrics as standalone PNG/PDF figures.

Usage: python -m worlds_predictor.plots --metrics reports/metrics.json
       --output reports/calibration.png
No fit, smoothing, generated observations or re-estimation occurs in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


COLORS = {"A": "#3771A3", "B": "#2A837C", "C": "#C7653A", "selected": "#5A3D82"}


def _label(name: str) -> str:
    return name.replace("_logistic", " logistic").replace("_catboost_uniform", " CatBoost · uniform").replace("_catboost", " CatBoost")


def render_metrics(metrics_path: str | Path, output: str | Path) -> dict:
    metrics_path, output = Path(metrics_path), Path(output)
    raw = metrics_path.read_bytes()
    metrics = json.loads(raw)
    if metrics.get("status") != "complete" or metrics.get("evaluation_type") != "real_gt":
        raise ValueError("Figure requires completed metrics based on actual dataset ground truth")
    test = metrics["splits"]["test"]
    n = int(test["n"])
    selected = metrics["selected_model"]
    models = metrics["models"]
    curve_names = list(dict.fromkeys(["A_catboost", "B_catboost", "C_catboost", selected]))
    if n <= 0 or any(name not in models for name in curve_names):
        raise ValueError("Missing completed test results for required models")
    for name, entry in models.items():
        measured = entry["test_calibrated"]
        if measured["n"] != n or sum(b["n"] for b in measured["calibration_bins"]) != n:
            raise ValueError(f"Test sample/bin count mismatch for {name}")
        if not math.isfinite(measured["log_loss"]) or measured["log_loss"] < 0:
            raise ValueError(f"Invalid measured log loss for {name}")
        for b in measured["calibration_bins"]:
            if b["n"] <= 0 or not 0 <= b["mean_probability"] <= 1 or not 0 <= b["observed_blue_win_rate"] <= 1:
                raise ValueError(f"Invalid observed calibration bin for {name}")

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#89919A", "axes.labelcolor": "#253341",
        "text.color": "#253341", "xtick.color": "#4A5560", "ytick.color": "#4A5560",
        "savefig.facecolor": "white", "figure.facecolor": "white", "pdf.fonttype": 42,
    })
    figure = plt.figure(figsize=(14.6, 7.2))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.03, 1], left=0.07, right=0.975, bottom=0.20, top=0.78, wspace=0.54)
    reliability = figure.add_subplot(grid[0, 0])
    losses = figure.add_subplot(grid[0, 1])
    figure.suptitle("Worlds 2026 BP Predictor | Chronological holdout", x=0.07, ha="left", y=0.97, fontsize=19, fontweight="bold")
    first, last = test["first_game"][:10], test["last_game"][:10]
    figure.text(0.07, 0.91, f"{first} to {last} · {n:,} real professional games · Calibrated probabilities", fontsize=12)
    figure.text(0.07, 0.865, "Frozen estimators; earlier available results update historical features. Model selected on validation, before test.", fontsize=10.5, color="#53616E")

    reliability.plot([0, 1], [0, 1], color="#ABB3BA", linestyle="--", linewidth=1.2, label="Perfect calibration (reference)", zorder=1)
    max_count = max(b["n"] for name in curve_names for b in models[name]["test_calibrated"]["calibration_bins"])
    curve_evidence = {}
    for name in curve_names:
        measured = models[name]["test_calibrated"]
        bins = sorted(measured["calibration_bins"], key=lambda b: b["mean_probability"])
        xs = [b["mean_probability"] for b in bins]
        ys = [b["observed_blue_win_rate"] for b in bins]
        color = COLORS["selected"] if name == selected else COLORS[name[0]]
        label = f"{_label(name)}{' (selected)' if name == selected else ''}"
        label += f"  |  ECE {measured['ece_10']:.3f}"
        reliability.plot(xs, ys, color=color, linewidth=2.3 if name == selected else 1.6, alpha=0.94, label=label)
        reliability.scatter(xs, ys, s=[15 + 65 * b["n"] / max_count for b in bins], color=color, edgecolor="white", linewidth=0.7, zorder=3)
        curve_evidence[name] = {"n": measured["n"], "ece_10": measured["ece_10"], "calibration_bins": bins}
    reliability.set(xlim=(0, 1), ylim=(0, 1), xlabel="Mean predicted blue win probability", ylabel="Observed blue win frequency")
    reliability.set_title("Reliability by probability bin", fontsize=13, fontweight="bold", loc="left", pad=13)
    reliability.xaxis.set_major_locator(MultipleLocator(0.2))
    reliability.yaxis.set_major_locator(MultipleLocator(0.2))
    reliability.grid(alpha=0.18)
    reliability.legend(loc="upper left", frameon=True, framealpha=0.93, edgecolor="#DFE4E8", fontsize=8.4, borderpad=0.7)

    order = list(models)
    values = [models[name]["test_calibrated"]["log_loss"] for name in order]
    span = max(values) - min(values)
    pad = max(span * 0.2, 0.005)
    losses.set_xlim(min(values) - pad, max(values) + pad * 2.4)
    losses.set_ylim(-0.7, len(order) - 0.3)
    for index, (name, value) in enumerate(zip(order, values)):
        color = COLORS["selected"] if name == selected else COLORS[name[0]]
        losses.plot(value, index, "D" if name == selected else "o", markersize=8.5 if name == selected else 7.5, color=color, zorder=3)
        losses.annotate(f"{value:.4f}", xy=(value, index), xytext=(9, 0), textcoords="offset points", va="center", fontsize=10, fontweight="bold" if name == selected else "normal")
    losses.set_yticks(range(len(order)), [_label(name) + ("  ★" if name == selected else "") for name in order])
    losses.invert_yaxis()
    losses.set_xlabel("Log loss · lower is better")
    losses.set_title("Test log loss across all fitted models", fontsize=13, fontweight="bold", loc="left", pad=13)
    losses.grid(axis="x", alpha=0.2)
    losses.xaxis.set_major_locator(MultipleLocator(0.01))
    losses.tick_params(axis="y", length=0, pad=8)
    losses.spines["left"].set_visible(False)

    figure.text(0.07, 0.12, "Reliability: only nonempty observed bins; marker size reflects bin count. Small tail bins can be noisy.", fontsize=9.6, color="#53616E")
    figure.text(0.07, 0.082, "A: team + side + recent form     B: A + player identity/form     C: B + BP, proficiency, matchups, synergy and patch", fontsize=9.6, color="#53616E")
    figure.text(0.07, 0.045, f"Source: {metrics_path.name}  |  Run: {metrics['run_id']}  |  No synthetic observations; not a Worlds-only accuracy claim.", fontsize=8.8, color="#69747F")
    output.parent.mkdir(parents=True, exist_ok=True)
    png = output.with_suffix(".png")
    pdf = output.with_suffix(".pdf")
    figure.savefig(png, dpi=180)
    figure.savefig(pdf)
    plt.close(figure)
    evidence = {
        "input_path": str(metrics_path), "input_sha256": hashlib.sha256(raw).hexdigest(),
        "run_id": metrics["run_id"], "test": test, "selected_model": selected,
        "reliability_curves": curve_evidence,
        "test_calibrated_log_loss": dict(zip(order, values)),
        "outputs": {"png": str(png), "pdf": str(pdf)},
        "note": "All empirical points copied from real_gt test_calibrated metrics; diagonal is a labeled mathematical reference.",
    }
    output.with_suffix(".plot_manifest.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=Path("reports/metrics.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/calibration.png"))
    args = parser.parse_args()
    result = render_metrics(args.metrics, args.output)
    print(json.dumps({"outputs": result["outputs"], "run_id": result["run_id"], "n_test": result["test"]["n"]}, indent=2))


if __name__ == "__main__":
    main()
