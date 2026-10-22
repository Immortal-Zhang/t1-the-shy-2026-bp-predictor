"""Single-map prediction service; no model means no probability response."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request

from .context import enforce_worlds_context, is_worlds_league
from .lookup import search_players
from .schemas import PredictionRequest
from .worlds import DEFAULT_CONFIG, PROJECT_ROOT, verify_worlds_patch


def _model_status(model_dir: Path, games_path: Path) -> dict:
    metadata = model_dir / "metadata.json"
    artifact_path = model_dir / "selected_model.joblib"
    if not metadata.is_file() or not artifact_path.is_file():
        return {"available": False, "reason": "No trained model artifacts; run the real-data training pipeline"}
    if not games_path.is_file():
        return {"available": False, "reason": "Normalized historical games are unavailable"}
    try:
        info = json.loads(metadata.read_text(encoding="utf-8"))
        if not isinstance(info, dict) or info.get("status") != "trained" or not info.get("label_cutoff"):
            return {"available": False, "reason": "Model metadata does not describe a trained, time-bounded model"}
        label_cutoff = datetime.fromisoformat(info["label_cutoff"].replace("Z", "+00:00"))
        if label_cutoff.tzinfo is None or label_cutoff.utcoffset() is None:
            return {"available": False, "reason": "Model label cutoff must include a timezone"}
        with artifact_path.open("rb") as stream:
            artifact_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if artifact_hash != info.get("artifact_sha256"):
            return {"available": False, "reason": "Model artifact SHA256 does not match trusted local metadata"}
        feature_hash = hashlib.sha256(Path(__file__).with_name("features.py").read_bytes()).hexdigest()
        if feature_hash != info.get("feature_code_sha256"):
            return {"available": False, "reason": "Feature code SHA256 does not match the trained model"}
        return {"available": True, "label_cutoff": info["label_cutoff"], "model_version": info.get("model_version", info.get("run_id")), "integrity": "artifact_and_feature_hashes_verified", "note": "Hashes checked against trusted local metadata; inference additionally validates deserialization and request time compatibility"}
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return {"available": False, "reason": f"Invalid model metadata: {type(exc).__name__}"}


def run_prediction(payload: dict, model_dir: Path, games_path: Path) -> dict:
    try:
        from .model import ModelUnavailableError, predict
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Prediction engine is unavailable; no probability was generated") from exc
    try:
        return predict(payload, model_dir=model_dir, games_path=games_path)
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def create_app(
    model_dir: str | Path | None = None,
    games_path: str | Path | None = None,
    worlds_config: str | Path | None = None,
    verification_report: str | Path | None = None,
) -> FastAPI:
    model_path = Path(model_dir or os.getenv("WORLDS_MODEL_DIR", str(PROJECT_ROOT / "models" / "latest")))
    data_path = Path(games_path or os.getenv("WORLDS_GAMES_PATH", str(PROJECT_ROOT / "data" / "processed" / "games.parquet")))
    config_path = Path(worlds_config or os.getenv("WORLDS_CONFIG", str(DEFAULT_CONFIG)))
    report_path = Path(verification_report or os.getenv("WORLDS_VERIFICATION_REPORT", str(PROJECT_ROOT / "reports" / "aggressive" / "worlds_patch_verification.json")))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.worlds_verification = await asyncio.to_thread(verify_worlds_patch, config_path, report_path)
        yield

    app = FastAPI(
        title="Worlds 2026 BP Predictor",
        version="0.3.0",
        description="Real historical professional match models. One map per request, pre-match inputs only.",
        lifespan=lifespan,
    )
    app.state.worlds_verification = {"status": "unverified", "configured_patch": "26.20", "reason": "Application startup has not completed"}

    # Phase-two read-only catalog and analysis routes reuse the frozen models.
    from .catalog_api import create_catalog_router
    from .analysis_api import create_analysis_router
    app.include_router(create_catalog_router(data_path))
    app.include_router(create_analysis_router(model_path, data_path))

    @app.get("/health")
    def health(request: Request) -> dict:
        return {
            "service": "Worlds 2026 BP Predictor",
            "model": _model_status(model_path, data_path),
            "worlds_patch_verification": request.app.state.worlds_verification,
            "series_prediction_supported": False,
        }

    @app.get("/players")
    def players(as_of: datetime, query: str = Query(default="", max_length=160), limit: int = Query(default=50, ge=1, le=200)) -> dict:
        try:
            matches = search_players(data_path.parent / "player_registry.csv", query, as_of, limit)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="Professional player registry is unavailable; import real match data first") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"as_of": as_of.isoformat(), "players": matches, "returned": len(matches), "identity_notice": "Local display-name identities are not immutable provider person IDs; see identity_basis. No future observation counts are returned."}

    @app.post("/predict")
    def predict_map(payload: PredictionRequest, request: Request) -> dict:
        verification = request.app.state.worlds_verification
        is_worlds = payload.scheduled_start.year == 2026 and is_worlds_league(payload.league)
        try:
            enforce_worlds_context(payload, verification)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        readiness = _model_status(model_path, data_path)
        if not readiness["available"]:
            raise HTTPException(status_code=503, detail=readiness["reason"])
        result = run_prediction(payload.model_dump(mode="json"), model_path, data_path)
        result["worlds_patch_verification"] = verification
        warnings = list(result.get("warnings", []))
        if is_worlds and verification.get("status") != "confirmed":
            warnings.append("Worlds patch could not be verified at startup; configured 26.20 is unverified")
        result["warnings"] = warnings
        return result

    return app


app = create_app()
