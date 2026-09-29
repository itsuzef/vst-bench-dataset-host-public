# Local host protocol

The host implements JSON-RPC 2.0 over HTTP POST at `127.0.0.1`. It does not
listen on non-loopback interfaces.

## Lifecycle

1. `ping`
2. `load_plugin {"plugin_path": "/absolute/.../MethodFixture.vst3"}`
3. `get_identity`
4. zero or more `set_parameters`
5. one or more `render_audio`
6. `unload_plugin` or host-process termination

A second `load_plugin` fails with `-32002`. The loaded module must expose the
locked fixture class UID, name, vendor, six controller parameters, and pinned
SDK identity. Any mismatch fails with `-32011`.

## Identity

`get_identity` binds:

- protocol version;
- source repository label, source revision, and dirty flag;
- server and runner SHA-256 values;
- build mode and pinned SDK commit;
- canonical plugin path and aggregate bundle SHA-256;
- plugin format, name, vendor, stable identifier, version, and rights class;
- deterministic-reset, parameter-readback, and attempt-ID capabilities.

For a Git checkout the revision is its commit. In archive mode, `source_kind`
is `archive`, `source_archive` binds the manifest and complete file-list hashes,
and the revision is `archive-sha256:<files_sha256>`; the upstream commit is only
a lineage label. `source_dirty: false` records a successful exact-file check,
not an observed Git state. See [ARCHIVES.md](ARCHIVES.md).

Each validation manifest additionally binds the exact installed
`vst-bench-ml` wheel to either its repository commit/tree/clean state or its
pinned source-archive identity, plus distribution, version, filename, archive SHA-256, validated wheel
RECORD, and payload identity. Every wheel payload file and its RECORD row must
match the installed distribution, and the imported `vst_bench_ml/__init__.py`
must be owned by that distribution and match the wheel. The manifest also binds
the complete dependency-lock SHA-256; installed native-library identities; the
fixed MIDI-bank SHA-256; ordered parameter definitions and per-attempt
readback; the literal reset policy; and explicit requested, rendered, kept,
dropped, and failed counts.

## Parameters and rendering

`set_parameters` accepts unique `{"index", "value"}` objects. Values must be
normalized finite numbers in `[0, 1]`; unknown, duplicate, and out-of-range
parameters fail with `-32602`.

`render_audio` accepts `num_samples`, a new absolute `output_path` under
the system temporary directory, and the fixed orchestration MIDI-event objects. The observed protocol supports
44.1 kHz. The server serializes all six current parameter values to the offline
runner. The runner loads the VST3 binary, creates a fresh component/controller,
configures stereo 32-bit offline processing, resets on activation, applies
parameter queues, renders MIDI events, and writes deterministic 16-bit stereo
WAV. Controller readback is compared with the requested normalized values;
mismatch fails with `-32021`.

An optional nonempty `attempt_id` is accepted for direct host clients; otherwise
the stable output stem is used. Reuse fails with `-32022`. During validation,
the host appends one fsynced trace per completed render to an external trace.
On the successful fixture path, finalization requires an empty core failure
ledger and appends exactly one terminal `kept` entry per host trace to the
dataset's `failures.jsonl`, then binds its byte
count and SHA-256 into the sealed manifest. Entries carry stable attempt,
plan, patch, and signal IDs; UTC start/end; outcome, stage, code, retry count;
host/plugin/parameter identities; MIDI identity; all-six-parameter readback;
reset and normalization paths; partial artifacts; and final disposition.

Negative cases are appended to the same ledger with evidence digests. Resume
may append but never erase or rewrite prior events. Duplicate IDs, sequence
gaps, artifact/hash mismatch, missing render entries, record/count mismatch,
or missing negative-case evidence fail closed. Validation explicitly rejects an
actual sdist renamed `.whl`, an unrelated file renamed `.whl`, and a
structurally valid wrong wheel. It also reseals a copy after deleting one
attempt and proves that the incomplete ledger is still rejected.

This protocol and its observed outputs establish behavior only for the pinned
private stack. They do not establish public release rights or cross-machine
audio identity.
