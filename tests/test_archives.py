from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import provenance_gate as gate  # noqa: E402
from source_archive import (  # noqa: E402
    ArchiveError, MANIFEST, canonical_bytes, digest, make_manifest,
    validate_identity, verify_archive,
)
from validate import PACKAGE_QUARANTINE, package_ruff_paths  # noqa: E402
from export_archives import PACKAGE_FILES, HOST_FILES, zip_snapshot  # noqa: E402


def write_manifest(root, project="vst-bench-ml"):
    manifest = make_manifest(root, project, "a" * 40)
    (root / MANIFEST).write_text(json.dumps(manifest))
    return verify_archive(root, project)


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "source.py").write_text("VALUE = 1\n")
    identity = write_manifest(root)
    return root, identity


def test_exact_archive_identity(snapshot):
    root, identity = snapshot
    assert verify_archive(root, "vst-bench-ml", identity) == identity
    assert identity["manifest_sha256"] == digest((root / MANIFEST).read_bytes())


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra", "symlink", "cache"])
def test_file_mutations_fail_closed(snapshot, mutation):
    root, identity = snapshot
    if mutation == "changed":
        (root / "source.py").write_text("VALUE = 2\n")
    elif mutation == "missing":
        (root / "source.py").unlink()
    elif mutation == "extra":
        (root / "extra.py").write_text("pass\n")
    elif mutation == "cache":
        (root / "__pycache__").mkdir()
        (root / "__pycache__/source.pyc").write_bytes(b"not trusted")
    else:
        (root / "alias.py").symlink_to(root / "source.py")
    with pytest.raises(ArchiveError):
        verify_archive(root, "vst-bench-ml", identity)


def test_resealed_substitution_rejected_by_pin(snapshot):
    root, original = snapshot
    (root / "source.py").write_text("VALUE = 999\n")
    write_manifest(root)
    with pytest.raises(ArchiveError, match="locked expectation"):
        verify_archive(root, "vst-bench-ml", original)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "a/../b", "a//b", ".git/config"])
def test_unsafe_paths_rejected(snapshot, name):
    root, _ = snapshot
    manifest = json.loads((root / MANIFEST).read_text())
    manifest["files"][0]["path"] = name
    manifest["files_sha256"] = digest(canonical_bytes(manifest["files"]))
    (root / MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ArchiveError, match="unsafe source path"):
        verify_archive(root, "vst-bench-ml")


def test_duplicate_paths_rejected(snapshot):
    root, _ = snapshot
    manifest = json.loads((root / MANIFEST).read_text())
    manifest["files"] *= 2
    (root / MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ArchiveError, match="unique and sorted"):
        verify_archive(root, "vst-bench-ml")


def test_duplicate_json_keys_rejected(snapshot):
    root, _ = snapshot
    (root / MANIFEST).write_text('{"schema": "a", "schema": "b"}')
    with pytest.raises(ArchiveError, match="malformed"):
        verify_archive(root, "vst-bench-ml")


def test_manifest_symlink_rejected(snapshot):
    root, _ = snapshot
    target = root.parent / "external.json"
    (root / MANIFEST).rename(target)
    (root / MANIFEST).symlink_to(target)
    with pytest.raises(ArchiveError, match="manifest symlink"):
        verify_archive(root, "vst-bench-ml")


def test_git_and_archive_ambiguity_rejected(snapshot):
    root, _ = snapshot
    (root / ".git").mkdir()
    with pytest.raises(ArchiveError, match="without .git"):
        verify_archive(root, "vst-bench-ml")


def test_wrong_project_rejected(snapshot):
    with pytest.raises(ArchiveError, match="project or schema"):
        verify_archive(snapshot[0], "vst-bench-dataset-host")


def test_missing_source_pin_rejected_before_wheel(snapshot):
    root, _ = snapshot
    with pytest.raises(gate.GateError, match="no locked expectation"):
        gate.package_identity(root, root / "x.whl", root / "lock", Path(sys.executable), {}, {})


def test_archive_failure_does_not_fall_back_to_git(snapshot, monkeypatch):
    root, identity = snapshot
    (root / "source.py").write_text("modified")
    monkeypatch.setattr(gate, "_git", lambda *a, **k: pytest.fail("Git fallback"))
    with pytest.raises(gate.GateError, match="files differ"):
        gate.package_identity(root, root / "x.whl", root / "lock", Path(sys.executable), {},
                              {"source_archive": identity})


def test_dirty_git_rejection_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_git", lambda *a, **k: "1 .M changed.py")
    with pytest.raises(gate.GateError, match="repository is dirty"):
        gate.package_identity(tmp_path, tmp_path / "x.whl", tmp_path / "lock",
                              Path(sys.executable), {}, {})


def test_archive_requires_real_wheel(snapshot):
    root, identity = snapshot
    with pytest.raises(gate.GateError, match="not a valid wheel archive"):
        gate.package_identity(root, root / "x.whl", root / "lock", Path(sys.executable), {},
                              {"source_archive": identity})


def test_source_pin_cannot_be_removed_to_enter_git(snapshot):
    root, identity = snapshot
    (root / MANIFEST).unlink()
    with pytest.raises(gate.GateError, match="locked source archive is missing"):
        gate.package_identity(root, root / "x.whl", root / "lock", Path(sys.executable), {},
                              {"source_archive": identity})


def test_archive_lint_allowlist_and_quarantine(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/allowed.py").write_text("pass\n")
    write_manifest(tmp_path)
    assert package_ruff_paths(tmp_path) == ["scripts/allowed.py"]
    (tmp_path / "scripts/smoke_generate.py").write_text("pass\n")
    write_manifest(tmp_path)
    with pytest.raises(SystemExit, match="quarantined"):
        package_ruff_paths(tmp_path)


def test_public_allowlists_exclude_private_files():
    assert not PACKAGE_FILES & PACKAGE_QUARANTINE
    assert not {"docs/CONTRACT.md", "docs/RIGHTS.md", "docs/LICENSE-DECISION.md"} & HOST_FILES
    assert not any(name.startswith((".git/", ".github/")) for name in PACKAGE_FILES | HOST_FILES)


def test_zip_is_repeatable_and_has_no_history(snapshot, tmp_path):
    root, _ = snapshot
    first = zip_snapshot(root)
    (root.parent / first["path"]).rename(tmp_path / "first.zip")
    assert zip_snapshot(root) == first


def test_host_archive_constructor_without_git(snapshot, tmp_path, monkeypatch):
    root, _ = snapshot
    identity = write_manifest(root, "vst-bench-dataset-host")
    server_path = Path(__file__).resolve().parents[1] / "host/server.py"
    spec = importlib.util.spec_from_file_location("archive_test_server", server_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.FixtureHost, "_git", lambda *a: pytest.fail("Git required"))
    runner = tmp_path / "runner"
    runner.write_bytes(b"stub; never executed")
    host = module.FixtureHost(runner, root)
    assert host.source_commit == "archive-sha256:" + identity["files_sha256"]
    assert host.source_dirty is False
    assert host.source_archive == identity


@pytest.mark.parametrize("key", ["manifest_sha256", "files_sha256", "upstream_commit"])
def test_incomplete_recorded_identity_rejected(snapshot, key):
    identity = dict(snapshot[1])
    identity[key] = "not a digest"
    with pytest.raises(ArchiveError):
        validate_identity(identity, "vst-bench-ml")
