"""Trusted local challenger inference. Standard probability artifacts stay intact."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import Pool

from .data import load_games
from .enhanced_features import enhanced_features_for_game
from .model import ModelUnavailableError, _logits, request_to_game, sha256
from .schemas import PredictionRequest


def load_enhanced(artifact_dir=Path("models/aggressive-experiment/latest")):
    directory = Path(artifact_dir)
    try:
        metadata = json.loads((directory / "metadata.json").read_text())
        if not metadata.get("enhanced_available") or metadata.get("status") != "trained":
            raise ModelUnavailableError("Enhanced candidate did not pass its validation-only deployment gate")
        path = directory / "selected_model.joblib"
        if sha256(path) != metadata["artifact_sha256"]:
            raise ModelUnavailableError("Enhanced artifact integrity mismatch")
        for module, expected in metadata["feature_code_sha256"].items():
            if sha256(Path(__file__).with_name(module)) != expected:
                raise ModelUnavailableError("Enhanced feature implementation changed; retraining required")
        artifact = joblib.load(path)
        if float(artifact["calibrator"].coef_[0, 0]) <= 0:
            raise ModelUnavailableError("Enhanced calibration reverses ranking")
        return artifact, metadata
    except ModelUnavailableError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModelUnavailableError(f"Enhanced artifact unavailable: {exc}") from exc


def predict_enhanced(payload, games_path=Path("data/processed/games.parquet"), artifact_dir=Path("models/aggressive-experiment/latest")):
    payload = PredictionRequest.model_validate(payload).model_dump(mode="json")
    artifact, metadata = load_enhanced(artifact_dir)
    cutoff = pd.Timestamp(payload["as_of"])
    if cutoff <= pd.Timestamp(metadata["label_cutoff"]):
        raise ValueError(f"as_of must be later than enhanced model label cutoff {metadata['label_cutoff']}")
    history = load_games(Path(games_path), as_of=cutoff.isoformat())
    if history.empty:
        raise ModelUnavailableError("No history strictly before as_of for enhanced judgment")
    game = request_to_game(payload)
    features, coverage = enhanced_features_for_game(history, game, cutoff)
    frame = pd.DataFrame([features])[artifact["columns"]]
    try:
        estimator = artifact["estimator"]
        raw = float(estimator.predict(frame, prediction_type="RawFormulaVal")[0])
        uncalibrated = estimator.predict_proba(frame)[:, 1]
        probability = float(artifact["calibrator"].predict_proba(_logits(uncalibrated))[0, 1])
        values = estimator.get_feature_importance(Pool(frame, cat_features=artifact["categorical"]), type="ShapValues")[0]
    except Exception as exc:
        raise ModelUnavailableError(f"Enhanced inference failed: {exc}") from exc
    if not np.isfinite(probability) or not 0 <= probability <= 1 or not np.isfinite(values).all():
        raise ModelUnavailableError("Enhanced model returned invalid output")
    return {
        "raw_score": raw, "calibrated_probability": probability,
        "feature_values": features, "categorical": artifact["categorical"],
        "contributions": [{"feature": name, "value": features[name], "contribution": float(value)} for name, value in zip(artifact["columns"], values[:-1])],
        "base_value": float(values[-1]), "reconstruction_error": float(abs(values.sum() - raw)),
        "metadata": metadata, "coverage": coverage,
    }
