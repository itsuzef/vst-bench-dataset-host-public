# Reproduce release validation

The validator pins the package commit and wheel in `fixtures/expected-output.json`.
Use the package commit specified there; a newer package checkout is a different
source identity even when its rendering code is unchanged. Keep both checkouts
clean and all environments/builds/results outside them.

## Check installed dependency versions

The exact validation workflow compares every active lockfile version with the
distribution metadata in the interpreter selected by `--python`, including SciPy
and the other transitive dependencies. A mismatch or missing package stops
validation before rendering. The same comparison runs before finalization and is
recorded in `identities.dependencies.lock_verification`.

To check the environment without building or rendering:

```sh
python scripts/check_environment.py \
  --dependency-lock ../vst-bench-ml-public/requirements/lock.txt \
  --python /absolute/path/to/validation-venv/bin/python
```

For example, SciPy 1.18.1 against a lock requiring 1.15.3 produces
`FAIL: dependency lock mismatch: scipy: expected 1.15.3, installed 1.18.1` and
exits nonzero. A matching environment reports the number of checked distributions.
The historical lock contains 19 distributions. Its checksum alone does not show
that those versions are installed.

The checker accepts exact `name==version` entries with SHA-256 archive hashes,
continuation lines, and environment markers evaluated by the selected interpreter.
It rejects ranges, wildcard pins, URLs, nested requirements, and unsupported
options. The `packaging` tool must be installed in the selected interpreter; it
is included in the historical lock. Additional packages outside the lock are
allowed.

This checks version metadata, not the contents or origin of every dependency.
Install into a fresh environment with `pip --require-hashes` to check downloaded
archive hashes. Native-library hashes are recorded separately. Offline dataset
verification checks stored artifacts and does not require the original environment.

## Run complete release validation

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
provenance, installed package payload and RECORD, lockfile identity, installed
versions of every active locked distribution, recorded native-library identities,
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
