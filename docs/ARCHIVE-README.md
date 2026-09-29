# Sealed source snapshot

This is a source-archive export of vst-bench-dataset-host. See `CITATION.cff` for
its version and `docs/HISTORY.md` for public source lineage.

Follow `docs/QUICKSTART.md`, substituting the extracted host directory for the
Git clone. Install the matching package distribution or extracted package source.
For locked release validation, follow `docs/VALIDATION.md` using the matching
extracted package snapshot and wheel. Archive expectations identify source
manifests instead of Git commits.

Keep both extracted snapshots intact: no `.git`, generated caches, environments,
build outputs, or result files inside them. Run Python with `-B`. The verifier
rejects extra, missing, changed, or unsafe source paths.

Source is MIT; qualifying sample-free fixture outputs are CC0-1.0 under
`OUTPUT-LICENSE`. See `THIRD_PARTY.md` for external component terms. Generated
audio, SDK source, and plugin binaries are not included.
