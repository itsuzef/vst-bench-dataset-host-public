# Reproduce release validation

The validator pins the package commit and wheel in `fixtures/expected-output.json`.
Use the package commit specified there; a newer package checkout is a different
source identity even when its rendering code is unchanged. Keep both checkouts
clean and all environments/builds/results outside them.

From a working directory containing sibling `vst-bench-ml-public` and
`vst-bench-dataset-host-public` clones:

```sh
WORK_DIR="$PWD"
PACKAGE_DIR="$WORK_DIR/vst-bench-ml-public"
HOST_DIR="$WORK_DIR/vst-bench-dataset-host-public"
python3.12 -m venv "$WORK_DIR/validation-venv"
source "$WORK_DIR/validation-venv/bin/activate"
python -m pip install --require-hashes -r "$PACKAGE_DIR/requirements/lock.txt"
python -m pip install build
python -m build "$PACKAGE_DIR" --outdir "$WORK_DIR/dist"
python -m pip install --no-deps "$WORK_DIR/dist/vst_bench_ml-0.1.1-py3-none-any.whl"
sh "$HOST_DIR/scripts/build.sh" "$WORK_DIR/build"
python -B "$HOST_DIR/scripts/validate.py" \
  --build-dir "$WORK_DIR/build" --package-repo "$PACKAGE_DIR" \
  --package-wheel "$WORK_DIR/dist/vst_bench_ml-0.1.1-py3-none-any.whl" \
  --package-sdist "$WORK_DIR/dist/vst_bench_ml-0.1.1.tar.gz" \
  --dependency-lock "$PACKAGE_DIR/requirements/lock.txt" \
  --python "$WORK_DIR/validation-venv/bin/python" \
  --work-dir "$WORK_DIR/validation-results"
```

The result path must not already exist. Expected checks cover exact source/wheel
provenance, installed payload and RECORD, the dependency lock and native libraries,
parameter/MIDI/reset/readback identity, two runs with eight outputs each, the
stored output/plan hashes, and twelve negative cases. Preserve logs with the exact
commits and environment. A passing ordinary quickstart is not a substitute.

If starting from a PyPI wheel, download it, then install that local wheel path
with `--no-deps` after the lock. This allows the validator to bind the supplied
wheel to pip's direct-install provenance. An ordinary index install does not
provide that same local-wheel provenance.

The original 0.1.0 archives retain their original pins and instructions. The
new public release keeps historical output expectations and updates package
identity only after a new distribution is built. Do not overwrite audio hashes
to accommodate a failure.
