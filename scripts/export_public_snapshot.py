"""Export only tracked project files; normalize private paths in browser reports.

The original checkout/history stays intact. Run after staging intended files.
No credentials, data binaries, parent-workspace files or Git history are copied.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PATH = re.compile(r"/(?:Users|home)/[^/\s\"\)]+/")
PRIVATE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:163\.com|qq\.com|gmail\.com)")
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,}|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def export(destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination must be a new directory; existing files are never overwritten")
    paths = subprocess.check_output(["git", "ls-files", "-z", "--", "."], cwd=ROOT).decode().split("\0")
    destination.mkdir(parents=True)
    transformations = []
    for name in filter(None, paths):
        if name in {"PUBLICATION.md", "PUBLICATION_MANIFEST.json"}:
            continue  # Regenerate export metadata; never hash a previous manifest into itself.
        source = ROOT / name
        if source.is_symlink() or not source.is_file() or ".." in Path(name).parts:
            raise ValueError(f"Unsupported tracked path: {name}")
        data = source.read_bytes()
        if len(data) > 50 * 1024 * 1024:
            raise ValueError(f"Unexpected large tracked file: {name}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            clean = text.replace(str(ROOT), ".")
            if PRIVATE_PATH.search(clean) or PRIVATE_EMAIL.search(clean) or SECRET.search(clean):
                raise ValueError(f"Potential private content requires review: {name}")
            encoded = clean.encode("utf-8")
            if encoded != data:
                transformations.append({"file": name, "change": "Replaced absolute workstation project paths with a project-relative dot",
                                        "original_sha256": digest(data), "published_sha256": digest(encoded)})
                data = encoded
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        shutil.copymode(source, target)
    note = """# Public source snapshot

This repository publishes the project's source, multilingual README, cached
reference catalogs, recorded evaluation reports and application screenshots.
It does not include raw/processed match data, trained model binaries, local
dependencies, private workspace files or the local development Git history.
Follow the README's first-clone data/training steps before predicting.

Absolute workstation paths in three browser JSON reports were normalized to
project-relative paths. Their test results were not changed. Original local
audit/delivery manifests describe the recorded historical run and may refer to
local artifacts not distributed here or the reports' pre-normalization bytes.
They are not manifests of this public source export. PUBLICATION_MANIFEST.json
records the exported file hashes and the exact source/export hashes of changed
reports. It is a reproducibility record, not a cryptographic signature.

The initial public commit uses the account's GitHub noreply address. Existing
local commits and their authorship were not rewritten or uploaded. No software
license is implied by public visibility; data and Riot materials retain their
separate terms as described in the README.
"""
    (destination / "PUBLICATION.md").write_text(note)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "type": "public_source_snapshot",
                "path_normalizations": transformations,
                "files": {str(p.relative_to(destination)): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                          for p in sorted(destination.rglob("*")) if p.is_file()}}
    (destination / "PUBLICATION_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "normalized_reports": len(transformations),
                      "bytes": sum(item["bytes"] for item in manifest["files"].values())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    export(parser.parse_args().destination)
