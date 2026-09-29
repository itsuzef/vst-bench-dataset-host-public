#!/usr/bin/env python3
"""Local JSON-RPC host for the self-authored method fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_archive import MANIFEST, verify_archive  # noqa: E402

SDK_COMMIT = "3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96"
SOURCE_REPOSITORY = "https://github.com/itsuzef/vst-bench-dataset-host.git"
PLUGIN_IDENTIFIER = "org.example.method-fixture.v1"
PLUGIN_CLASS_UID = "5F94B1C27A624DF0A910B2D364E0F871"
PLUGIN_NAME = "Method Fixture Instrument"
PLUGIN_VENDOR = "Independent Method Fixture"
PLUGIN_VERSION = "0.1.0-private"
PARAMETERS = (
    {"index": 0, "parameter_id": "gain", "name": "Gain", "num_steps": 2147483647, "default_value": 0.5},
    {"index": 1, "parameter_id": "tone", "name": "Tone", "num_steps": 2147483647, "default_value": 0.5},
    {"index": 2, "parameter_id": "waveform", "name": "Waveform", "num_steps": 3, "default_value": 0.0},
    {"index": 3, "parameter_id": "octave", "name": "Octave", "num_steps": 5, "default_value": 0.5},
    {"index": 4, "parameter_id": "enabled", "name": "Enabled", "num_steps": 2, "default_value": 1.0},
    {"index": 5, "parameter_id": "control_only", "name": "Control Only", "num_steps": 2147483647, "default_value": 0.5},
)
RESET_POLICY = {
    "name": "fresh-runner-process-and-plugin-instance-per-render",
    "steps": [
        "load a new plugin component in a new runner process",
        "apply all six normalized parameters",
        "read back all six parameters",
        "activate the component, which resets fixture DSP state",
        "process exactly one offline render",
        "deactivate and terminate the runner process",
    ],
}


class RpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise RpcError(-32602, f"plugin path is not a file or bundle: {path}")

    digest = hashlib.sha256()
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        if child.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(child).encode("utf-8"))
        elif child.is_file():
            digest.update(b"file\0")
            with child.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        elif child.is_dir():
            digest.update(b"directory\0")
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_readback(expected: dict[int, float], actual: list[float]) -> None:
    if len(actual) != len(PARAMETERS):
        raise RpcError(-32021, "reset/readback mismatch: wrong parameter count")
    for index, expected_value in expected.items():
        if abs(float(actual[index]) - expected_value) > 1e-9:
            raise RpcError(
                -32021,
                f"reset/readback mismatch at parameter {index}: "
                f"{actual[index]} != {expected_value}",
            )


def validate_attempt_ids(entries: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for entry in entries:
        attempt_id = entry.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise RpcError(-32602, "attempt ledger entry is missing attempt_id")
        if attempt_id in seen:
            raise RpcError(-32022, f"duplicate attempt ID: {attempt_id}")
        seen.add(attempt_id)


class FixtureHost:
    def __init__(self, runner: Path, repo_root: Path, attempt_trace: Path | None = None):
        self.runner = runner.resolve()
        self.repo_root = repo_root.resolve()
        self.plugin_path: Path | None = None
        self.plugin_sha256: str | None = None
        self.parameters = {
            int(item["index"]): float(item["default_value"]) for item in PARAMETERS
        }
        self.attempt_ids: set[str] = set()
        self.attempt_trace = attempt_trace.resolve() if attempt_trace else None

        if not self.runner.is_file():
            raise RuntimeError(f"runner does not exist: {self.runner}")
        self.runner_sha256 = sha256_file(self.runner)
        self.server_sha256 = sha256_file(Path(__file__).resolve())
        self.source_archive = None
        if (self.repo_root / MANIFEST).exists():
            self.source_archive = verify_archive(self.repo_root, "vst-bench-dataset-host")
            self.source_commit = "archive-sha256:" + self.source_archive["files_sha256"]
            self.source_dirty = False
        else:
            if Path(self._git("rev-parse", "--show-toplevel")).resolve() != self.repo_root:
                raise RuntimeError("host source root is not a Git checkout root")
            self.source_commit = self._git("rev-parse", "HEAD")
            self.source_dirty = bool(
                self._git("status", "--porcelain=v2", "--untracked-files=all")
            )
        if self.attempt_trace is not None:
            if self.attempt_trace.exists():
                raise RuntimeError("attempt trace must not already exist")
            self.attempt_trace.parent.mkdir(parents=True, exist_ok=True)

    def _append_attempt(self, entry: dict[str, Any]) -> None:
        if self.attempt_trace is None:
            return
        with self.attempt_trace.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(entry, allow_nan=False, sort_keys=True) + "\n")
            sink.flush()
            os.fsync(sink.fileno())

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _runner_call(self, *arguments: str) -> dict[str, Any]:
        result = subprocess.run(
            [str(self.runner), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise RpcError(-32020, f"fixture runner failed: {detail}")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RpcError(-32020, "fixture runner returned malformed JSON") from error
        if not isinstance(value, dict):
            raise RpcError(-32020, "fixture runner returned a non-object")
        return value

    def load_plugin(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.plugin_path is not None:
            raise RpcError(-32002, "a plugin is already loaded")
        raw_path = params.get("plugin_path")
        if not isinstance(raw_path, str) or not raw_path:
            raise RpcError(-32602, "plugin_path is required")
        plugin_path = Path(raw_path).resolve()
        if not plugin_path.exists():
            raise RpcError(-32602, f"plugin path does not exist: {plugin_path}")

        inspection = self._runner_call("inspect", str(plugin_path))
        observed_uid = str(inspection.get("class_uid", "")).replace("-", "").upper()
        if (
            observed_uid != PLUGIN_CLASS_UID
            or inspection.get("name") != PLUGIN_NAME
            or inspection.get("vendor") != PLUGIN_VENDOR
            or inspection.get("parameter_count") != len(PARAMETERS)
            or inspection.get("sdk_commit") != SDK_COMMIT
        ):
            raise RpcError(-32011, "loaded module is not the declared method fixture")

        self.plugin_path = plugin_path
        self.plugin_sha256 = sha256_path(plugin_path)
        return {"loaded": True}

    def unload_plugin(self) -> dict[str, Any]:
        self.plugin_path = None
        self.plugin_sha256 = None
        self.parameters = {
            int(item["index"]): float(item["default_value"]) for item in PARAMETERS
        }
        self.attempt_ids.clear()
        return {"unloaded": True}

    def get_identity(self) -> dict[str, Any]:
        if self.plugin_path is None or self.plugin_sha256 is None:
            raise RpcError(-32001, "no plugin is loaded")
        return {
            "host": {
                "protocol_version": "vst-bench-host-jsonrpc/1",
                "source_repository": SOURCE_REPOSITORY,
                "source_commit": self.source_commit,
                "source_dirty": self.source_dirty,
                **({"source_kind": "archive", "source_archive": self.source_archive}
                   if self.source_archive else {}),
                "executable_sha256": self.server_sha256,
                "build_configuration": (
                    f"Release;vst3sdk={SDK_COMMIT};"
                    f"runner_sha256={self.runner_sha256}"
                ),
            },
            "plugin": {
                "path": str(self.plugin_path),
                "sha256": self.plugin_sha256,
                "format": "VST3",
                "name": PLUGIN_NAME,
                "vendor": PLUGIN_VENDOR,
                "identifier": PLUGIN_IDENTIFIER,
                "version": PLUGIN_VERSION,
                "rights_class": "private-self-authored-no-distribution-grant",
            },
            "capabilities": {
                "deterministic_reset": True,
                "parameter_readback": True,
                "attempt_id_validation": True,
                "reset_policy": RESET_POLICY,
            },
        }

    def list_parameters(self) -> dict[str, Any]:
        return {"parameters": [dict(item) for item in PARAMETERS]}

    def set_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        values = params.get("parameters")
        if not isinstance(values, list) or not values:
            raise RpcError(-32602, "parameters must be a non-empty list")
        updates: dict[int, float] = {}
        for entry in values:
            if not isinstance(entry, dict):
                raise RpcError(-32602, "parameter entry must be an object")
            try:
                index = int(entry["index"])
                value = float(entry["value"])
            except (KeyError, TypeError, ValueError) as error:
                raise RpcError(-32602, "parameter entry is malformed") from error
            if index not in self.parameters:
                raise RpcError(-32602, f"unknown parameter index: {index}")
            if not 0.0 <= value <= 1.0:
                raise RpcError(-32602, f"parameter {index} is outside [0, 1]")
            if index in updates:
                raise RpcError(-32602, f"duplicate parameter index: {index}")
            updates[index] = value
        self.parameters.update(updates)
        return {
            "parameters": [
                {"index": index, "value": self.parameters[index]}
                for index in sorted(updates)
            ]
        }

    def render_audio(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.plugin_path is None:
            raise RpcError(-32001, "no plugin is loaded")
        try:
            num_samples = int(params["num_samples"])
            output_path = Path(params["output_path"]).resolve()
        except (KeyError, TypeError, ValueError) as error:
            raise RpcError(-32602, "render request is malformed") from error
        midi_events = params.get("midi_events")
        if num_samples < 1 or not isinstance(midi_events, list):
            raise RpcError(-32602, "num_samples and midi_events are required")
        if not output_path.parent.is_dir():
            raise RpcError(-32602, "output parent directory does not exist")
        temporary_root = Path(tempfile.gettempdir()).resolve()
        try:
            output_path.relative_to(temporary_root)
        except ValueError as error:
            raise RpcError(
                -32602, "output path must be under the system temporary directory"
            ) from error
        if output_path.exists():
            raise RpcError(-32602, "output path already exists")

        attempt_id = params.get("attempt_id", output_path.stem)
        if not isinstance(attempt_id, str) or not attempt_id:
            raise RpcError(-32602, "attempt_id must be a non-empty string")
        if attempt_id in self.attempt_ids:
            raise RpcError(-32022, f"duplicate attempt ID: {attempt_id}")
        self.attempt_ids.add(attempt_id)
        started_at = observed_at()

        lines = ["MFIXTURE/1", "sample_rate 44100", f"num_samples {num_samples}"]
        for index in sorted(self.parameters):
            lines.append(f"param {index} {self.parameters[index]:.17g}")
        for entry in midi_events:
            if not isinstance(entry, dict):
                raise RpcError(-32602, "MIDI event must be an object")
            event_type = entry.get("type")
            if event_type not in {"note_on", "note_off"}:
                raise RpcError(-32602, f"unsupported MIDI event type: {event_type}")
            try:
                offset = int(entry["sample_position"])
                channel = int(entry.get("channel", 1)) - 1
                pitch = int(entry["note"])
                velocity = float(entry.get("velocity", 0.0))
            except (KeyError, TypeError, ValueError) as error:
                raise RpcError(-32602, "MIDI event is malformed") from error
            if (
                not 0 <= offset < num_samples
                or not 0 <= channel <= 15
                or not 0 <= pitch <= 127
                or not 0.0 <= velocity <= 1.0
            ):
                raise RpcError(-32602, "MIDI event value is out of range")
            lines.append(
                f"event {offset} {event_type} {channel} {pitch} {velocity:.17g}"
            )

        request_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="method_fixture_",
                suffix=".txt",
                delete=False,
            ) as request:
                request.write("\n".join(lines) + "\n")
                request_path = Path(request.name)
            result = self._runner_call(
                "render",
                str(self.plugin_path),
                str(request_path),
                str(output_path),
            )
        finally:
            if request_path is not None:
                request_path.unlink(missing_ok=True)

        if result.get("samples") != num_samples or not output_path.is_file():
            raise RpcError(
                -32020, "fixture runner did not produce the requested output"
            )
        actual = result.get("readback")
        if not isinstance(actual, list):
            raise RpcError(-32020, "fixture runner omitted parameter readback")
        validate_readback(self.parameters, actual)
        self._append_attempt(
            {
                "schema": "method-fixture.render-trace/v1",
                "attempt_id": attempt_id,
                "started_at_utc": started_at,
                "completed_at_utc": observed_at(),
                "outcome": "rendered",
                "stage": "render",
                "retry_count": 0,
                "midi_events_sha256": canonical_sha256(midi_events),
                "parameter_readback": [
                    {
                        "index": index,
                        "parameter_id": str(PARAMETERS[index]["parameter_id"]),
                        "value": float(actual[index]),
                    }
                    for index in range(len(PARAMETERS))
                ],
                "reset_policy": RESET_POLICY,
                "output": {
                    "name": output_path.name,
                    "bytes": output_path.stat().st_size,
                    "sha256": sha256_file(output_path),
                },
            }
        )
        return {
            "output_path": str(output_path),
            "num_samples": num_samples,
            "sha256": sha256_file(output_path),
        }

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "ping":
            return {"ok": True}
        if method == "load_plugin":
            return self.load_plugin(params)
        if method == "unload_plugin":
            return self.unload_plugin()
        if method == "get_identity":
            return self.get_identity()
        if method == "list_parameters":
            return self.list_parameters()
        if method == "set_parameters":
            return self.set_parameters(params)
        if method == "render_audio":
            return self.render_audio(params)
        raise RpcError(-32601, f"method not found: {method}")


def make_handler(host: FixtureHost):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            request_id: Any = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 1024 * 1024:
                    raise RpcError(-32600, "invalid request size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("jsonrpc") != "2.0"
                ):
                    raise RpcError(-32600, "invalid JSON-RPC request")
                request_id = payload.get("id")
                method = payload.get("method")
                params = payload.get("params", {})
                if not isinstance(method, str) or not isinstance(params, dict):
                    raise RpcError(-32600, "invalid JSON-RPC method or params")
                response = {
                    "jsonrpc": "2.0",
                    "result": host.dispatch(method, params),
                    "id": request_id,
                }
            except RpcError as error:
                response = {
                    "jsonrpc": "2.0",
                    "error": {"code": error.code, "message": error.message},
                    "id": request_id,
                }
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "parse error"},
                    "id": request_id,
                }

            encoded = json.dumps(response, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--attempt-trace", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    host = FixtureHost(args.runner, args.repo_root, args.attempt_trace)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(host))
    print(f"READY 127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
