#!/usr/bin/env python3
"""Run the repaired deterministic workflow and every BON-678 gate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from source_archive import MANIFEST, verify_archive  # noqa: E402
from provenance_gate import (  # noqa: E402
    GateError,
    _reseal,
    append_negative_evidence,
    file_identity,
    finalize_run,
    normalized_attempts,
    package_identity,
    read_json,
    read_jsonl,
    validate_run,
)

NEGATIVE_CASES = {
    "package-wheel-renamed-sdist",
    "package-wheel-unrelated-file",
    "package-wheel-wrong-wheel",
    "wrong-plugin-identity",
    "unreachable-host",
    "malformed-parameter-manifest",
    "missing-normalization-dependency",
    "out-of-range-parameter",
    "reset-readback-mismatch",
    "duplicate-attempt-id",
    "corrupted-output",
    "incomplete-attempt-ledger",
}
PACKAGE_QUARANTINE = {
    "scripts/smoke_generate.py",
    "src/vst_bench_ml/pool.py",
    "src/vst_bench_ml/presets.py",
    "src/vst_bench_ml/sensitivity.py",
    "src/vst_bench_ml/spectral.py",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    expect_success: bool = True,
    expected_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    if expect_success and result.returncode != 0:
        fail(f"command failed ({result.returncode}): {' '.join(arguments)}\n{combined}")
    if not expect_success and result.returncode == 0:
        fail(f"negative command unexpectedly succeeded: {' '.join(arguments)}")
    if expected_text is not None and expected_text not in combined:
        fail(
            f"command output omitted expected text {expected_text!r}: "
            f"{' '.join(arguments)}\n{combined}"
        )
    return result


def evidence(
    case_id: str,
    stage: str,
    code: str,
    result: subprocess.CompletedProcess[str] | None = None,
    detail: str = "",
) -> dict[str, Any]:
    if result is None:
        payload = detail
        return_code = 0
    else:
        payload = result.stdout + result.stderr
        return_code = result.returncode
    return {
        "case_id": case_id,
        "stage": stage,
        "code": code,
        "observed_at_utc": observed_at(),
        "return_code": return_code,
        "evidence_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def start_host(
    python: Path,
    repo: Path,
    runner: Path,
    port: int,
    attempt_trace: Path,
    env: dict[str, str],
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            str(python),
            str(repo / "host" / "server.py"),
            "--runner",
            str(runner),
            "--repo-root",
            str(repo),
            "--port",
            str(port),
            "--attempt-trace",
            str(attempt_trace),
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    ready = process.stdout.readline().strip()
    if ready != f"READY 127.0.0.1:{port}":
        stderr = process.stderr.read() if process.stderr is not None else ""
        process.kill()
        fail(f"fixture host failed to start: {ready}\n{stderr}")
    return process


def stop_host(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def find_artifacts(build_dir: Path) -> tuple[Path, Path]:
    plugins = sorted(build_dir.rglob("MethodFixture.vst3"))
    runners = sorted(
        path
        for path in build_dir.rglob("method_fixture_runner")
        if path.is_file() and os.access(path, os.X_OK)
    )
    if len(plugins) != 1 or len(runners) != 1:
        fail(
            f"expected one plugin and runner; found "
            f"{len(plugins)} plugins and {len(runners)} runners"
        )
    return plugins[0], runners[0]


def cli_command(
    python: Path,
    plugin: Path,
    manifest: Path,
    output: Path,
    port: int,
) -> list[str]:
    return [
        str(python),
        "-m",
        "vst_bench_ml.cli",
        "render",
        "--plugin",
        str(plugin),
        "--param-manifest",
        str(manifest),
        "--out",
        str(output),
        "--n",
        "4",
        "--port",
        str(port),
        "--signals",
        "sus_c3,gate_c2",
        "--signal-mode",
        "all",
        "--seconds",
        "0.5",
        "--sr",
        "44100",
        "--seed-label",
        "bon-369-v1",
        "--keep-bad",
    ]


def render_once(
    python: Path,
    repo: Path,
    runner: Path,
    plugin: Path,
    manifest: Path,
    output: Path,
    trace: Path,
    env: dict[str, str],
) -> None:
    port = free_port()
    host = start_host(python, repo, runner, port, trace, env)
    try:
        run(
            cli_command(python, plugin, manifest, output, port),
            cwd=repo,
            env=env,
        )
    finally:
        stop_host(host)


def normalized_records(path: Path) -> list[dict[str, Any]]:
    records = read_jsonl(path)
    for record in records:
        record.pop("observed_at", None)
    return records


def package_ruff_paths(package_repo: Path) -> list[str]:
    if (package_repo / MANIFEST).exists():
        verify_archive(package_repo, "vst-bench-ml")
        manifest = read_json(package_repo / MANIFEST)
        paths = [row["path"] for row in manifest["files"]]
        if PACKAGE_QUARANTINE & set(paths):
            fail("source archive contains quarantined paths")
        included = [path for path in paths if path.endswith(".py")
                    and path.split("/")[0] in {"src", "tests", "scripts"}]
        if not included:
            fail("source archive has no Python lint surface")
        return included
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "src/**/*.py",
            "tests/*.py",
            "tests/**/*.py",
            "scripts/*.py",
            "scripts/**/*.py",
        ],
        cwd=package_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [line for line in result.stdout.splitlines() if line]
    included = [path for path in paths if path not in PACKAGE_QUARANTINE]
    if not included or PACKAGE_QUARANTINE - set(paths):
        fail("package Ruff surface does not match the immutable quarantine boundary")
    return included


def write_wrong_wheel(path: Path) -> None:
    dist_info = "unrelated_distribution-9.9.dist-info"
    files = {
        "unrelated_distribution/__init__.py": b"__version__ = '9.9'\n",
        f"{dist_info}/METADATA": (
            b"Metadata-Version: 2.4\n"
            b"Name: unrelated-distribution\n"
            b"Version: 9.9\n"
        ),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Generator: BON-679 negative fixture\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
    }
    record_path = f"{dist_info}/RECORD"
    rows = []
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
        rows.append(f"{name},sha256={digest.rstrip(b'=').decode()},{len(data)}\n")
    rows.append(f"{record_path},,\n")
    files[record_path] = "".join(rows).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)


def rejected_wheel_evidence(
    case_id: str,
    code: str,
    candidate: Path,
    expected_error: str,
    package_repo: Path,
    dependency_lock: Path,
    python: Path,
    expected_package: dict[str, Any],
) -> dict[str, Any]:
    try:
        package_identity(
            package_repo,
            candidate,
            dependency_lock,
            python,
            {},
            expected_package,
        )
    except GateError as exc:
        detail = str(exc)
        if expected_error not in detail:
            raise
        return evidence(
            case_id,
            "package_provenance",
            code,
            detail=detail,
        )
    fail(f"substituted package artifact was accepted: {case_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--package-repo", type=Path, required=True)
    parser.add_argument("--package-wheel", type=Path, required=True)
    parser.add_argument("--package-sdist", type=Path, required=True)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    build_dir = args.build_dir.resolve()
    package_repo = args.package_repo.resolve()
    package_wheel = args.package_wheel.resolve()
    package_sdist = args.package_sdist.resolve()
    dependency_lock = args.dependency_lock.resolve()
    python = Path(os.path.abspath(args.python))
    work_dir = args.work_dir.resolve()
    for source in (repo, package_repo):
        try:
            work_dir.relative_to(source)
        except ValueError:
            pass
        else:
            fail("validation work directory must be outside every source repository")
    if work_dir.exists():
        fail("validation work directory must not already exist")
    work_dir.mkdir(parents=True)
    if (
        not package_wheel.is_file()
        or not package_sdist.is_file()
        or not dependency_lock.is_file()
    ):
        fail("built wheel, sdist, or complete dependency lock is missing")

    plugin, runner = find_artifacts(build_dir)
    parameter_manifest = repo / "fixtures" / "parameter-manifest.json"
    midi_bank = repo / "fixtures" / "midi-bank.json"
    expected = read_json(repo / "fixtures" / "expected-output.json")
    host_archive = None
    if (repo / MANIFEST).exists():
        host_archive = verify_archive(repo, "vst-bench-dataset-host")
    if set(expected.get("required_negative_cases", [])) != NEGATIVE_CASES:
        fail("locked expected-output negative-case set is incomplete")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)

    package_identity(
        package_repo,
        package_wheel,
        dependency_lock,
        python,
        {},
        expected["package"],
    )

    run(
        [str(python), "-m", "ruff", "check", "--no-cache", "host", "scripts", "tests"],
        cwd=repo,
        env=env,
        expected_text="All checks passed",
    )
    run(
        [
            str(python),
            "-m",
            "ruff",
            "check",
            "--no-cache",
            *package_ruff_paths(package_repo),
        ],
        cwd=package_repo,
        env=env,
        expected_text="All checks passed",
    )
    run(
        [
            str(python),
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "tests/test_server.py",
            "tests/test_archives.py",
        ],
        cwd=repo,
        env=env,
        expected_text="passed",
    )

    renamed_sdist = work_dir / "renamed-sdist.whl"
    shutil.copyfile(package_sdist, renamed_sdist)
    unrelated_file = work_dir / "unrelated-file.whl"
    unrelated_file.write_bytes(b"this is not a wheel archive\n")
    wrong_wheel = work_dir / "unrelated_distribution-9.9-py3-none-any.whl"
    write_wrong_wheel(wrong_wheel)
    wheel_negative_evidence = [
        rejected_wheel_evidence(
            "package-wheel-renamed-sdist",
            "PACKAGE_WHEEL_RENAMED_SDIST",
            renamed_sdist,
            "not a valid wheel archive",
            package_repo,
            dependency_lock,
            python,
            expected["package"],
        ),
        rejected_wheel_evidence(
            "package-wheel-unrelated-file",
            "PACKAGE_WHEEL_UNRELATED_FILE",
            unrelated_file,
            "not a valid wheel archive",
            package_repo,
            dependency_lock,
            python,
            expected["package"],
        ),
        rejected_wheel_evidence(
            "package-wheel-wrong-wheel",
            "PACKAGE_WHEEL_WRONG_WHEEL",
            wrong_wheel,
            "wheel identity differs from locked expectation: distribution",
            package_repo,
            dependency_lock,
            python,
            expected["package"],
        ),
    ]

    run1 = work_dir / "run1"
    run2 = work_dir / "run2"
    trace1 = work_dir / "run1-trace.jsonl"
    trace2 = work_dir / "run2-trace.jsonl"
    render_once(
        python, repo, runner, plugin, parameter_manifest, run1, trace1, env
    )
    render_once(
        python, repo, runner, plugin, parameter_manifest, run2, trace2, env
    )
    for output, trace in ((run1, trace1), (run2, trace2)):
        finalize_run(
            output,
            trace,
            package_repo,
            package_wheel,
            dependency_lock,
            python,
            parameter_manifest,
            midi_bank,
            expected["package"],
        )

    manifests = [read_json(run1 / "manifest.json"), read_json(run2 / "manifest.json")]
    for manifest in manifests:
        package = manifest["identities"]["package"]
        source_keys = (("source_archive",) if "source_archive" in expected["package"]
                       else ("git_commit", "git_tree", "git_tree_listing_sha256"))
        for key in source_keys + (
            "repository_url",
            "distribution",
            "version",
            "wheel_filename",
            "wheel_bytes",
            "wheel_sha256",
            "wheel_payload_file_count",
            "wheel_payload_sha256",
        ):
            if package[key] != expected["package"][key]:
                fail(f"package identity differs from locked expectation: {key}")
        if host_archive is not None:
            if manifest["identities"]["host"].get("source_archive") != host_archive:
                fail("host archive identity differs from checked snapshot")
        if (
            package["wheel_record"]["path"]
            != expected["package"]["wheel_record_path"]
            or package["wheel_record"]["sha256"]
            != expected["package"]["wheel_record_sha256"]
        ):
            fail("wheel RECORD identity differs from the locked expectation")
        if (
            manifest["identities"]["dependencies"]["lock_sha256"]
            != expected["package"]["dependency_lock_sha256"]
        ):
            fail("dependency-lock checksum differs from the locked expectation")
        if manifest["identities"]["midi_bank"]["sha256"] != expected["midi_bank_sha256"]:
            fail("MIDI-bank checksum differs from the locked expectation")
        if manifest["outcomes"]["kept"] != expected["outcomes"]["kept"]:
            fail(f"unexpected outcome counts: {manifest['outcomes']}")
        if manifest["render"]["rendered_count"] != expected["rendered_count"]:
            fail("explicit rendered count differs from the locked expectation")
        if manifest["identities"]["rng"]["plan_sha256"] != expected["plan_sha256"]:
            fail("sampling-plan checksum differs from the locked expectation")
        actual_outputs = [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in manifest["artifacts"]["outputs"]
        ]
        if actual_outputs != expected["outputs"]:
            fail("output checksums differ from the locked expectation")
    if normalized_records(run1 / "records.jsonl") != normalized_records(
        run2 / "records.jsonl"
    ):
        fail("records differ after excluding observation timestamps")
    if normalized_attempts(run1) != normalized_attempts(run2):
        fail("render-attempt ledgers differ after excluding observation timestamps")

    negative_evidence = list(wheel_negative_evidence)
    malformed = work_dir / "malformed.json"
    malformed.write_text("{not-json}\n", encoding="utf-8")
    result = run(
        cli_command(python, plugin, malformed, work_dir / "negative-malformed", free_port()),
        cwd=repo,
        env=env,
        expect_success=False,
        expected_text="malformed parameter manifest",
    )
    negative_evidence.append(
        evidence("malformed-parameter-manifest", "manifest", "MALFORMED_MANIFEST", result)
    )

    result = run(
        cli_command(
            python,
            plugin,
            parameter_manifest,
            work_dir / "negative-unreachable",
            free_port(),
        ),
        cwd=repo,
        env=env,
        expect_success=False,
        expected_text="Connection refused",
    )
    negative_evidence.append(
        evidence("unreachable-host", "connect", "HOST_UNREACHABLE", result)
    )

    wrong_identity = read_json(parameter_manifest)
    wrong_identity["plugin"] = "org.example.not-the-method-fixture"
    wrong_manifest = work_dir / "wrong-identity.json"
    wrong_manifest.write_text(
        json.dumps(wrong_identity, indent=2) + "\n", encoding="utf-8"
    )
    wrong_port = free_port()
    wrong_host = start_host(
        python,
        repo,
        runner,
        wrong_port,
        work_dir / "wrong-identity-trace.jsonl",
        env,
    )
    try:
        result = run(
            cli_command(
                python,
                plugin,
                wrong_manifest,
                work_dir / "negative-wrong-identity",
                wrong_port,
            ),
            cwd=repo,
            env=env,
            expect_success=False,
            expected_text="does not match loaded plugin",
        )
    finally:
        stop_host(wrong_host)
    negative_evidence.append(
        evidence("wrong-plugin-identity", "plugin_identity", "PLUGIN_IDENTITY_MISMATCH", result)
    )

    missing_dependency_code = """
