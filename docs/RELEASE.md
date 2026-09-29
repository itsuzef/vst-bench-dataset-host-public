# Release maintenance

1. Build and test a clean package commit and record its wheel and source identities.
2. Update only the package identity in `fixtures/expected-output.json` for that
   release; preserve MIDI, sampling, and output expectations unless a separately
   justified behavioral change is intended.
3. Commit host changes and run [VALIDATION.md](VALIDATION.md) against clean sources.
4. Record the host/package commits, distribution hashes, environment, and results.
5. Publish versioned source tags and the validated Python distribution. Preserve
   existing release tags and historical Zenodo archives.

Run host unit checks with the package's locked development environment:

```sh
python -B -m pytest -p no:cacheprovider -q tests
python -m ruff check --no-cache host scripts tests
```

Public development starts from the archive import described in [HISTORY.md](HISTORY.md).
