#!/usr/bin/env python3
"""Finalize and verify the BON-678 provenance and append-only attempt ledger."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from source_archive import ArchiveError, MANIFEST, validate_identity, verify_archive

SCHEMA = "vst-bench-ml.provenance/v1"
LEDGER_SCHEMA = "vst-bench-ml.attempt-ledger/v1"
RESET_POLICY_NAME = "fresh-runner-process-and-plugin-instance-per-render"


class GateError(ValueError):
    """Raised when a locked provenance or ledger requirement fails closed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: str | Path, root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    file_path = Path(path).resolve()
    try:
        relative = file_path.relative_to(root_path)
    except ValueError as exc:
        raise GateError(f"artifact escapes its root: {file_path}") from exc
    if not file_path.is_file():
        raise GateError(f"artifact is missing: {relative}")
    return {
        "path": relative.as_posix(),
        "bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
    }


def read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"malformed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateError(f"expected JSON object: {path}")
    return value


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    entries = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise GateError(f"JSONL entry is not an object at line {line_number}")
            entries.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"malformed JSONL: {path}") from exc
    return entries


def append_jsonl(path: str | Path, entries: list[dict[str, Any]]) -> None:
    target = Path(path)
    with target.open("a", encoding="utf-8") as sink:
        for entry in entries:
            sink.write(json.dumps(entry, allow_nan=False, sort_keys=True) + "\n")
            sink.flush()
            os.fsync(sink.fileno())


def _git(repo: Path, *arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=not binary,
    )
    return result.stdout


def native_library_identities(python: Path) -> list[dict[str, Any]]:
    code = r'''
import hashlib
import importlib.metadata
import json

items = []
seen = set()
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name") or "unknown"
    version = distribution.version
    for relative in distribution.files or ():
        text = str(relative)
        if not text.endswith((".so", ".dylib", ".dll", ".pyd")):
            continue
        path = distribution.locate_file(relative)
        if not path.is_file():
            continue
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append({
            "distribution": name,
            "version": version,
            "artifact": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
        })
print(json.dumps(sorted(items, key=lambda item: (
    item["distribution"].casefold(), item["artifact"], item["sha256"]
))))
'''
    result = subprocess.run(
        [str(python), "-c", code], check=True, capture_output=True, text=True
    )
    value = json.loads(result.stdout)
    if not isinstance(value, list) or not value:
        raise GateError("no installed native-library identities were observed")
    return value


