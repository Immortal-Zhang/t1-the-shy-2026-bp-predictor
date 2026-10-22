#!/usr/bin/env python3
"""Train genuine challenger models without replacing the standard artifact."""
import argparse
import json
from pathlib import Path

from worlds_predictor.enhanced_training import train_enhanced

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", type=Path, default=Path("configs/aggressive_experiment.json"))
parser.add_argument("--games", type=Path, default=Path("data/processed/games.parquet"))
parser.add_argument("--models-dir", type=Path, default=Path("models/aggressive-experiment"))
parser.add_argument("--reports-dir", type=Path, default=Path("reports/aggressive"))
args = parser.parse_args()
train_enhanced(json.loads(args.config.read_text()), args.games, args.models_dir, args.reports_dir)
