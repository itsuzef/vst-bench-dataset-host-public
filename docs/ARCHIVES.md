# Source archives

Normal use starts from the public Git checkout and [quickstart](QUICKSTART.md).
The historical 0.1.0 Zenodo archives remain sealed, standalone source snapshots.

To prepare a sealed snapshot of a validated Git release:

```sh
python3.12 -B scripts/export_archives.py \
  --package-repo /absolute/path/to/vst-bench-ml-public \
  --output /absolute/new/export-directory
```

The package commit must match `fixtures/expected-output.json`, and both source
trees must be clean. The exporter copies an explicit allowlist, writes source
manifests, and substitutes the archive package identity into host expectations.
It does not publish anything. Its Python requirement is 3.11+ (`tomllib`); the
complete documented environment uses Python 3.12.

Git metadata and `SOURCE-ARCHIVE.json` are mutually exclusive at a source root.
Archive checks reject extra/changed/missing files, including caches. Run Python
with `-B`, disable pytest caches, and keep build/environment/results elsewhere.
The manifest hash establishes source consistency, not publisher authentication.
See [archive consumer instructions](ARCHIVE-README.md).
