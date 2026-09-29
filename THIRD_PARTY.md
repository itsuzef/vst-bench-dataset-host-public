# Third-party build and runtime identities

Nothing listed here is vendored, relicensed, or authorized for redistribution
by this repository.

## VST3 SDK

- Upstream: https://github.com/steinbergmedia/vst3sdk
- Pinned root commit: `3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96`
- Required submodules:
  - `base`: `fcf9da0bd27a16f7f03773a3a39822f28f5c8477`
  - `cmake`: `054c9143cbb8d47fc4694e473f2ee3b4d951a8f5`
  - `pluginterfaces`: `4f547e8e102b47de4a8b8aaf343c73b700786372`
  - `public.sdk`: `586dc5e6c8012c3e4b01c79389375cbe96bdb1da`
- License authority: the upstream `LICENSE.txt` and license notices at the
  pinned identities.
- Use here: compile the self-authored VST3 fixture and offline runner.
- This repository contains no SDK source or binaries; users fetch the SDK
  themselves under its upstream licence.

## Separate orchestration checkout

The demonstration invokes `vst-bench-ml` from an explicit external path. It
does not copy or package that project. Its manifest records the loaded Python
source hashes, runtime identity, and direct dependency versions.
