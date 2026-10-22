"""Metrics on unmodified held-out binary outcomes; no score normalization."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score


def metrics(y, p, bins=10):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    if len(y) == 0:
        return {"n": 0}
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid probability output")
    bucket = np.minimum((p * bins).astype(int), bins - 1)
    calibration = []
    ece = 0.0
    for i in range(bins):
        selected = bucket == i
        count = int(selected.sum())
        if count:
            mean_p, rate = float(p[selected].mean()), float(y[selected].mean())
            ece += count / len(y) * abs(mean_p - rate)
            calibration.append({"lower": i / bins, "upper": (i + 1) / bins,
                                "n": count, "mean_probability": mean_p, "observed_blue_win_rate": rate})
    return {"n": len(y), "accuracy": float(accuracy_score(y, p >= 0.5)),
            "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
            "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "brier_score": float(brier_score_loss(y, p)),
            "ece_10": float(ece), "calibration_bins": calibration,
            "observed_blue_win_rate": float(y.mean())}


def temporal_split(frame, config):
    """Purge results not yet available at each segment end. Equal dates stay together."""
    if frame.game_id.duplicated().any():
        raise ValueError("Duplicate game_id: cannot split participant rows or duplicate games")
    dates = pd.to_datetime(frame.date, utc=True)
    availability = pd.to_datetime(frame.available_at, utc=True)
    edges = [pd.Timestamp(config[k]) for k in ("train_end", "validation_end", "calibration_end", "as_of")]
    if any(e.tzinfo is None for e in edges) or not all(a < b for a, b in zip(edges, edges[1:])):
        raise ValueError("Split cutoffs must be strictly increasing timezone-aware times")
    output = {}
    lower = None
    for name, upper in zip(("train", "validation", "calibration", "test"), edges):
        mask = (dates < upper) & (availability < upper)
        if lower is not None:
            mask &= dates >= lower
        output[name] = frame.loc[mask].sort_values(["date", "game_id"]).copy()
        required = config.get("min_train", 500) if name == "train" else config.get("min_eval", 100)
        if len(output[name]) < required or output[name].blue_win.nunique() != 2:
            raise ValueError(f"Insufficient real data in {name}: n={len(output[name])}, need {required} and both outcomes")
        lower = upper
    return output


def paired_day_bootstrap(y, b, c, dates, seed=2026, repetitions=500):
    """Paired day-block bootstrap for C minus B; negative loss delta favors C."""
    y, b, c = np.asarray(y), np.clip(b, 1e-12, 1 - 1e-12), np.clip(c, 1e-12, 1 - 1e-12)
    diff = -(y * np.log(c) + (1-y)*np.log(1-c)) + (y*np.log(b)+(1-y)*np.log(1-b))
    df = pd.DataFrame({"day": pd.to_datetime(dates, utc=True).dt.floor("D"), "delta": diff})
    groups = df.groupby("day").delta.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    sample = rng.integers(0, len(groups), size=(repetitions, len(groups)))
    values = groups["sum"].to_numpy()[sample].sum(axis=1) / groups["count"].to_numpy()[sample].sum(axis=1)
    return {"metric": "log_loss_C_minus_B", "point": float(diff.mean()),
            "day_block_bootstrap_95_interval": np.quantile(values, [0.025, .975]).tolist(),
            "days": len(groups), "repetitions": repetitions,
            "interpretation": "Negative favors C; diagnostic interval, one temporal holdout and one training seed."}
