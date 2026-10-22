"""One command: dependencies, verified pretrained data, production app. No training."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    print("+ " + " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=ROOT, check=True, **kwargs)


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def node_ready():
    if not shutil.which("node") or not shutil.which("npm"):
        raise ValueError("Install Node.js 20.19+ or 22.12+ and npm before running ./start.sh")
    version = subprocess.check_output(["node", "-p", "process.versions.node"], text=True).strip()
    major, minor, *_ = map(int, version.split("."))
    if not (major == 20 and minor >= 19 or major == 22 and minor >= 12 or major > 22):
        raise ValueError(f"Unsupported Node.js {version}; install Node.js 20.19+ or 22.12+")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--archive", type=Path, help="Install a previously downloaded release archive")
    args = parser.parse_args()
    node_ready()
    for key, default in (("WORLDS_API_PORT", "8026"), ("WORLDS_WEB_PORT", "5173")):
        value = int(os.environ.get(key, default))
        if not 1024 <= value <= 65535:
            raise ValueError(f"{key} must be between 1024 and 65535")
    runtime = ROOT / ".runtime"; runtime.mkdir(exist_ok=True)
    python = ROOT / ".venv/bin/python"
    if not python.is_file():
        print("Creating isolated Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    requirements = fingerprint([ROOT / "requirements.lock.txt", ROOT / "pyproject.toml"])
    stamp = runtime / "python-setup.json"
    ready = stamp.exists() and json.loads(stamp.read_text()).get("requirements") == requirements
    if ready:
        probe = subprocess.run([str(python), "-c", "import worlds_predictor,catboost,pandas,duckdb,sklearn,fastapi,uvicorn"], cwd=ROOT, capture_output=True)
        ready = probe.returncode == 0
    if not ready:
        run([python, "-m", "pip", "install", "-r", "requirements.lock.txt"])
        run([python, "-m", "pip", "install", "--no-deps", "-e", ".[dev]"])
        run([python, "-m", "pip", "check"])
        stamp.write_text(json.dumps({"requirements": requirements, "python": sys.version}))
    command = [python, "scripts/download_runtime.py"]
    if args.archive:
        command.extend(["--archive", args.archive.resolve()])
    run(command)
    package_stamp = runtime / "frontend-setup.sha256"
    package_hash = fingerprint([ROOT / "frontend/package-lock.json", ROOT / "frontend/package.json"])
    if not (ROOT / "frontend/node_modules/.bin/vite").exists() or not package_stamp.exists() or package_stamp.read_text() != package_hash:
        run(["npm", "--prefix", "frontend", "ci"])
        package_stamp.write_text(package_hash)
    source_hash = fingerprint([p for p in (ROOT / "frontend/src").rglob("*") if p.is_file()] +
                              [ROOT / "frontend/index.html", ROOT / "frontend/vite.config.ts", ROOT / "frontend/package-lock.json"])
    build_stamp = runtime / "frontend-build.sha256"
    if not (ROOT / "frontend/dist/index.html").exists() or not build_stamp.exists() or build_stamp.read_text() != source_hash:
        run(["npm", "--prefix", "frontend", "run", "build"])
        build_stamp.write_text(source_hash)
    print("Ready: verified pretrained models, real history and production frontend. No retraining.", flush=True)
    if not args.setup_only:
        os.execv("/bin/bash", ["bash", str(ROOT / "scripts/start_local.sh"), "--built"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        sys.exit(1)
