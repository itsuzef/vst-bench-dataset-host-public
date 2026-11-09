# Third-party build and runtime identities

The third-party SDK is not vendored or relicensed by this repository. Its
upstream license, rather than this repository, governs copying and redistribution.

## VST3 SDK

- Upstream: https://github.com/steinbergmedia/vst3sdk
- Pinned root commit: `3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96`
- Required submodules:
  - `base`: `fcf9da0bd27a16f7f03773a3a39822f28f5c8477`
  - `cmake`: `054c9143cbb8d47fc4694e473f2ee3b4d951a8f5`
  - `pluginterfaces`: `4f547e8e102b47de4a8b8aaf343c73b700786372`
  - `public.sdk`: `586dc5e6c8012c3e4b01c79389375cbe96bdb1da`
- License: **MIT** at the pinned root and all four required submodule revisions
  above (copyright 2026 Steinberg Media Technologies GmbH), checked 2026-11-09
  from those Git objects and byte-matched to upstream files at the same commits:
  - [SDK root LICENSE.txt](https://github.com/steinbergmedia/vst3sdk/blob/3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96/LICENSE.txt)
  - [base LICENSE.txt](https://github.com/steinbergmedia/vst3_base/blob/fcf9da0bd27a16f7f03773a3a39822f28f5c8477/LICENSE.txt)
  - [cmake LICENSE.txt](https://github.com/steinbergmedia/vst3_cmake/blob/054c9143cbb8d47fc4694e473f2ee3b4d951a8f5/LICENSE.txt)
  - [pluginterfaces LICENSE.txt](https://github.com/steinbergmedia/vst3_pluginterfaces/blob/4f547e8e102b47de4a8b8aaf343c73b700786372/LICENSE.txt)
  - [public.sdk LICENSE.txt](https://github.com/steinbergmedia/vst3_public_sdk/blob/586dc5e6c8012c3e4b01c79389375cbe96bdb1da/LICENSE.txt)
- MIT requires that the copyright and permission notice be included in copies
  or substantial portions of the software and provides the software without
  warranty. The linked license texts are authoritative; this is a summary.
- This statement concerns only the pinned revisions, not current upstream terms
  or every optional SDK component. It does not grant rights to third-party
  plugins, datasets, or Steinberg trademarks; consult the SDK's separate
  [usage guidelines](https://github.com/steinbergmedia/vst3sdk/blob/3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96/VST3_Usage_Guidelines.pdf)
  for branding. No SDK source or binaries are added here.
- Use here: compile the self-authored VST3 fixture and offline runner.
- This repository contains no SDK source or binaries; users fetch the SDK
  themselves under its upstream licence.

## Separate orchestration checkout

The demonstration invokes `vst-bench-ml` from an explicit external path. It
does not copy or package that project. Its manifest records the loaded Python
source hashes, runtime identity, and direct dependency versions.
