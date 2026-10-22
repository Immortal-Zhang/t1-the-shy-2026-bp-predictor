"""Install checksum-pinned pretrained models/history without importing joblib."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name or not path.parts:
        raise ValueError(f"Unsafe bundle path: {name}")
    return path


def safe_target(root, name):
    target = root / safe_name(name)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Bundle destination escapes project: {name}")
    for item in [target, *target.parents]:
        if item == root.parent:
            break
        if item.is_symlink():
            raise ValueError(f"Bundle destination is a symlink: {name}")
    return target


def read_config(root):
    config = json.loads((root / "configs/runtime_bundle.json").read_text())
    if config["schema_version"] != 1 or not config["files"]:
        raise ValueError("Unsupported runtime bundle configuration")
    for name in config["files"]:
        safe_target(root, name)
    for name, expected in config["compatible_source_sha256"].items():
        target = safe_target(root, name)
        if not target.is_file() or digest(target) != expected:
            raise ValueError(f"Runtime/source version mismatch: {name}; use the matching release checkout")
    return config


def check(root, config):
    return [name for name, meta in config["files"].items()
            if not safe_target(root, name).is_file() or digest(root / name) != meta["sha256"]]


def download(url, destination, expected_bytes):
    if not url.startswith("https://github.com/Immortal-Zhang/"):
        raise ValueError("Runtime downloads must use the pinned project GitHub release")
    if shutil.which("curl"):
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--connect-timeout", "20",
                        "--max-time", "600", "--proto", "=https", "--output", str(destination), url], check=True)
    else:
        with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > expected_bytes:
                    raise ValueError("Downloaded archive exceeds pinned size")
                output.write(block)
    if destination.stat().st_size != expected_bytes:
        raise ValueError("Downloaded archive size does not match release")


def install(root, config, archive_path, replace=False):
    if archive_path.stat().st_size != config["archive_bytes"] or digest(archive_path) != config["archive_sha256"]:
        raise ValueError("Archive SHA-256/size mismatch; nothing installed")
    expected = config["files"]
    runtime_dir = root / ".runtime"; runtime_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bundle-stage-", dir=runtime_dir) as temp:
        stage = Path(temp)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or set(names) != set(expected) | {"runtime-manifest.json"}:
                raise ValueError("Archive contains unexpected, missing or duplicate members")
            for member in members:
                safe_name(member.name)
                if not member.isfile() or member.issym() or member.islnk():
                    raise ValueError("Only regular files are permitted in the runtime archive")
                if member.size > 100 * 1024 * 1024 or member.size < 0:
                    raise ValueError("Unexpected runtime member size")
                if member.name in expected and member.size != expected[member.name]["bytes"]:
                    raise ValueError("Runtime member size mismatch")
                target = stage / member.name; target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Missing archive member stream")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            if digest(stage / "runtime-manifest.json") != config["manifest_sha256"]:
                raise ValueError("Internal manifest hash mismatch")
            manifest = json.loads((stage / "runtime-manifest.json").read_text())
            if manifest["files"] != expected or manifest["compatible_source_sha256"] != config["compatible_source_sha256"]:
                raise ValueError("Internal manifest does not match source configuration")
            for name, meta in expected.items():
                if digest(stage / name) != meta["sha256"]:
                    raise ValueError(f"Runtime member hash mismatch: {name}")
        # Validate every conflict BEFORE mutating any model/data file.
        conflicts = [name for name in expected if safe_target(root, name).exists() and digest(root / name) != expected[name]["sha256"]]
        if conflicts and not replace:
            raise ValueError("Different local artifacts preserved: " + ", ".join(conflicts) + "; use --replace explicitly to back up and replace")
        backup = Path(tempfile.mkdtemp(prefix="runtime-backup-", dir=runtime_dir)) if conflicts else None
        for name in expected:
            target = safe_target(root, name)
            if target.is_file() and digest(target) == expected[name]["sha256"]:
                continue
            if name in conflicts:
                saved = backup / name; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / name, target)
    remaining = check(root, config)
    if remaining:
        raise ValueError("Runtime post-install verification failed: " + ", ".join(remaining))
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    config = read_config(root)
    missing = check(root, config)
    if not missing:
        print("Pretrained runtime ready: all model/data hashes verified. No training required.")
        return
    if args.check_only:
        raise ValueError("Runtime missing or changed: " + ", ".join(missing))
    archive = args.archive.resolve() if args.archive else None
    if archive is None:
        cache = root / ".runtime/downloads"; cache.mkdir(parents=True, exist_ok=True)
        archive = cache / config["asset_name"]
        if not archive.exists() or digest(archive) != config["archive_sha256"]:
            partial = archive.with_suffix(archive.suffix + ".part")
            print(f"Downloading pretrained runtime ({config['archive_bytes'] / 1024**2:.1f} MiB)...", flush=True)
            try:
                download(config["url"], partial, config["archive_bytes"])
                if digest(partial) != config["archive_sha256"]:
                    raise ValueError("Downloaded runtime SHA-256 mismatch")
                os.replace(partial, archive)
            finally:
                partial.unlink(missing_ok=True)
    backup = install(root, config, archive, args.replace)
    print("Installed and verified real pretrained models + match history. Training was not run.")
    if backup:
        print("Previous local artifacts backed up to " + str(backup))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f"Runtime setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
