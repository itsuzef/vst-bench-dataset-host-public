# Changelog

## 0.2.0

- Reject unlisted dataset files, symbolic links, and non-regular entries during verification.
- Compare every active exact dependency pin with the selected interpreter's
  installed version before release validation and manifest finalization.
- Add a standalone environment check and record its result in companion manifests.
- Reject changed or missing dependencies even when the lockfile itself is unchanged.
- Host can write an attempt trace outside the dataset (`--attempt-trace`), including
  the hash of each audio file it wrote.
- Native Vital 1.0.6 profile: three controls, all-kept and mixed-outcome runs, with
  a checker for the dataset, trace and plan ([VITAL.md](docs/VITAL.md)).
- Native Podolski 1.2.3 and Triple Cheese 1.3.0 profiles for the Output control
  ([UHE.md](docs/UHE.md)).
- `get_identity` states the plugin digest algorithm, so vst-bench-ml 0.2.0 can
  compare it with its own digest of the plugin files.
- Exact-hash fixture conformance stays pinned to the vst-bench-ml 0.1.1 identity
  and schema v1 manifests. Datasets written by 0.2.0 are checked by the core verifier.
- MIT SPDX headers on first-party source; pinned VST3 SDK licence identified.

## 0.1.1

- Introduce a public Git source repository derived from the published archive.
- Add a complete installation/render/verification walkthrough and user documentation.
- Use the public host repository URL in recorded source identity.
- Adapt source export and package identity pins for the new public release.
- Preserve native fixture/runner implementation, MIDI inputs, and expected audio hashes.
  The fixture's embedded legacy plugin version remains unchanged; the repository
  release version identifies the documentation and integration changes.

## 0.1.0 — 2026-09-23

Published archive: https://doi.org/10.5281/zenodo.22924073.
The documented README correction is preserved in the initial public import.
