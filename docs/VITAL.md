# Vital 1.0.6 on macOS arm64

Use `revision/installation-compatibility`, a separately installed Vital VST3,
and the revised vst-bench-ml package. Build as in QUICKSTART.md. The current
profile discovers and checks these exact native IDs by name:

| Package index | Name | Native ID | Normalized range |
| --- | --- | --- | --- |
| 0 | Volume | 51696 | 0–1 |
| 1 | Oscillator 1 Pan | 50800 | 0–1 |
| 2 | Voice Transpose | 54455 | 0–1, 96 steps |

Each render starts a fresh process and plugin instance; all other controls remain
at startup settings. Default audio buses, silent input, 44100 Hz, one second,
`sus_c3`, all-signals mode were tested on macOS 27.2 arm64, Vital 1.0.6
(class ABCDEF019182FAEB4F70656E5669616C). This is not arbitrary plugin support.
The old Volume-only manifest and historical traces remain historical examples;
use `fixtures/vital-1.0.6-controls.json` for the current three-control profile.

Start the host (new trace filename), then run the client in another terminal:

```sh
python host/server.py --repo-root . --runner /path/to/method_fixture_runner --attempt-trace trace.jsonl
vst-bench-ml render --plugin "$HOME/Library/Audio/Plug-Ins/VST3/Vital.vst3" --param-manifest fixtures/vital-1.0.6-controls.json --out dataset --n 4 --signals sus_c3 --signal-mode all --sr 44100 --seconds 1 --seed-label vital-probe
python scripts/verify_vital.py dataset trace.jsonl
```

For mixed outcomes the checker additionally requires the exact external plan
(`--plan plan.json`, JSON `[[tier, {index: normalized_value}], ...]`). It checks
its digest/count against the core manifest, one terminal record or event per
planned observation, and matching requested parameters/readbacks for each native
render. It supports render-stage failures only, not set-parameter failures,
process failures after successful rendering, or unattempted suffixes after abort.
Missing, duplicate and unexpected attempts fail closed.

Since package 0.2.0 the core records one outcome per planned attempt itself
(`attempts.jsonl`, manifest schema v2) and can compare it with this host's trace,
including the hash of each WAV the host wrote:

```sh
vst-bench-ml verify --manifest dataset/manifest.json --host-trace trace.jsonl
```

That core check covers kept, dropped, failed and unattempted renders for any
plugin. `verify_vital.py` remains the check of requested parameters against
native readbacks, which the core does not see.

To reproduce the bounded regression with explicit failure injection:

```sh
python scripts/exercise_vital.py --plugin "$HOME/Library/Audio/Plug-Ins/VST3/Vital.vst3" --runner /path/to/method_fixture_runner --out /new/evidence-directory
```

This uses HTTP JSON-RPC, native rendering, and a hand-specified four-patch plan
(not an RNG test). The all-kept run keeps four; the mixed run keeps two, drops
one naturally silent zero-Volume render, and injects a runner RPC error on the
last attempt. The failure is a test double, not an observed Vital failure or
crash. Five negative trace cases per run test omission, duplication, readback,
plan correspondence and outcome tampering. The harness retains manifests,
records, events, traces, plans and artifact hashes. It never overwrites a run.

The external trace/plan are consistency inputs, not authenticated evidence.
Keep their hashes independently if substitution matters. The check does not
reseal a dataset, prove acoustic parameter semantics, or establish independent
human reproduction, bit-identical repeats for the new controls, native support
for Podolski/Triple Cheese, or complete coverage of Vital. The historical
Volume-only repeat evidence is distinct. Do not apply the fixture CSV labels to
Vital. Vital and its assets remain under their own terms; no fixture-output
licence is granted to them.
