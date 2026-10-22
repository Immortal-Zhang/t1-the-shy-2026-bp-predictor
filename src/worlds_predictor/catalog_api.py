"""Read-only data routes for the BP workbench."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .catalog import catalog_payload, match_list, team_list, team_roster


def create_catalog_router(games_path: Path) -> APIRouter:
    router = APIRouter(tags=["catalog"])

    def guarded(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError as exc:
            raise HTTPException(503, "目录或历史数据尚未准备好，请运行 scripts/update_catalog.py") from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/catalog")
    def catalog(as_of: datetime):
        return guarded(catalog_payload, as_of, games_path)

    @router.get("/teams")
    def teams(as_of: datetime, worlds_only: bool = True, query: str = Query("", max_length=160)):
        return guarded(team_list, as_of, games_path, worlds_only, query)

    @router.get("/teams/{team_id}/roster")
    def roster(team_id: str, as_of: datetime):
        return guarded(team_roster, team_id, as_of, games_path)

    @router.get("/matches")
    def matches(as_of: datetime, worlds_only: bool = True, limit: int = Query(100, ge=1, le=500)):
        return guarded(match_list, as_of, games_path, worlds_only, limit)

    return router
