"""Archive safety/integrity tests use tiny non-model bytes, never prediction data."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("download_runtime", ROOT / "scripts/download_runtime.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "checkout"; root.mkdir()
    (root / "configs").mkdir()
    (root / "source.py").write_text("# Structural test source only\n")
    content = b"structural archive test, not a model"
    files = {"models/unit-fixture.bin": {"sha256": sha(content), "bytes": len(content)}}
    manifest = {"files": files, "compatible_source_sha256": {"source.py": module.digest(root / "source.py")}}
    manifest_bytes = json.dumps(manifest).encode()
    path = tmp_path / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, data in {"models/unit-fixture.bin": content, "runtime-manifest.json": manifest_bytes}.items():
            info = tarfile.TarInfo(name); info.size = len(data); archive.addfile(info, io.BytesIO(data))
    config = {"schema_version": 1, **manifest, "manifest_sha256": sha(manifest_bytes),
              "archive_sha256": module.digest(path), "archive_bytes": path.stat().st_size}
    (root / "configs/runtime_bundle.json").write_text(json.dumps(config))
    return root, path, config, content


def test_install_verified_archive_and_repeat(bundle):
    root, archive, config, content = bundle
    assert module.check(root, config) == ["models/unit-fixture.bin"]
    assert module.read_config(root) == config
    assert module.install(root, config, archive) is None
    assert (root / "models/unit-fixture.bin").read_bytes() == content
    assert module.check(root, config) == []
    assert module.install(root, config, archive) is None


def test_corruption_before_any_install(bundle):
    root, archive, config, _ = bundle
    archive.write_bytes(archive.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="SHA-256/size"):
        module.install(root, config, archive)
    assert not (root / "models").exists()


def test_preserve_custom_models_unless_explicit_backup(bundle):
    root, archive, config, content = bundle
    (root / "models").mkdir()
    target = root / "models/unit-fixture.bin"; target.write_bytes(b"my original local model")
    with pytest.raises(ValueError, match="preserved"):
        module.install(root, config, archive)
    assert target.read_bytes() == b"my original local model"
    backup = module.install(root, config, archive, replace=True)
    assert (backup / "models/unit-fixture.bin").read_bytes() == b"my original local model"
    assert target.read_bytes() == content


def test_changed_source_refuses_runtime(bundle):
    root, _, _, _ = bundle
    (root / "source.py").write_text("changed")
    with pytest.raises(ValueError, match="version mismatch"):
        module.read_config(root)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../b", "a\\b", "a/./b", "a//b", ""])
def test_unsafe_paths_rejected(name):
    with pytest.raises(ValueError, match="Unsafe"):
        module.safe_name(name)


def test_existing_symlink_not_followed(bundle, tmp_path):
    root, archive, config, _ = bundle
    outside = tmp_path / "outside"; outside.mkdir()
    (root / "models").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes|symlink"):
        module.install(root, config, archive)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "duplicate", "traversal", "unlisted"])
def test_malicious_tar_rejected_even_with_matching_archive_hash(bundle, kind):
    root, archive, config, content = bundle
    manifest = {"files": config["files"], "compatible_source_sha256": config["compatible_source_sha256"]}
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("models/unit-fixture.bin"); info.size = len(content)
        if kind == "symlink":
            info.type = tarfile.SYMTYPE; info.linkname = "/tmp/unsafe"; info.size = 0
        tar.addfile(info, None if kind == "symlink" else io.BytesIO(content))
        data = json.dumps(manifest).encode(); info = tarfile.TarInfo("runtime-manifest.json"); info.size = len(data); tar.addfile(info, io.BytesIO(data))
        if kind != "symlink":
            name = "models/unit-fixture.bin" if kind == "duplicate" else "../outside" if kind == "traversal" else "unexpected.bin"
            info = tarfile.TarInfo(name); info.size = len(content); tar.addfile(info, io.BytesIO(content))
    config.update(archive_sha256=module.digest(archive), archive_bytes=archive.stat().st_size)
    with pytest.raises(ValueError, match="regular|unexpected|duplicate|Unsafe"):
        module.install(root, config, archive)
    assert not (root / "models").exists()


def test_downloader_rejects_unpinned_host(tmp_path):
    with pytest.raises(ValueError, match="pinned"):
        module.download("https://other.example/bundle", tmp_path / "download", 1)


def test_real_bundle_matches_deployed_artifacts():
    config_path = ROOT / "configs/runtime_bundle.json"
    if not config_path.exists():
        pytest.skip("Runtime release config not present")
    config = module.read_config(ROOT)
    missing = module.check(ROOT, config)
    if missing:
        pytest.skip("Run ./start.sh --setup-only to install the real runtime")
    assert config["real_games"] == 28738
    assert config["standard_model"].endswith("C_catboost_uniform")
