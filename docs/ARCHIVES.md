# Source archives without public development history

This is an additional release route. Development repositories may remain private.
Nothing in this document authorizes an upload, repository visibility change, tag,
release, deposit, manuscript submission, or publication.

## Prepare locally

From a development checkout of the companion:

```
python3 -B scripts/export_archives.py \
  --package-repo /absolute/path/to/vst-bench-ml \
  --output /absolute/new/outside-source/directory
```

`--allow-dirty-host` permits an explicitly labeled local candidate while adapting
the host; it does not claim those changes were committed or independently reviewed.
The package must remain clean at the baseline commit locked by the fixture.

The exporter uses explicit file allowlists. It excludes Git history, CI workflows,
the five quarantined package paths, internal host-contract/incident/rights-decision
notes, binaries, SDK trees, generated audio and validation outputs. It replaces
the host README with standalone archive instructions. The package build inputs
and wheel expectations remain unchanged. The companion's archived expectation
file pins the exact package source manifest instead of demanding Git metadata.

## Source identity and trust

Each root contains `SOURCE-ARCHIVE.json`: project, upstream commit label, sorted
paths, byte counts, SHA-256 file digests, and the canonical file-list digest.
The manifest does not hash itself; its exact-byte SHA-256 is recorded externally
in the receipt and, for the package, in the companion expectations.

Verification rejects changed, missing, additional, unsafe, duplicate, and symlink
entries. Keep source trees read-only in practice: use Python `-B` or
`PYTHONDONTWRITEBYTECODE=1`, disable pytest caches, and put builds, environments,
distributions, and validation results outside them. Cache files are not exempt.

An archive records `source_kind: archive` and `source_archive` rather than claiming
a checked-out Git commit/tree or Git cleanliness. The host's protocol-compatible
`source_commit` becomes `archive-sha256:<files_sha256>`. Its `source_dirty: false`
means the files matched the declared archive, not that Git was consulted. The
upstream commit identifies lineage only; filtered/adapted contents are identified
by the snapshot hashes. Mixed `.git` and archive roots are rejected. Git mode keeps
the existing clean-tree, commit/tree, wheel, installed RECORD, dependency, MIDI,
readback/reset, deterministic-output, and negative-case checks.

These hashes establish consistency, not publisher authentication. Before running
downloaded code, obtain and compare ZIP hashes from a trusted release receipt or
archive record. A malicious party able to replace code and every trust anchor can
replace the verifier as well. No signature/authentication guarantee is claimed.

## Release gate for this route

1. Review exact source allowlists and standalone instructions.
2. Export twice; compare ZIP hashes, inspect contents, and re-extract into new roots.
3. Build from the extracted sources and run unit/lint checks plus the full existing
   two-run/eight-output/twelve-negative-case validation against the locked wheel.
4. Record source ZIP/manifest hashes, wheel and lock identities, toolchain and
   validation results. Do not substitute a Git-only CI result for archive testing.
5. Obtain explicit approval of the exact archives before depositing or publishing.

This gate replaces the public-GitHub workflow prerequisite for an archive-only
release; the old GitHub route remains documented in `docs/RELEASE.md`. The exporter
does not alter either repository or invent DOI, publication date, or acceptance.
