# Vital 1.0.6 on macOS arm64

Use the revised `revision/installation-compatibility` source checkout (the historical fixture-only release tag does not include this profile). Install the Vital VST3 instrument separately. Build the companion runner as in QUICKSTART.md and install the revision of vst-bench-ml. The Vital profile discovers the Volume control by name and binds its native ID (51696) to package index 0. Each render loads a fresh instance with all other controls at startup settings. The profile uses the instrument's default audio bus arrangement and silent input. Its tested rate is 44100 Hz.

Start the server from the companion checkout, using a new trace filename:

```sh
python host/server.py --repo-root . --runner /path/to/method_fixture_runner --attempt-trace trace.jsonl
```

Run the client from the same checkout, supplying a new output directory:

```sh
vst-bench-ml render --plugin "$HOME/Library/Audio/Plug-Ins/VST3/Vital.vst3" --param-manifest fixtures/vital-1.0.6-volume.json --out dataset --n 2 --signals sus_c3 --signal-mode all --sr 44100 --seconds 1 --seed-label vital-probe
python scripts/verify_vital.py dataset trace.jsonl
```

The verifier checks core artifact integrity and requires one matching successful trace and readback per planned observation. Its scope is complete all-kept runs in all-signals mode. The trace is a separate comparison input. Retain its hash independently if later substitution matters. Fixture conformance has its own validation procedure. Vital and its assets are supplied by the user under their own terms.

On an intact all-kept run the checker prints `Verified Vital dataset and complete attempt inventory.` It does not reseal the dataset or add a kept-attempt ledger. Dropped/failed observations and other controls are outside its verified path. The fixture suite has separate finalization and conformance checks; core-only verification has no complete terminal-attempt ledger. Separate Pedalboard measurements of Podolski, Triple Cheese and Vital do not exercise this native path. These are agent-run checks on the documented stack, not independent human reproduction or general plugin support. The fixture-specific CSV exporter must not be used to label Vital records without changing its columns and parameter mapping.
