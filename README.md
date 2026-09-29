# vst-bench-dataset-host

A sample-free VST3 test instrument and offline host for demonstrating
[`vst-bench-ml`](https://github.com/itsuzef/vst-bench-ml-public) dataset generation and checking its provenance.
The fixture synthesizes waveforms from MIDI; no sample pack is needed.

## Start here

Follow the [complete installation and first-dataset walkthrough](docs/QUICKSTART.md).
It builds the host and fixture, starts the local server, generates eight outputs,
and verifies the stored dataset.

Requirements for the demonstrated environment: macOS arm64, Python 3.12,
CMake >=3.25, AppleClang/Xcode command-line tools, Git, and network access to fetch
the pinned VST3 SDK. Builds and generated results belong outside the source tree.

The host supports the supplied Method Fixture instrument. Supporting arbitrary
plugins requires another compatible host or additional implementation and validation.
The larger `vst-bench` MCP testing application is not needed for this workflow.

## Documentation

- [Quickstart](docs/QUICKSTART.md): build, start, render, verify.
- [Validation](docs/VALIDATION.md): reproduce the locked release checks.
- [Host protocol](docs/PROTOCOL.md): identities, reset, parameter readback, rendering.
- [Source archives](docs/ARCHIVES.md) and [public history](docs/HISTORY.md).
- [Contributing](CONTRIBUTING.md), [release checks](docs/RELEASE.md), and [issues](https://github.com/itsuzef/vst-bench-dataset-host-public/issues).

The fixture has six parameters: gain, tone, waveform, octave, enabled, and a
control-only parameter. Definitions are in `fixtures/parameter-manifest.json`;
MIDI inputs and expected output hashes are in `fixtures/`.

## Licence and citation

Source is MIT. `OUTPUT-LICENSE` dedicates qualifying sample-free generated fixture
outputs under CC0-1.0. Third-party components retain their own terms; see
[THIRD_PARTY.md](THIRD_PARTY.md). This repository contains no SDK source, binaries,
or generated audio.

The [0.1.0 Zenodo archive](https://doi.org/10.5281/zenodo.22924073) remains available.
Use the exact version and commit for later releases; see [CITATION.cff](CITATION.cff).
Output identity is limited to tested pinned environments, and the fixture does
not establish scientific suitability or representativeness of other plugins.
