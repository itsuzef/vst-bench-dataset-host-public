from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "host" / "server.py"
SPEC = importlib.util.spec_from_file_location("method_fixture_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def test_out_of_range_parameter_fails_closed():
    host = object.__new__(server.FixtureHost)
    host.parameters = {index: 0.5 for index in range(6)}

    with pytest.raises(server.RpcError, match=r"outside \[0, 1\]"):
        host.set_parameters({"parameters": [{"index": 0, "value": 1.01}]})


def test_readback_mismatch_fails_closed():
    expected = {index: 0.5 for index in range(6)}
    actual = [0.5] * 6
    actual[3] = 0.25

    with pytest.raises(server.RpcError, match="reset/readback mismatch"):
        server.validate_readback(expected, actual)


def test_duplicate_attempt_id_fails_closed():
    entries = [{"attempt_id": "a"}, {"attempt_id": "a"}]

    with pytest.raises(server.RpcError, match="duplicate attempt ID"):
        server.validate_attempt_ids(entries)


def test_missing_attempt_id_fails_closed():
    with pytest.raises(server.RpcError, match="missing attempt_id"):
        server.validate_attempt_ids([{}])
