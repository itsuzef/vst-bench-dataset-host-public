"""Strict, history-free source snapshot identities (not signatures)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

MANIFEST = "SOURCE-ARCHIVE.json"
SCHEMA = "vst-bench.source-archive/v1"
PROJECTS = {"vst-bench-ml", "vst-bench-dataset-host"}


class ArchiveError(ValueError):
    """An archive does not match its declared snapshot."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArchiveError("duplicate JSON key")
        value[key] = item
    return value


def source_files(root: Path) -> list[dict]:
    """Include every file; reject symlinks and unapproved filesystem objects."""
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ArchiveError(f"source symlink is not allowed: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ArchiveError(f"non-regular source: {relative}")
        if relative == MANIFEST:
            continue
        data = path.read_bytes()
        rows.append({"path": relative, "bytes": len(data), "sha256": digest(data)})
    return rows


def make_manifest(root: Path, project: str, upstream_commit: str) -> dict:
    rows = source_files(root)
    return {"schema": SCHEMA, "project": project,
            "upstream_commit": upstream_commit, "files": rows,
            "files_sha256": digest(canonical_bytes(rows))}


def validate_identity(identity: object, project: str) -> None:
    if not isinstance(identity, dict) or set(identity) != {
        "schema", "project", "upstream_commit", "manifest_sha256", "files_sha256"
    }:
        raise ArchiveError("incomplete source archive identity")
    if identity["schema"] != SCHEMA or identity["project"] != project:
        raise ArchiveError("wrong source archive project or schema")
    if not isinstance(identity["upstream_commit"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", identity["upstream_commit"]
    ):
        raise ArchiveError("invalid upstream commit label")
    if not all(is_digest(identity[key]) for key in ("manifest_sha256", "files_sha256")):
        raise ArchiveError("invalid source archive digest")


def verify_archive(root: Path, project: str, expected: dict | None = None) -> dict:
    """Check exact bytes/membership; caller supplies a pin for trusted comparison.

    The upstream commit is a lineage label, never proof of a Git checkout.
    A self-consistent manifest alone does not authenticate a publisher.
    """
    root = root.resolve()
    if project not in PROJECTS or (root / ".git").exists():
        raise ArchiveError("archive mode requires a known project without .git")
    manifest_path = root / MANIFEST
    if manifest_path.is_symlink():
        raise ArchiveError("manifest symlink is not allowed")
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, ValueError) as exc:
        raise ArchiveError("missing or malformed source archive manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "project", "upstream_commit", "files", "files_sha256"
    }:
        raise ArchiveError("invalid source archive schema")
    identity = {key: manifest[key] for key in
                ("schema", "project", "upstream_commit", "files_sha256")}
    identity["manifest_sha256"] = digest(raw)
    validate_identity(identity, project)
    rows = manifest["files"]
    if not isinstance(rows, list) or not rows:
        raise ArchiveError("empty source archive")
    paths = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ArchiveError("invalid source file entry")
        name = row["path"]
        if not isinstance(name, str) or not name or "\\" in name:
            raise ArchiveError("unsafe source path")
        path = PurePosixPath(name)
        if (path.is_absolute() or path.as_posix() != name
                or any(part in {"..", ".git"} for part in path.parts)
                or name == MANIFEST):
            raise ArchiveError("unsafe source path")
        if type(row["bytes"]) is not int or row["bytes"] < 0 or not is_digest(row["sha256"]):
            raise ArchiveError("invalid source file identity")
        paths.append(name)
    if paths != sorted(set(paths)):
        raise ArchiveError("source paths must be unique and sorted")
    if digest(canonical_bytes(rows)) != manifest["files_sha256"]:
        raise ArchiveError("source file-list digest mismatch")
    if rows != source_files(root):
        raise ArchiveError("source archive files differ (changed, missing, or extra)")
    if expected is not None and identity != expected:
        raise ArchiveError("source archive differs from locked expectation")
    return identity
