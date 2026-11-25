# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provenance_gate import GateError  # noqa: E402


@pytest.mark.parametrize("relative", ["extra.npz", "audio/extra.npz", ".DS_Store", "notes/readme.txt"])
def test_companion_rejects_unlisted_files(tmp_path, relative):
    from provenance_gate import verify_file_inventory
    artifacts = {"records": {"path": "records.jsonl"},
                 "failure_ledger": {"path": "failures.jsonl"}, "outputs": []}
    for name in ("manifest.json", "records.jsonl", "failures.jsonl"):
        (tmp_path / name).write_text("")
    verify_file_inventory(tmp_path, "manifest.json", artifacts)
    extra = tmp_path / relative
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("unlisted")
    with pytest.raises(GateError, match="unlisted dataset file"):
        verify_file_inventory(tmp_path, "manifest.json", artifacts)
    extra.unlink()
    verify_file_inventory(tmp_path, "manifest.json", artifacts)


@pytest.mark.parametrize("kind", ["file", "directory", "dangling"])
def test_companion_inventory_rejects_links(tmp_path, kind):
    from provenance_gate import verify_file_inventory
    artifacts = {"records": {"path": "records.jsonl"},
                 "failure_ledger": {"path": "failures.jsonl"}, "outputs": []}
    target = {"file": tmp_path / "records.jsonl", "directory": tmp_path,
              "dangling": tmp_path / "absent"}[kind]
    (tmp_path / "records.jsonl").touch()
    try:
        (tmp_path / "extra-link").symlink_to(target, target_is_directory=kind == "directory")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(GateError, match="symbolic link"):
        verify_file_inventory(tmp_path, "manifest.json", artifacts)


def _v2_dataset(tmp_path):
    """A minimal schema v2 dataset: one kept attempt with a bound core ledger."""
    import json
    from provenance_gate import file_identity
    output = {"path": "audio/p000000_sus_c3.npz", "bytes": 3, "sha256": "ab" * 32}
    row = {"attempt_id": "p000000_sus_c3", "disposition": "kept", "output": output,
           "raw_output": {"bytes": 10, "sha256": "cd" * 32}}
    (tmp_path / "attempts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    manifest = {
        "artifacts": {"attempt_ledger": file_identity(tmp_path / "attempts.jsonl", tmp_path)},
        "attempts": {"planned": 1, "kept": 1, "dropped": 0, "failed": 0, "not_attempted": 0},
    }
    records = [{"patch_id": "p000000", "signal": "sus_c3", "output": output}]
    return manifest, records, row


def test_v2_inventory_allows_the_bound_core_attempt_ledger(tmp_path):
    from provenance_gate import verify_file_inventory
    artifacts = {"records": {"path": "records.jsonl"}, "failure_ledger": {"path": "failures.jsonl"},
                 "attempt_ledger": {"path": "attempts.jsonl"}, "outputs": []}
    for name in ("manifest.json", "records.jsonl", "failures.jsonl", "attempts.jsonl"):
        (tmp_path / name).write_text("")
    verify_file_inventory(tmp_path, "manifest.json", artifacts)
    del artifacts["attempt_ledger"]
    with pytest.raises(GateError, match="unlisted dataset file: attempts.jsonl"):
        verify_file_inventory(tmp_path, "manifest.json", artifacts)


def test_v2_core_attempt_ledger_must_agree_with_fixture_ledger_and_records(tmp_path):
    import json
    from provenance_gate import _check_core_attempts, file_identity
    manifest, records, row = _v2_dataset(tmp_path)
    _check_core_attempts(tmp_path, manifest, records, ["p000000_sus_c3"])
    with pytest.raises(GateError, match="does not reconcile with the fixture ledger"):
        _check_core_attempts(tmp_path, manifest, records, ["p000000_sus_c3", "p000000_gate_c2"])
    with pytest.raises(GateError, match="attempt counts"):
        _check_core_attempts(tmp_path, {**manifest, "attempts": {**manifest["attempts"], "kept": 0}},
                             records, ["p000000_sus_c3"])
    (tmp_path / "attempts.jsonl").write_text(
        json.dumps({**row, "disposition": "dropped"}) + "\n", encoding="utf-8")
    with pytest.raises(GateError, match="attempt_ledger artifact mismatch"):  # edited, not rebound
        _check_core_attempts(tmp_path, manifest, records, ["p000000_sus_c3"])
    manifest["artifacts"]["attempt_ledger"] = file_identity(tmp_path / "attempts.jsonl", tmp_path)
    with pytest.raises(GateError, match="disagrees with records"):
        _check_core_attempts(tmp_path, manifest, records, ["p000000_sus_c3"])
    with pytest.raises(GateError, match="not bound"):
        _check_core_attempts(tmp_path, {"artifacts": {}}, records, ["p000000_sus_c3"])


def test_v2_host_trace_audio_must_match_the_core_attempt_ledger(tmp_path):
    from provenance_gate import _check_core_attempts_against_trace
    manifest, _, row = _v2_dataset(tmp_path)
    trace = {"attempt_id": row["attempt_id"], "output": dict(row["raw_output"], name="raw.wav")}
    _check_core_attempts_against_trace(tmp_path, manifest, [trace])
    trace["output"]["sha256"] = "ef" * 32
    with pytest.raises(GateError, match="host audio differs"):
        _check_core_attempts_against_trace(tmp_path, manifest, [trace])
    with pytest.raises(GateError, match="no host audio identity"):
        _check_core_attempts_against_trace(tmp_path, manifest, [{"attempt_id": "p000009_sus_c3"}])
