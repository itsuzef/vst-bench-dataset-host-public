# vst-bench-dataset-host — source archive

Self-authored, sample-free VST3 fixture, offline runner, and localhost JSON-RPC host
for `vst-bench-ml`. Development repositories may remain private; no clone, Git
history, or access to those repositories is needed to use these two source archives.
Git is still needed to retrieve the external pinned VST3 SDK during a native build.

## Published archives

Both source archives were published on Zenodo on 23 September 2026, version 0.1.0.
Development repositories remain private; download the source ZIPs from these records.

| Software | Record and download | DOI |
| --- | --- | --- |
| vst-bench-dataset-host | [Zenodo record](https://zenodo.org/records/22924073) | [10.5281/zenodo.22924073](https://doi.org/10.5281/zenodo.22924073) |
| vst-bench-ml | [Zenodo record](https://zenodo.org/records/22924036) | [10.5281/zenodo.22924036](https://doi.org/10.5281/zenodo.22924036) |

Source and checked-in fixture definitions: MIT (`LICENSE`). `OUTPUT-LICENSE`
applies only to sample-free outputs generated from this self-authored fixture's
mathematical waveforms, fixed MIDI inputs, and parameters. It does not cover the
SDK, third-party code/binaries, external plugins/audio, or product assets. No SDK
source, compiled binaries, or generated audio is bundled. See `THIRD_PARTY.md`.

## Setup and verification

Unpack both ZIPs into separate source roots. Verify the ZIP checksums against the
release receipt before running code. `SOURCE-ARCHIVE.json` inventories exact source
files; `docs/ARCHIVES.md` explains identities, restrictions, and release gates.
Use Python 3.12 on macOS arm64; other setups are not yet validated.

Set the following to absolute paths on your machine. Build, distribution,
environment and result directories must be outside both extracted source roots;
the results directory must not already exist.

```sh
PACKAGE_SRC=/absolute/path/to/vst-bench-ml-0.1.0
HOST_SRC=/absolute/path/to/vst-bench-dataset-host-0.1.0
BUILD_DIR=/absolute/outside-source/build
DIST_DIR=/absolute/outside-source/dist
VENV_DIR=/absolute/outside-source/venv
RESULTS_DIR=/absolute/outside-source/results
export PYTHONDONTWRITEBYTECODE=1

sh "$HOST_SRC/scripts/build.sh" "$BUILD_DIR"
uv build "$PACKAGE_SRC" --out-dir "$DIST_DIR"
uv venv "$VENV_DIR" --python 3.12
uv pip install --python "$VENV_DIR/bin/python" --require-hashes \
  -r "$PACKAGE_SRC/requirements/lock.txt"
uv pip install --python "$VENV_DIR/bin/python" --no-deps \
  "$DIST_DIR/vst_bench_ml-0.1.0-py3-none-any.whl"
(cd "$PACKAGE_SRC" && "$VENV_DIR/bin/python" -B -m pytest -p no:cacheprovider -q)
(cd "$HOST_SRC" && "$VENV_DIR/bin/python" -B -m pytest -p no:cacheprovider -q)
"$VENV_DIR/bin/python" -B "$HOST_SRC/scripts/validate.py" \
  --build-dir "$BUILD_DIR" --package-repo "$PACKAGE_SRC" \
  --package-wheel "$DIST_DIR/vst_bench_ml-0.1.0-py3-none-any.whl" \
  --package-sdist "$DIST_DIR/vst_bench_ml-0.1.0.tar.gz" \
  --dependency-lock "$PACKAGE_SRC/requirements/lock.txt" \
  --python "$VENV_DIR/bin/python" --work-dir "$RESULTS_DIR"
```

The full validator retains the baseline wheel/installed-payload, dependency-lock,
native-library, MIDI, reset/readback, two-run/eight-output, and twelve-negative-case
gates. Source archives additionally require complete file hashes and the package
manifest pinned by the companion. The origin URL is a lineage label, not a promise
of public GitHub access. Git-only developer instructions in the package's original
`docs/RELEASE.md` do not apply to this archive route.

Integrity and repeatability do not establish scientific suitability, perceptual
quality, cross-machine output identity, or publisher authentication. Cite the
version-specific Zenodo records above for the published archives; `CITATION.cff`
provides project citation metadata.
