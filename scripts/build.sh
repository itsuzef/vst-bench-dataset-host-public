#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: scripts/build.sh /absolute/outside-repository/build-dir" >&2
    exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
build_dir=$1
case "$build_dir" in
    /*) ;;
    *)
        echo "build directory must be absolute" >&2
        exit 2
        ;;
esac
case "$build_dir" in
    "$repo_dir"|"$repo_dir"/*)
        echo "build directory must be outside the source repository" >&2
        exit 2
        ;;
esac

cmake -S "$repo_dir" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DSMTG_CREATE_PLUGIN_LINK=OFF
cmake --build "$build_dir" --config Release \
    --target MethodFixture method_fixture_runner --parallel 4

find "$build_dir" -type d -name 'MethodFixture.vst3' -print
find "$build_dir" -type f -name 'method_fixture_runner' -print
