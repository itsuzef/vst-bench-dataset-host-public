from importlib.metadata import version
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provenance_gate import GateError, dependency_lock_identity, sha256_file  # noqa: E402


HASH = " --hash=sha256:" + "0" * 64


def lockfile(tmp_path, text):
    path = tmp_path / "lock.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_installed_versions_match_continued_hashed_lock(tmp_path):
    path = lockfile(tmp_path, f"# generated lock\npytest=={version('pytest')} \\\n    {HASH.strip()}\n    # via validation\n")
    result = dependency_lock_identity(path, Path(sys.executable), sha256_file(path))
    assert result["items"] == [{"distribution": "pytest", "locked_version": version("pytest"),
                                "version": version("pytest")}]
    assert result["lock_sha256"] == sha256_file(path)


def test_scipy_change_rejected_with_unchanged_lock(tmp_path):
    path = lockfile(tmp_path, "scipy==0.0.0" + HASH)
    checksum = sha256_file(path)
    with pytest.raises(GateError, match=r"scipy: expected 0\.0\.0, installed"):
        dependency_lock_identity(path, Path(sys.executable), checksum)
    assert sha256_file(path) == checksum


def test_missing_distribution_is_rejected(tmp_path):
    path = lockfile(tmp_path, "vst-bench-nonexistent-dependency==1.0" + HASH)
    with pytest.raises(GateError, match="not installed"):
        dependency_lock_identity(path, Path(sys.executable))


def test_inactive_marker_does_not_require_distribution(tmp_path):
    path = lockfile(tmp_path, f"pytest=={version('pytest')}{HASH}\n"
                    "vst-bench-nonexistent-dependency==1.0; python_version < '3.0'" + HASH)
    result = dependency_lock_identity(path, Path(sys.executable))
    assert len(result["items"]) == 1
    assert result["skipped"][0]["distribution"] == "vst-bench-nonexistent-dependency"


def test_changed_lock_rejected_before_interpreter_probe(tmp_path):
    path = lockfile(tmp_path, f"pytest=={version('pytest')}{HASH}")
    with pytest.raises(GateError, match="checksum differs"):
        dependency_lock_identity(path, tmp_path / "missing-python", "0" * 64)


@pytest.mark.parametrize("requirement", [
    "pytest>=8" + HASH,
    "pytest==8.*" + HASH,
    "pytest @ https://example.invalid/pytest.whl" + HASH,
    "pytest[extra]==8.4.1" + HASH,
    "-r another-lock.txt",
    "--index-url https://example.invalid/simple",
    "pytest==8.4.1",
    "pytest==8.4.1 --hash=sha256:bad",
    "",
])
def test_unsupported_or_incomplete_lock_is_rejected(tmp_path, requirement):
    with pytest.raises(GateError):
        dependency_lock_identity(lockfile(tmp_path, requirement), Path(sys.executable))


def test_duplicate_active_distribution_is_rejected(tmp_path):
    path = lockfile(tmp_path, (f"pytest=={version('pytest')}{HASH}\n") * 2)
    with pytest.raises(GateError, match="duplicate active distribution"):
        dependency_lock_identity(path, Path(sys.executable))
