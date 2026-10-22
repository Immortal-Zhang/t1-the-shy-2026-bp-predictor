"""FastAPI presentation endpoint over the unchanged phase-one real models."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .analysis import AnalysisRequest, analyze
from .context import enforce_worlds_context, is_worlds_league
from .model import ModelUnavailableError


def create_analysis_router(model_dir: Path, games_path: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/analyze")
    def analyze_map(payload: AnalysisRequest, request: Request) -> dict:
        verification = getattr(request.app.state, "worlds_verification", {"status": "unverified", "configured_patch": "26.20"})
        try:
            enforce_worlds_context(payload, verification)
            result = analyze(payload.model_dump(mode="json"), model_dir, games_path)
        except ModelUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result["prediction"]["worlds_patch_verification"] = verification
        if payload.scheduled_start.year == 2026 and is_worlds_league(payload.league) and verification.get("status") != "confirmed":
            result["prediction"]["warnings"].append("Worlds 官方版本本次启动未核验，配置版本仅供参考。")
        return result

    return router
