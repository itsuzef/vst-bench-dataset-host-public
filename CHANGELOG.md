# Changelog

## Unreleased

- Compare every active exact dependency pin with the selected interpreter's
  installed version before release validation and manifest finalization.
- Add a standalone environment check and record its result in companion manifests.
- Reject changed or missing dependencies even when the lockfile itself is unchanged.

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