from importlib.metadata import PackageNotFoundError
from vst_bench_ml import provenance
original = provenance.importlib.metadata.version
def missing(name):
    if name == 'pyloudnorm':
        raise PackageNotFoundError(name)
    return original(name)
provenance.importlib.metadata.version = missing
try:
    provenance.normalization_identity(-14.0)
except PackageNotFoundError:
    print('missing normalization dependency rejected')
else:
    raise SystemExit('missing normalization dependency was accepted')
"""
    result = run(
        [str(python), "-c", missing_dependency_code],
        cwd=repo,
        env=env,
        expected_text="missing normalization dependency rejected",
    )
    negative_evidence.append(
        evidence(
            "missing-normalization-dependency",
            "normalization",
            "NORMALIZATION_DEPENDENCY_MISSING",
            result,
        )
    )

    selected_tests = (
        (
            "out-of-range-parameter",
            "test_out_of_range_parameter_fails_closed",
            "parameter_set",
            "PARAMETER_OUT_OF_RANGE",
        ),
        (
            "reset-readback-mismatch",
            "test_readback_mismatch_fails_closed",
            "parameter_readback",
            "READBACK_MISMATCH",
        ),
        (
            "duplicate-attempt-id",
            "test_duplicate_attempt_id_fails_closed",
            "ledger",
            "DUPLICATE_ATTEMPT_ID",
        ),
    )
    for case_id, test_name, stage, code in selected_tests:
        result = run(
            [
                str(python),
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-q",
                f"tests/test_server.py::{test_name}",
            ],
            cwd=repo,
            env=env,
            expected_text="1 passed",
        )
        negative_evidence.append(evidence(case_id, stage, code, result))

    corrupt = work_dir / "negative-corrupt"
    shutil.copytree(run2, corrupt)
    first_output = corrupt / expected["outputs"][0]["path"]
    with first_output.open("ab") as target:
        target.write(b"corruption")
    try:
        validate_run(corrupt)
    except GateError as exc:
        if "output artifact mismatch" not in str(exc):
            raise
        negative_evidence.append(
            evidence("corrupted-output", "checksum", "OUTPUT_HASH_MISMATCH", detail=str(exc))
        )
    else:
        fail("corrupted output was accepted")

    incomplete = work_dir / "negative-incomplete-ledger"
    shutil.copytree(run2, incomplete)
    incomplete_manifest = read_json(incomplete / "manifest.json")
    incomplete_ledger = incomplete / "failures.jsonl"
    entries = read_jsonl(incomplete_ledger)[1:]
    for sequence, item in enumerate(entries):
        item["sequence"] = sequence
    incomplete_ledger.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in entries),
        encoding="utf-8",
    )
    incomplete_manifest["artifacts"]["failure_ledger"] = file_identity(
        incomplete_ledger, incomplete
    )
    _reseal(incomplete / "manifest.json", incomplete_manifest)
    try:
        validate_run(incomplete)
    except GateError as exc:
        if "incomplete" not in str(exc):
            raise
        negative_evidence.append(
            evidence(
                "incomplete-attempt-ledger",
                "ledger",
                "INCOMPLETE_ATTEMPT_LEDGER",
                detail=str(exc),
            )
        )
    else:
        fail("incomplete attempt ledger was accepted")

    append_negative_evidence(run1, negative_evidence)
    validate_run(run1, NEGATIVE_CASES)
    validate_run(run2)
    if {item["case_id"] for item in negative_evidence} != NEGATIVE_CASES:
        fail("negative-case evidence set is incomplete")

    print("PASS: exact built-wheel package provenance and verified source identity")
    print("PASS: wheel archive, RECORD, installed payload, and imported module identities")
    print("PASS: complete dependency-lock and installed native-library identities")
    print("PASS: MIDI bank, reset policy, ordered parameters/readback, and rendered count")
    print("PASS: 2 deterministic runs; 8 kept attempts per append-only ledger")
    print(f"PASS: plan SHA-256 {expected['plan_sha256']}")
    print("PASS: 8 locked output SHA-256 checksums")
    print("PASS: 12 bound negative cases, including wheel substitution rejection")
    print("PASS: complete authoritative Ruff surfaces")


if __name__ == "__main__":
    main()
