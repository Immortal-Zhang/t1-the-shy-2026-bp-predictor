"""Reproducible command-line entry points. Run from the project root."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="worlds-bp", description="Real-data, point-in-time professional LoL predictions")
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Download real ChainCC data with provenance")
    download.add_argument("--years", nargs="+", type=int, default=[2024, 2025, 2026])
    download.add_argument("--raw-dir", default="data/raw")
    manual = sub.add_parser("import-csv", help="Import a local ChainCC or Oracle's Elixir CSV")
    manual.add_argument("path")
    manual.add_argument("--source-url", required=True)
    manual.add_argument("--license", required=True, dest="license_text")
    manual.add_argument("--raw-dir", default="data/raw")
    normalize = sub.add_parser("normalize")
    normalize.add_argument("--raw-dir", default="data/raw")
    normalize.add_argument("--output-dir", default="data/processed")
    normalize.add_argument("--as-of", required=True)
    normalize.add_argument("--aliases")
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--games", default="data/processed/games.parquet")
    train_parser.add_argument("--config", default="configs/train.json")
    train_parser.add_argument("--as-of", help="Override cutoff; split boundaries must still precede it")
    train_parser.add_argument("--models-dir", default="models")
    train_parser.add_argument("--reports-dir", default="reports")
    pred = sub.add_parser("predict")
    pred.add_argument("request", help="JSON request using the same contract as POST /predict")
    pred.add_argument("--models-dir", default="models/latest")
    pred.add_argument("--games", default="data/processed/games.parquet")
    pred.add_argument("--output")
    sub.add_parser("verify-worlds")
    players = sub.add_parser("players", help="Resolve observed pro player IDs and aliases before as_of")
    players.add_argument("--query", required=True)
    players.add_argument("--as-of", required=True)
    players.add_argument("--games", default="data/processed/games.parquet")
    demo = sub.add_parser("make-replay", help="Create a request from an actual held-out historical game, not fabricated data")
    demo.add_argument("--games", default="data/processed/games.parquet")
    demo.add_argument("--game-id")
    demo.add_argument("--as-of", default="2026-10-22T00:00:00Z")
    demo.add_argument("--output", default="examples/real_match_replay.json")
    args = parser.parse_args(argv)
    if args.command == "download":
        from .data import download_data
        emit(download_data(args.raw_dir, years=tuple(args.years)))
    elif args.command == "import-csv":
        from .data import import_manual_csv
        emit(import_manual_csv(args.path, args.raw_dir, args.source_url, args.license_text))
    elif args.command == "normalize":
        from .data import normalize_data
        emit(normalize_data(args.raw_dir, args.output_dir, as_of=args.as_of, alias_path=args.aliases))
    elif args.command == "train":
        from .model import train
        config = json.loads(Path(args.config).read_text())
        if args.as_of:
            config["as_of"] = args.as_of
        result = train(args.games, config, args.models_dir, args.reports_dir)
        emit({"run_id": result["run_id"], "status": result["status"], "selected_model": result["selected_model"]})
    elif args.command == "predict":
        from .model import predict, dump_json
        from .schemas import PredictionRequest
        from .worlds import verify_worlds_patch, DEFAULT_CONFIG, PROJECT_ROOT
        from .context import enforce_worlds_context
        payload = PredictionRequest.model_validate_json(Path(args.request).read_text()).model_dump(mode="json")
        verification = verify_worlds_patch(DEFAULT_CONFIG, PROJECT_ROOT / "reports" / "worlds_patch_verification.json")
        try:
            enforce_worlds_context(payload, verification)
        except (ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        result = predict(payload, model_dir=Path(args.models_dir), games_path=Path(args.games))
        result["worlds_patch_verification"] = verification
        if verification["status"] != "confirmed":
            result["warnings"].append("Official Worlds patch could not be verified during this invocation")
        if args.output:
            dump_json(args.output, result)
        emit(result)
    elif args.command == "verify-worlds":
        from .worlds import verify_worlds_patch, DEFAULT_CONFIG, PROJECT_ROOT
        emit(verify_worlds_patch(DEFAULT_CONFIG, PROJECT_ROOT / "reports" / "worlds_patch_verification.json"))
    elif args.command == "players":
        from .lookup import search_players
        emit(search_players(Path(args.games).parent / "player_registry.csv", args.query, args.as_of))
    elif args.command == "make-replay":
        from .data import load_games
        from .model import dump_json
        from .context import is_worlds_league, public_patch
        games = load_games(args.games, as_of=args.as_of)
        if args.game_id:
            candidates = games.loc[games.game_id == args.game_id]
        else:
            candidates = games.loc[games.league.map(is_worlds_league) & (games.date.dt.year == 2026)]
            if candidates.empty:
                candidates = games.loc[games.date.dt.year == 2026]
        if candidates.empty:
            parser.error("No real eligible game found")
        row = candidates.sort_values(["date", "game_id"]).iloc[-1]
        payload = {"game_id": row.game_id, "as_of": row.date.isoformat(), "scheduled_start": row.date.isoformat(),
                   "league": "Worlds" if is_worlds_league(row.league) else row.league,
                   "patch": public_patch(row.patch), "first_pick_side": row.first_pick_side}
        for side in ("blue", "red"):
            payload[side] = {"team_id": row[f"{side}_team_id"],
                             "players": [{"role": role, "player_id": row[f"{side}_{role}_player_id"], "champion": row[f"{side}_{role}_champion"]} for role in ("top", "jng", "mid", "bot", "sup")],
                             "bans": [None if row[f"{side}_ban{i}"] in ("unknown", "__UNKNOWN__", "") else row[f"{side}_ban{i}"] for i in range(1, 6)]}
        dump_json(args.output, payload)
        dump_json(str(Path(args.output).with_suffix(".provenance.json")), {"type": "historical_real_match_replay", "game_id": row.game_id, "source_league": row.league, "source_patch": row.patch, "actual_blue_win": int(row.blue_win), "note": "Actual outcome stored only in provenance, never sent to predictor. This is a retrospective replay, not a forecast of an unplayed match. Public/source version aliases are explicit."})
        emit({"request": args.output, "game_id": row.game_id, "type": "historical_real_match_replay"})


if __name__ == "__main__":
    main()
