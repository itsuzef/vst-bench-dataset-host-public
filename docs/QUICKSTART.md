# Generate your first dataset

This walkthrough targets macOS arm64 and Python 3.12. Install Xcode command-line
tools, CMake >=3.25, and Git first. Use an empty working directory. Commands are
for a POSIX shell and keep environments, builds, and outputs outside source roots.

## 1. Get the sources and install the Python package

```sh
mkdir vst-bench-example
cd vst-bench-example
WORK_DIR="$PWD"
git clone https://github.com/itsuzef/vst-bench-dataset-host-public.git
HOST_DIR="$WORK_DIR/vst-bench-dataset-host-public"
python3.12 -m venv "$WORK_DIR/venv"
source "$WORK_DIR/venv/bin/activate"
python -m pip install vst-bench-ml==0.1.1
```

Alternatively, install from the public package checkout:

```sh
git clone https://github.com/itsuzef/vst-bench-ml-public.git
python -m pip install "$WORK_DIR/vst-bench-ml-public"
```

For an exact release, check out the matching `v0.1.1` tag.
Ordinary pip installation resolves transitive dependencies. For the full locked
validation environment and its exact expected hashes, follow [VALIDATION.md](VALIDATION.md).

## 2. Build the host and instrument

```sh
sh "$HOST_DIR/scripts/build.sh" "$WORK_DIR/build"
```

The build downloads the pinned VST3 SDK. Expected macOS paths:

- `$WORK_DIR/build/method_fixture_runner`
- `$WORK_DIR/build/VST3/Release/MethodFixture.vst3`

## 3. Start the host

In the same terminal:

```sh
python -B "$HOST_DIR/host/server.py" \
  --runner "$WORK_DIR/build/method_fixture_runner" \
  --repo-root "$HOST_DIR" --port 8765
```

Wait for `READY 127.0.0.1:8765`. Leave this terminal running.

## 4. Render in a second terminal

Set the absolute working directory you created in step 1, then activate its environment:

```sh
WORK_DIR="/absolute/path/to/vst-bench-example"
HOST_DIR="$WORK_DIR/vst-bench-dataset-host-public"
source "$WORK_DIR/venv/bin/activate"
vst-bench-ml render \
  --plugin "$WORK_DIR/build/VST3/Release/MethodFixture.vst3" \
  --param-manifest "$HOST_DIR/fixtures/parameter-manifest.json" \
  --port 8765 --n 4 --signals sus_c3,gate_c2 --signal-mode all \
  --seconds 0.5 --sr 44100 --seed-label bon-369-v1 --keep-bad \
  --out "$WORK_DIR/output"
vst-bench-ml verify --manifest "$WORK_DIR/output/manifest.json"
```

Expected summary: `verified: 8 kept, 0 dropped, 0 failures`. The output directory
contains `manifest.json`, `records.jsonl`, `failures.jsonl`, and eight `audio/*.npz`
files. `--keep-bad` retains intentionally silent fixture settings; it is not an
audio-quality recommendation. See the [output guide](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/USAGE.md).

Stop the server with Ctrl-C. Restart it before another render and choose a new
output directory. The current client can overwrite files in an existing output directory.

## What this demonstrates

This is the normal generate-and-verify workflow. It checks stored artifact integrity.
The [release validation](VALIDATION.md) additionally compares two runs, checks exact
expected hashes, binds the installed wheel and complete environment, and exercises
negative cases. That evidence is scoped to the tested environment.
