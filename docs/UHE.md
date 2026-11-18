# Native Podolski and Triple Cheese example

Bounded macOS profiles: Podolski VST3 V1.2.3 and TripleCheese VST3 V1.3.0,
u-he revision 12092. Install each plugin separately under its vendor's terms.
No binaries, presets, assets or generated plugin audio are distributed here.
Use the package environment and native Release build described in README.

The native runner initializes through the SDK PlugProvider (as used by
Vital); inspection succeeds for both instruments and enumerates their controls.
Both profiles discover and bind **Output, native ID 0**, rather than treating a
package index as a plugin parameter ID. Name, class UID, vendor and bundle
version are checked. These are reported/hashed identities, not authentication.

From this repository, with vst-bench-ml installed and the runner built:

```sh
python scripts/exercise_uhe.py --profile podolski \
  --plugin /Library/Audio/Plug-Ins/VST3/Podolski.vst3 \
  --runner /absolute/path/to/method_fixture_runner --out /new/path/podolski
python scripts/exercise_uhe.py --profile triplecheese \
  --plugin /Library/Audio/Plug-Ins/VST3/TripleCheese.vst3 \
  --runner /absolute/path/to/method_fixture_runner --out /new/path/triplecheese
python scripts/verify_uhe.py podolski /new/path/podolski/run-1/dataset \
  /new/path/podolski/run-1/trace.jsonl /new/path/podolski/run-1/plan.json
```

Each command requires a new output path. It invokes the package CLI in two
fresh Python processes, each hosting three renders in fresh native runner
processes/plugin instances. The explicitly substituted fixed plan sets Output
to 0.25, 0.5 and 0.75; manifest RNG configuration is **not** the origin of this
plan. This is not RNG replay. MIDI is `sus_c3`, one second, 44100 Hz, all mode;
default plugin state/buses, silent audio input, PCM16 raw WAV capture, then the
package's normal QC/normalization/NPZ pipeline. Readback must match every value.
Only this one control is supported per instrument. Other controls remain at
their initial plugin settings, not explicitly saved/restored preset state.

These builds return `kNotImplemented` from `setProcessing(true)`, as does the
SDK AudioEffect base implementation. The UHE/1 path tolerates exactly that
return in addition to success; component activation and process still must
succeed. Fixture/Vital paths retain their strict success requirement.
The runner records the result code.

The driver measures raw WAV/PCM equality, maximum and RMS sample difference,
raw RMS per setting, and stored NPZ byte equality. On Newton's macOS 27.2 arm64,
Python 3.12.13/M4 Max run, all six corresponding raw/stored pairs were equal
(maximum/RMS differences zero); raw RMS changed across the three settings.
It also rejects a changed stored artifact and a missing external trace entry.
The `deterministic_reset` RPC capability describes fresh-instance reset, **not**
a universal guarantee of deterministic audio.

The external trace and exact-plan checker does not reseal the dataset or
authenticate origin. These are all-kept tests, not fixture finalization or
mixed-outcome coverage for these plugins. No independent human reproduction,
other versions/platforms, preset coverage, or acoustic label validation claimed.
Results include hashes of local raw WAVs, datasets, traces, calls and logs.
