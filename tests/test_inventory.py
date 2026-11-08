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
