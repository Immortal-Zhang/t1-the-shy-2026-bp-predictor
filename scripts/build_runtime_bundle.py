"""Build a deterministic, version-pinned bundle from real existing artifacts."""
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TAG = "runtime-2026-10-22-v1"
ASSET = "t1-the-shy-2026-runtime-v1.tar.gz"
REPO = "Immortal-Zhang/t1-the-shy-2026-bp-predictor"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build():
    standard = json.loads((ROOT / "models/latest/metadata.json").read_text())
    enhanced = json.loads((ROOT / "models/aggressive-experiment/latest/metadata.json").read_text())
    run = standard["run_id"]
    names = ["models/latest/metadata.json", "models/latest/selected_model.joblib",
             f"models/{run}/evaluation.json", f"models/{run}/B_catboost.joblib",
             "models/aggressive-experiment/latest/metadata.json", "models/aggressive-experiment/latest/selected_model.joblib",
             "data/processed/games.parquet", "data/processed/player_registry.csv",
             "data/processed/player_team_stints.csv", "data/processed/quality_report.json"]
    files = {name: (ROOT / name).read_bytes() for name in names}
    assert sha(files["models/latest/selected_model.joblib"]) == standard["artifact_sha256"]
    assert sha(files["models/aggressive-experiment/latest/selected_model.joblib"]) == enhanced["artifact_sha256"]
    files["data/runtime/sources.json"] = (ROOT / "data/raw/sources.json").read_bytes()
    files["data/runtime/NOTICE.md"] = ("# Runtime data attribution\n\n"
        "ChainCC. League of Legends esports match dataset. https://chaincc.lol/free/data/ (accessed 2026-10-22).\n\n"
        "Match data: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/ . Redistribution retains attribution and this license link.\n"
        "Changes: normalized to one row per game, invalid games quarantined, local professional name identifiers and observed team stints derived.\n"
        "Underlying Riot rights remain applicable. This project is not endorsed by ChainCC, Riot Games, T1 or TheShy.\n"
        "The models are the actual previously trained standard C, pre-BP B and enhanced CatBoost artifacts, not demonstration predictions.\n"
        "Only load the trusted, checksum-pinned release: joblib deserialization executes Python objects.\n").encode()
    for name, data in files.items():
        if name.endswith((".json", ".md", ".csv")):
            text = data.decode()
            if re.search(r"/(Users|home)/|[\w.+-]+@(163\.com|qq\.com|gmail\.com)", text):
                raise ValueError(f"Private content found in {name}")
    compatibility = ["src/worlds_predictor/features.py", "src/worlds_predictor/enhanced_features.py",
                     "src/worlds_predictor/judgment_policy.py", "requirements.lock.txt",
                     "reports/aggressive/judgment_policy.json", "reports/aggressive/judgment_manifest.json",
                     "reports/aggressive/judgment_evaluation.json", "data/catalog/champion-en_US.json",
                     "data/catalog/champion-zh_CN.json", "data/catalog/worlds_rules.json",
                     "configs/worlds2026_participants.json"]
    manifest = {"schema_version": 1, "release_tag": TAG,
                "standard_model": standard["model_version"], "judgment_model": enhanced["model_version"],
                "data_cutoff": standard["evaluation_data_cutoff"], "real_games": 28738,
                "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(files.items())},
                "compatible_source_sha256": {name: sha((ROOT / name).read_bytes()) for name in compatibility}}
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    files["runtime-manifest.json"] = manifest_data
    directory = ROOT / ".runtime/releases"; directory.mkdir(parents=True, exist_ok=True)
    path = directory / ASSET
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, data in sorted(files.items()):
                item = tarfile.TarInfo(name); item.size = len(data); item.mode = 0o644; item.mtime = 0
                archive.addfile(item, io.BytesIO(data))
    archive_sha = sha(path.read_bytes())
    config = {**manifest, "repository": REPO, "asset_name": ASSET,
              "url": f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}",
              "archive_sha256": archive_sha, "archive_bytes": path.stat().st_size,
              "manifest_sha256": sha(manifest_data)}
    (ROOT / "configs/runtime_bundle.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    (directory / "SHA256SUMS").write_text(f"{archive_sha}  {ASSET}\n")
    (directory / "runtime-manifest.json").write_bytes(manifest_data)
    print(json.dumps({"archive": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                      "sha256": archive_sha, "files": len(manifest["files"])}))


if __name__ == "__main__":
    build()
