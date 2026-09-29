#!/usr/bin/env python3
"""Prepare allowlisted local snapshots; never publish or include Git history."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
from source_archive import MANIFEST, digest, make_manifest, verify_archive  # noqa: E402

PACKAGE_FILES = {
    "CITATION.cff", "LICENSE", "NOTICE", "README.md", "docs/DESIGN.md",
    "CHANGELOG.md", "CONTRIBUTING.md", "docs/HISTORY.md", "docs/README.md",
    "docs/INSTALL.md", "docs/USAGE.md", "docs/TROUBLESHOOTING.md",
    "docs/RELEASE.md", "pyproject.toml", "requirements/lock.txt",
    "scripts/introspect_plugin.py", "scripts/profile_render.py",
    "src/vst_bench_ml/__init__.py", "src/vst_bench_ml/batch.py",
    "src/vst_bench_ml/cli.py", "src/vst_bench_ml/client.py",
    "src/vst_bench_ml/export.py", "src/vst_bench_ml/introspect.py",
    "src/vst_bench_ml/midi_signals.py", "src/vst_bench_ml/provenance.py",
    "src/vst_bench_ml/quality.py", "src/vst_bench_ml/renderer.py",
    "src/vst_bench_ml/sampling.py", "src/vst_bench_ml/seeding.py",
    "tests/__init__.py", "tests/fixtures/parameter-manifest.json",
    "tests/test_batch.py", "tests/test_cli.py", "tests/test_client.py",
    "tests/test_export.py", "tests/test_install.py", "tests/test_introspect.py",
    "tests/test_provenance.py", "tests/test_quality.py", "tests/test_sampling.py",
    "tests/test_seeding.py",
}
HOST_FILES = {
    "CITATION.cff", "CMakeLists.txt", "LICENSE", "OUTPUT-LICENSE", "THIRD_PARTY.md",
    "docs/PROTOCOL.md", "docs/ARCHIVES.md", "docs/ARCHIVE-README.md",
    "CHANGELOG.md", "CONTRIBUTING.md", "docs/HISTORY.md", "docs/QUICKSTART.md",
    "docs/VALIDATION.md", "docs/RELEASE.md",
    "fixture/controller.cpp", "fixture/controller.h", "fixture/factory.cpp",
    "fixture/ids.h", "fixture/processor.cpp", "fixture/processor.h",
    "fixtures/expected-output.json", "fixtures/midi-bank.json",
    "fixtures/parameter-manifest.json", "host/runner.cpp", "host/server.py",
    "scripts/build.sh", "scripts/provenance_gate.py", "scripts/validate.py",
    "scripts/source_archive.py", "scripts/export_archives.py",
    "tests/test_server.py", "tests/test_archives.py",
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def copy_allowed(source: Path, target: Path, names: set[str]) -> None:
    target.mkdir()
    for name in sorted(names):
        path = source / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise ValueError(f"missing or unsafe allowlisted path: {name}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        destination.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def seal(root: Path, project: str, commit: str) -> dict:
    write_json(root / MANIFEST, make_manifest(root, project, commit))
    return verify_archive(root, project)


def zip_snapshot(root: Path) -> dict:
    path = root.parent / (root.name + ".zip")
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(root.rglob("*")):
            if source.is_file():
                info = zipfile.ZipInfo(root.name + "/" + source.relative_to(root).as_posix(),
                                       date_time=(2026, 9, 23, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100755 if source.stat().st_mode & 0o111 else 0o100644) << 16
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    return {"path": path.name, "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes())}


def export(package: Path, host: Path, output: Path, allow_dirty_host: bool = False) -> dict:
    package, host, output = package.resolve(), host.resolve(), output.resolve()
    if output.exists() or any(output.is_relative_to(root) for root in (package, host)):
        raise ValueError("output must be new and outside both source trees")
    for root in (package, host):
        if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise ValueError("export requires exact Git checkout roots")
    if git(package, "status", "--porcelain=v2", "--untracked-files=all"):
        raise ValueError("package export requires a clean source checkout")
    host_dirty = bool(git(host, "status", "--porcelain=v2", "--untracked-files=all"))
    if host_dirty and not allow_dirty_host:
        raise ValueError("host has uncommitted changes; use --allow-dirty-host for a local candidate")
    expected = json.loads((host / "fixtures/expected-output.json").read_text())
    package_commit = git(package, "rev-parse", "HEAD")
    if package_commit != expected["package"]["git_commit"]:
        raise ValueError("package commit differs from the validated baseline")
    output.mkdir(parents=True)
    version = tomllib.loads((package / "pyproject.toml").read_text())["project"]["version"]
    package_root = output / f"vst-bench-ml-{version}"
    host_root = output / f"vst-bench-dataset-host-{version}"
    copy_allowed(package, package_root, PACKAGE_FILES)
    package_identity = seal(package_root, "vst-bench-ml", package_commit)
    copy_allowed(host, host_root, HOST_FILES)
    shutil.copyfile(host / "docs/ARCHIVE-README.md", host_root / "README.md")
    expected["package"]["source_archive"] = package_identity
    for key in ("git_commit", "git_tree", "git_tree_listing_sha256"):
        expected["package"].pop(key)
    write_json(host_root / "fixtures/expected-output.json", expected)
    host_identity = seal(host_root, "vst-bench-dataset-host", git(host, "rev-parse", "HEAD"))
    receipt = {"status": "local-unpublished-candidate", "host_has_uncommitted_changes": host_dirty,
               "package_source": package_identity, "host_source": host_identity,
               "archives": [zip_snapshot(package_root), zip_snapshot(host_root)]}
    write_json(output / "archive-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty-host", action="store_true")
    args = parser.parse_args()
    receipt = export(args.package_repo, Path(__file__).resolve().parents[1],
                     args.output, args.allow_dirty_host)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