def _normalized_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _wheel_archive_identity(
    wheel: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if wheel.suffix != ".whl" or not wheel.is_file() or not zipfile.is_zipfile(wheel):
        raise GateError("package wheel is not a valid wheel archive")
    try:
        with zipfile.ZipFile(wheel) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise GateError("wheel archive contains duplicate paths")
            for name in names:
                parts = Path(name).parts
                if name.startswith("/") or "\\" in name or ".." in parts:
                    raise GateError("wheel archive contains an unsafe path")
            corrupt = archive.testzip()
            if corrupt is not None:
                raise GateError(f"wheel archive contains a corrupt member: {corrupt}")

            record_paths = [name for name in names if name.endswith(".dist-info/RECORD")]
            if len(record_paths) != 1:
                raise GateError("wheel archive must contain exactly one RECORD")
            record_path = record_paths[0]
            dist_info = record_path.rsplit("/", 1)[0]
            metadata_path = f"{dist_info}/METADATA"
            wheel_metadata_path = f"{dist_info}/WHEEL"
            if metadata_path not in names or wheel_metadata_path not in names:
                raise GateError("wheel archive is missing METADATA or WHEEL")
            if any(
                ".dist-info/" in name and not name.startswith(f"{dist_info}/")
                for name in names
            ):
                raise GateError("wheel archive contains multiple dist-info identities")

            metadata = BytesParser(policy=policy.default).parsebytes(
                archive.read(metadata_path)
            )
            distribution = metadata.get("Name")
            version = metadata.get("Version")
            if not distribution or not version:
                raise GateError("wheel METADATA omits distribution or version")
            filename_parts = wheel.name.removesuffix(".whl").split("-")
            if len(filename_parts) < 5:
                raise GateError("wheel filename is malformed")
            if _normalized_distribution(filename_parts[0]) != _normalized_distribution(
                distribution
            ) or filename_parts[1].replace("_", "-") != version.replace("_", "-"):
                raise GateError("wheel filename disagrees with METADATA identity")
            expected_dist_info = (
                f"{_normalized_distribution(distribution).replace('-', '_')}-"
                f"{version.replace('-', '_')}.dist-info"
            )
            if dist_info != expected_dist_info:
                raise GateError("wheel dist-info path disagrees with METADATA identity")
            wheel_metadata = BytesParser(policy=policy.default).parsebytes(
                archive.read(wheel_metadata_path)
            )
            if not wheel_metadata.get("Wheel-Version") or not wheel_metadata.get_all("Tag"):
                raise GateError("wheel WHEEL metadata is incomplete")

            record_bytes = archive.read(record_path)
            try:
                rows = list(
                    csv.reader(io.StringIO(record_bytes.decode("utf-8")), strict=True)
                )
            except (UnicodeDecodeError, csv.Error) as exc:
                raise GateError("wheel RECORD is malformed") from exc
            if any(len(row) != 3 for row in rows):
                raise GateError("wheel RECORD contains a malformed row")
            if len({row[0] for row in rows}) != len(rows) or {
                row[0] for row in rows
            } != set(names):
                raise GateError("wheel RECORD does not identify every archive file exactly")

            payload = []
            record_entries = []
            for path, encoded_hash, encoded_size in rows:
                data = archive.read(path)
                digest = hashlib.sha256(data).digest()
                digest_hex = digest.hex()
                record_entries.append(
                    {"path": path, "hash": encoded_hash, "size": encoded_size}
                )
                if path == record_path:
                    if encoded_hash or encoded_size:
                        raise GateError("wheel RECORD self-entry must omit hash and size")
                    continue
                if not encoded_hash.startswith("sha256="):
                    raise GateError("wheel RECORD must use SHA-256 for every payload file")
                expected_hash = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                if encoded_hash != f"sha256={expected_hash}":
                    raise GateError(f"wheel RECORD hash mismatch: {path}")
                try:
                    expected_size = int(encoded_size)
                except ValueError as exc:
                    raise GateError(f"wheel RECORD size is malformed: {path}") from exc
                if expected_size != len(data):
                    raise GateError(f"wheel RECORD size mismatch: {path}")
                payload.append({"path": path, "bytes": len(data), "sha256": digest_hex})
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise GateError("package wheel is not a valid wheel archive") from exc

    payload.sort(key=lambda item: item["path"])
    record_entries.sort(key=lambda item: item["path"])
    identity = {
        "distribution": distribution,
        "version": version,
        "filename": wheel.name,
        "bytes": wheel.stat().st_size,
        "sha256": sha256_file(wheel),
        "record": {
            "path": record_path,
            "bytes": len(record_bytes),
            "sha256": hashlib.sha256(record_bytes).hexdigest(),
            "entries_sha256": canonical_sha256(record_entries),
        },
        "payload_file_count": len(payload),
        "payload_sha256": canonical_sha256(payload),
    }
    return identity, payload


def _installed_distribution_identity(
    python: Path,
    wheel: Path,
    wheel_identity: dict[str, Any],
    wheel_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    code = r"""
import csv
import hashlib
import importlib
import importlib.metadata
import io
import json
import pathlib
import sys

distribution = importlib.metadata.distribution(sys.argv[1])
module = importlib.import_module("vst_bench_ml")
files = {}
for relative in distribution.files or ():
    path = distribution.locate_file(relative)
    if path.is_file():
        data = path.read_bytes()
        files[str(relative)] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
record_paths = [name for name in files if name.endswith(".dist-info/RECORD")]
if len(record_paths) != 1:
    raise SystemExit("installed distribution must contain exactly one RECORD")
record_path = record_paths[0]
record_bytes = distribution.locate_file(record_path).read_bytes()
rows = list(csv.reader(io.StringIO(record_bytes.decode("utf-8")), strict=True))
if any(len(row) != 3 for row in rows):
    raise SystemExit("installed RECORD contains a malformed row")
direct_url_text = distribution.read_text("direct_url.json")
print(json.dumps({
    "distribution": distribution.metadata.get("Name"),
    "version": distribution.version,
    "module": str(pathlib.Path(module.__file__).resolve()),
    "expected_module": str(distribution.locate_file("vst_bench_ml/__init__.py").resolve()),
    "files": files,
    "record_path": record_path,
    "record_bytes": len(record_bytes),
    "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
    "record_rows": rows,
    "direct_url": json.loads(direct_url_text) if direct_url_text else None,
}))
"""
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            code,
            _normalized_distribution(wheel_identity["distribution"]),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GateError(f"installed distribution probe failed: {result.stderr.strip()}")
    installed = json.loads(result.stdout)
    if installed["module"] != installed["expected_module"]:
        raise GateError("imported module is not owned by the installed distribution")
    if _normalized_distribution(installed["distribution"]) != _normalized_distribution(
        wheel_identity["distribution"]
    ) or installed["version"] != wheel_identity["version"]:
        raise GateError("installed distribution identity differs from the supplied wheel")

    installed_record = {row[0]: row[1:] for row in installed["record_rows"]}
    matched_payload = []
    for expected in wheel_payload:
        path = expected["path"]
        actual = installed["files"].get(path)
        if actual != {"bytes": expected["bytes"], "sha256": expected["sha256"]}:
            raise GateError(f"installed distribution file differs from wheel: {path}")
        row = installed_record.get(path)
        digest = bytes.fromhex(expected["sha256"])
        encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if row != [f"sha256={encoded}", str(expected["bytes"])]:
            raise GateError(f"installed RECORD differs from wheel RECORD: {path}")
        matched_payload.append(expected)
    if canonical_sha256(matched_payload) != wheel_identity["payload_sha256"]:
        raise GateError("installed payload identity differs from supplied wheel")

    imported_module = next(
        (item for item in wheel_payload if item["path"] == "vst_bench_ml/__init__.py"),
        None,
    )
    if imported_module is None or installed["files"].get(imported_module["path"]) != {
        "bytes": imported_module["bytes"],
        "sha256": imported_module["sha256"],
    }:
        raise GateError("imported module identity differs from supplied wheel")

    direct_url = installed.get("direct_url")
    if not isinstance(direct_url, dict) or not isinstance(direct_url.get("url"), str):
        raise GateError("installed distribution omits direct wheel provenance")
    parsed_url = urlparse(direct_url["url"])
    if parsed_url.scheme != "file" or Path(unquote(parsed_url.path)).resolve() != wheel.resolve():
        raise GateError("supplied wheel is not the wheel installed by the interpreter")

    installed_rows = [
        {"path": row[0], "hash": row[1], "size": row[2]}
        for row in installed["record_rows"]
    ]
    installed_rows.sort(key=lambda item: item["path"])
    return {
        "distribution": installed["distribution"],
        "version": installed["version"],
        "record": {
            "path": installed["record_path"],
            "bytes": installed["record_bytes"],
            "sha256": installed["record_sha256"],
            "entries_sha256": canonical_sha256(installed_rows),
        },
        "matched_wheel_file_count": len(matched_payload),
        "matched_wheel_payload_sha256": canonical_sha256(matched_payload),
        "imported_module": imported_module["path"],
        "imported_module_sha256": imported_module["sha256"],
        "direct_url_matches_supplied_wheel": True,
    }


def package_identity(
    package_repo: Path,
    wheel: Path,
    dependency_lock: Path,
    python: Path,
    existing: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    archive_identity = None
    if (package_repo / MANIFEST).exists():
        if not isinstance(expected.get("source_archive"), dict):
            raise GateError("source archive has no locked expectation")
        try:
            archive_identity = verify_archive(
                package_repo, "vst-bench-ml", expected["source_archive"]
            )
        except ArchiveError as exc:
            raise GateError(str(exc)) from exc
    else:
        if "source_archive" in expected:
            raise GateError("locked source archive is missing")
        status = _git(package_repo, "status", "--porcelain=v2", "--untracked-files=all")
        if status:
            raise GateError("package repository is dirty")
    wheel_identity, wheel_payload = _wheel_archive_identity(wheel)
    locked_values = {
        "distribution": wheel_identity["distribution"],
        "version": wheel_identity["version"],
        "wheel_filename": wheel_identity["filename"],
        "wheel_bytes": wheel_identity["bytes"],
        "wheel_sha256": wheel_identity["sha256"],
        "wheel_record_path": wheel_identity["record"]["path"],
        "wheel_record_sha256": wheel_identity["record"]["sha256"],
        "wheel_payload_file_count": wheel_identity["payload_file_count"],
        "wheel_payload_sha256": wheel_identity["payload_sha256"],
    }
    for key, actual in locked_values.items():
        if expected.get(key) != actual:
            raise GateError(f"wheel identity differs from locked expectation: {key}")
    installed = _installed_distribution_identity(
        python, wheel, wheel_identity, wheel_payload
    )
    try:
        Path(installed["imported_module"]).relative_to(package_repo.resolve())
    except ValueError:
        pass
    else:
        raise GateError("validation imported vst-bench-ml from the source repository")
    if installed["version"].endswith("+source"):
        raise GateError("validation did not import the built wheel")
    if archive_identity:
        source_identity = {"source_kind": "archive", "source_archive": archive_identity}
    else:
        tree_listing = _git(package_repo, "ls-tree", "-r", "-z", "HEAD", binary=True)
        source_identity = {
            "git_commit": str(_git(package_repo, "rev-parse", "HEAD")).strip(),
            "git_tree": str(_git(package_repo, "rev-parse", "HEAD^{tree}")).strip(),
            "git_tree_listing_sha256": hashlib.sha256(tree_listing).hexdigest(),
        }
    identity = dict(existing)
    identity.update(
        {
            "distribution": installed["distribution"],
            "version": installed["version"],
            "repository_url": (expected["repository_url"] if archive_identity else
                               str(_git(package_repo, "remote", "get-url", "origin")).strip()),
            **source_identity,
            "dirty": False,
            "wheel_filename": wheel_identity["filename"],
            "wheel_bytes": wheel_identity["bytes"],
            "wheel_sha256": wheel_identity["sha256"],
            "wheel_record": wheel_identity["record"],
            "wheel_payload_file_count": wheel_identity["payload_file_count"],
            "wheel_payload_sha256": wheel_identity["payload_sha256"],
            "installed_distribution": installed,
            "installed_module": installed["imported_module"],
        }
    )
    return identity


def _reseal(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest.pop("integrity", None)
    manifest["integrity"] = {
        "algorithm": "sha256",
        "payload_sha256": canonical_sha256(manifest),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def finalize_run(
    run_dir: Path,
    trace_path: Path,
    package_repo: Path,
    wheel: Path,
    dependency_lock: Path,
    python: Path,
    parameter_manifest: Path,
    midi_bank: Path,
    expected_package: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    ledger_path = run_dir / "failures.jsonl"
    manifest = read_json(manifest_path)
    records = read_jsonl(run_dir / "records.jsonl")
    traces = read_jsonl(trace_path)
    if ledger_path.stat().st_size != 0:
        raise GateError("attempt ledger was not empty before append-only finalization")
    if len(traces) != len(records):
        raise GateError("render trace count does not match kept records")

    parameters = read_json(parameter_manifest)
    definitions = sorted(parameters.get("params", []), key=lambda item: item["index"])
    if [item.get("index") for item in definitions] != list(range(len(definitions))):
        raise GateError("parameter definitions are not an exact ordered index set")
    bank = read_json(midi_bank)
    signals = bank.get("signals")
    if not isinstance(signals, dict) or not signals:
        raise GateError("MIDI bank has no signal definitions")

    record_by_attempt = {
        f"{record['patch_id']}_{record['signal']}": record for record in records
    }
    manifest["identities"]["plugin"]["path"] = "MethodFixture.vst3"
    ledger_entries = []
    readbacks = []
    host_digest = canonical_sha256(manifest["identities"]["host"])
    plugin_digest = canonical_sha256(manifest["identities"]["plugin"])
    parameter_digest = canonical_sha256(definitions)
    for sequence, trace in enumerate(traces):
        attempt_id = trace.get("attempt_id")
        record = record_by_attempt.get(attempt_id)
        if record is None:
            raise GateError(f"render trace has no matching record: {attempt_id}")
        signal = record["signal"]
        expected_midi = signals.get(signal)
        if not isinstance(expected_midi, list):
            raise GateError(f"MIDI bank omits signal: {signal}")
        if canonical_sha256(expected_midi) != trace.get("midi_events_sha256"):
            raise GateError(f"MIDI trace differs from locked bank: {attempt_id}")
        readback = trace.get("parameter_readback")
        if not isinstance(readback, list) or len(readback) != len(definitions):
            raise GateError(f"incomplete parameter readback: {attempt_id}")
        readbacks.append({"attempt_id": attempt_id, "values": readback})
        ledger_entries.append(
            {
                "schema": LEDGER_SCHEMA,
                "sequence": sequence,
                "kind": "render_attempt",
                "attempt_id": attempt_id,
                "record_id": attempt_id,
                "plan_id": manifest["identities"]["rng"]["plan_sha256"],
                "patch_id": record["patch_id"],
                "signal_id": signal,
                "started_at_utc": trace["started_at_utc"],
                "completed_at_utc": trace["completed_at_utc"],
                "outcome": "kept",
                "stage": "finalized",
                "code": "KEPT",
                "reason": None,
                "retry_count": trace["retry_count"],
                "host_identity_sha256": host_digest,
                "plugin_identity_sha256": plugin_digest,
                "parameter_identity_sha256": parameter_digest,
                "midi_events_sha256": trace["midi_events_sha256"],
                "parameter_readback": readback,
                "reset_policy": trace["reset_policy"],
                "partial_artifacts": [record["output"]],
                "normalization_path": manifest["identities"]["normalization"],
                "final_disposition": "kept",
            }
        )
    append_jsonl(ledger_path, ledger_entries)

    package = package_identity(
        package_repo,
        wheel,
        dependency_lock,
        python,
        manifest["identities"]["package"],
        expected_package,
    )
    manifest["identities"]["package"] = package
    manifest["identities"]["midi_bank"] = {
        "schema": bank.get("schema"),
        "filename": midi_bank.name,
        "bytes": midi_bank.stat().st_size,
        "sha256": sha256_file(midi_bank),
        "signals": list(signals),
    }
    manifest["identities"]["dependencies"].update(
        {
            "lock_filename": dependency_lock.name,
            "lock_bytes": dependency_lock.stat().st_size,
            "lock_sha256": sha256_file(dependency_lock),
            "native_libraries": native_library_identities(python),
        }
    )
    manifest["identities"]["parameters"].update(
        {
            "ordered_definitions": definitions,
            "ordered_definitions_sha256": parameter_digest,
            "observed_readback": readbacks,
        }
    )
    manifest["render"] = {
        "sample_rate": manifest["request"]["sample_rate"],
        "sample_count": int(
            manifest["request"]["sample_rate"] * manifest["request"]["seconds"]
        ),
        "reset_policy": ledger_entries[0]["reset_policy"],
        "requested_count": len(records),
        "rendered_count": len(traces),
        "kept_count": len(records),
        "dropped_count": 0,
        "failed_count": 0,
    }
    manifest["outcomes"]["attempted"] = len(traces)
    manifest["outcomes"]["rendered"] = len(traces)
    manifest["artifacts"]["failure_ledger"] = file_identity(ledger_path, run_dir)
    manifest["validation"] = {"negative_case_ids": []}
    _reseal(manifest_path, manifest)
    return validate_run(run_dir)


def append_negative_evidence(
    run_dir: Path, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    ledger_path = run_dir / "failures.jsonl"
    manifest = read_json(manifest_path)
    existing = read_jsonl(ledger_path)
    entries = []
    for offset, item in enumerate(evidence, start=len(existing)):
        entries.append(
            {
                "schema": LEDGER_SCHEMA,
                "sequence": offset,
                "kind": "negative_case",
                "case_id": item["case_id"],
                "observed_at_utc": item["observed_at_utc"],
                "outcome": "expected_rejection",
                "stage": item["stage"],
                "code": item["code"],
                "return_code": item["return_code"],
                "evidence_sha256": item["evidence_sha256"],
                "final_disposition": "expected_pass",
            }
        )
    append_jsonl(ledger_path, entries)
    manifest["artifacts"]["failure_ledger"] = file_identity(ledger_path, run_dir)
    manifest["validation"]["negative_case_ids"] = [
        item["case_id"] for item in evidence
    ]
    _reseal(manifest_path, manifest)
    return manifest


def validate_run(
    run_dir: Path, required_negative_cases: set[str] | None = None
) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema") != SCHEMA:
        raise GateError("unsupported manifest schema")
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        raise GateError("manifest integrity is missing")
    payload = dict(manifest)
    payload.pop("integrity", None)
    if canonical_sha256(payload) != integrity.get("payload_sha256"):
        raise GateError("manifest payload hash mismatch")

    package = manifest.get("identities", {}).get("package", {})
    for key in (
        "distribution",
        "version",
        "repository_url",
        "dirty",
        "wheel_filename",
        "wheel_bytes",
        "wheel_sha256",
        "wheel_record",
        "wheel_payload_file_count",
        "wheel_payload_sha256",
        "installed_distribution",
        "installed_module",
    ):
        if key not in package:
            raise GateError(f"package provenance is incomplete: {key}")
    if package.get("source_kind", "git") == "archive":
        try:
            validate_identity(package.get("source_archive"), "vst-bench-ml")
        except ArchiveError as exc:
            raise GateError(str(exc)) from exc
        if any(key in package for key in ("git_commit", "git_tree", "git_tree_listing_sha256")):
            raise GateError("archive provenance must not claim a Git checkout")
    elif package.get("source_kind", "git") == "git":
        if "source_archive" in package:
            raise GateError("Git provenance must not claim an archive")
        for key in ("git_commit", "git_tree", "git_tree_listing_sha256"):
            if not package.get(key):
                raise GateError(f"package provenance is incomplete: {key}")
    else:
        raise GateError("unsupported package source kind")
    if package["dirty"] is not False or package["version"].endswith("+source"):
        raise GateError("package provenance is not a clean built wheel")
    wheel_record = package["wheel_record"]
    installed = package["installed_distribution"]
    installed_record = installed.get("record", {})
    for label, record in (
        ("wheel", wheel_record),
        ("installed distribution", installed_record),
    ):
        if not all(record.get(key) for key in ("path", "bytes", "sha256", "entries_sha256")):
            raise GateError(f"{label} RECORD identity is incomplete")
    if (
        _normalized_distribution(installed.get("distribution", ""))
        != _normalized_distribution(package["distribution"])
        or installed.get("version") != package["version"]
    ):
        raise GateError("installed distribution identity differs from wheel identity")
    if (
        installed.get("matched_wheel_file_count")
        != package["wheel_payload_file_count"]
        or installed.get("matched_wheel_payload_sha256")
        != package["wheel_payload_sha256"]
    ):
        raise GateError("installed distribution payload differs from wheel identity")
    if (
        installed.get("imported_module") != package["installed_module"]
        or not installed.get("imported_module_sha256")
        or installed.get("direct_url_matches_supplied_wheel") is not True
    ):
        raise GateError("imported distribution is not bound to the supplied wheel")

    identities = manifest["identities"]
    host = identities.get("host", {})
    if host.get("source_dirty") is not False:
        raise GateError("host provenance is not from a clean source tree")
    if host.get("source_kind", "git") == "archive":
        try:
            validate_identity(host.get("source_archive"), "vst-bench-dataset-host")
        except ArchiveError as exc:
            raise GateError(str(exc)) from exc
        if host.get("source_commit") != "archive-sha256:" + host["source_archive"]["files_sha256"]:
            raise GateError("host archive revision mismatch")
    elif host.get("source_kind", "git") != "git" or "source_archive" in host:
        raise GateError("unsupported or mixed host source identity")
    dependencies = identities.get("dependencies", {})
    if not dependencies.get("lock_sha256"):
        raise GateError("dependency-lock identity is missing")
    native = dependencies.get("native_libraries")
    if not isinstance(native, list) or not native:
        raise GateError("native-library identities are missing")
    for item in native:
        if not item.get("sha256") or not item.get("artifact"):
            raise GateError("native-library identity is incomplete")
    midi = identities.get("midi_bank", {})
    if not midi.get("sha256") or not midi.get("signals"):
        raise GateError("MIDI-bank identity is missing")
    parameters = identities.get("parameters", {})
    definitions = parameters.get("ordered_definitions")
    readbacks = parameters.get("observed_readback")
    if not isinstance(definitions, list) or not definitions:
        raise GateError("ordered parameter definitions are missing")
    if not isinstance(readbacks, list):
        raise GateError("observed parameter readback is missing")

    render = manifest.get("render", {})
    reset = render.get("reset_policy", {})
    if reset.get("name") != RESET_POLICY_NAME:
        raise GateError("reset policy is missing or changed")
    for key in ("requested_count", "rendered_count", "kept_count", "dropped_count", "failed_count"):
        if not isinstance(render.get(key), int):
            raise GateError(f"render count is missing: {key}")

    artifacts = manifest.get("artifacts", {})
    for name in ("records", "failure_ledger"):
        identity = artifacts.get(name, {})
        path = run_dir / identity.get("path", "")
        if not path.is_file() or file_identity(path, run_dir) != identity:
            raise GateError(f"bound {name} artifact mismatch")
    for identity in artifacts.get("outputs", []):
        path = run_dir / identity.get("path", "")
        if not path.is_file() or file_identity(path, run_dir) != identity:
            raise GateError(f"bound output artifact mismatch: {identity.get('path')}")

    records = read_jsonl(run_dir / artifacts["records"]["path"])
    entries = read_jsonl(run_dir / artifacts["failure_ledger"]["path"])
    for sequence, entry in enumerate(entries):
        if entry.get("sequence") != sequence:
            raise GateError("attempt ledger is not append-ordered")
    attempts = [entry for entry in entries if entry.get("kind") == "render_attempt"]
    negative = [entry for entry in entries if entry.get("kind") == "negative_case"]
    if len(attempts) != render["requested_count"]:
        raise GateError("attempt ledger is incomplete")
    attempt_ids = [entry.get("attempt_id") for entry in attempts]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise GateError("attempt ledger contains duplicate attempt IDs")
    expected_ids = {f"{record['patch_id']}_{record['signal']}" for record in records}
    if set(attempt_ids) != expected_ids:
        raise GateError("attempt ledger does not reconcile with records")
    required_attempt_fields = (
        "plan_id",
        "patch_id",
        "signal_id",
        "started_at_utc",
        "completed_at_utc",
        "outcome",
        "stage",
        "code",
        "retry_count",
        "host_identity_sha256",
        "plugin_identity_sha256",
        "parameter_identity_sha256",
        "midi_events_sha256",
        "parameter_readback",
        "reset_policy",
        "partial_artifacts",
        "normalization_path",
        "final_disposition",
    )
    for entry in attempts:
        missing = [key for key in required_attempt_fields if key not in entry]
        if missing:
            raise GateError(f"attempt ledger entry is incomplete: {missing}")
        if len(entry["parameter_readback"]) != len(definitions):
            raise GateError("attempt ledger readback is incomplete")
        expected_identity_digests = {
            "host_identity_sha256": canonical_sha256(identities["host"]),
            "plugin_identity_sha256": canonical_sha256(identities["plugin"]),
            "parameter_identity_sha256": canonical_sha256(definitions),
        }
        for key, expected in expected_identity_digests.items():
            if entry[key] != expected:
                raise GateError(f"attempt ledger identity mismatch: {key}")
    outcomes = [entry["outcome"] for entry in attempts]
    if outcomes.count("kept") != render["kept_count"]:
        raise GateError("kept count does not reconcile with attempt ledger")
    if render["rendered_count"] != len(attempts) or len(records) != render["kept_count"]:
        raise GateError("explicit render counts do not reconcile")
    if len(readbacks) != len(attempts):
        raise GateError("manifest readback count does not reconcile")

    if required_negative_cases is not None:
        observed = {entry.get("case_id") for entry in negative}
        if observed != required_negative_cases:
            raise GateError(
                f"negative-case ledger mismatch: observed={sorted(observed)} "
                f"required={sorted(required_negative_cases)}"
            )
        if any(entry.get("outcome") != "expected_rejection" for entry in negative):
            raise GateError("negative-case ledger contains an unproven outcome")
    return manifest


def normalized_attempts(run_dir: Path) -> list[dict[str, Any]]:
    manifest = read_json(run_dir / "manifest.json")
    ledger = read_jsonl(run_dir / manifest["artifacts"]["failure_ledger"]["path"])
    normalized = []
    for entry in ledger:
        if entry.get("kind") != "render_attempt":
            continue
        value = dict(entry)
        value.pop("started_at_utc", None)
        value.pop("completed_at_utc", None)
        normalized.append(value)
    return normalized
