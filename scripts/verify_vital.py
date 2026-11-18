#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify a complete all-kept Vital Volume run and its companion trace."""
import argparse
import json
import math
from pathlib import Path

from vst_bench_ml.provenance import verify_manifest


def verify(dataset: Path, trace: Path) -> None:
    manifest_path = dataset / "manifest.json"
    manifest = verify_manifest(manifest_path)
    request = manifest["request"]
    plugin = manifest["identities"]["plugin"]
    if (plugin["identifier"], plugin["version"]) != ("ABCDEF019182FAEB4F70656E5669616C", "1.0.6"):
        raise ValueError("unexpected Vital identity")
    if request["signal_mode"] != "all":
        raise ValueError("expected all signals per patch")
    ids = {f"p{i:06d}_{signal}" for i in range(request["requested_patches"])
           for signal in request["signals"]}
    if not ids or manifest["outcomes"] != {"kept": len(ids), "dropped": 0, "failures": 0}:
        raise ValueError("expected a complete all-kept dataset")
    entries = [json.loads(line) for line in trace.read_text().splitlines()]
    by_id = {entry["attempt_id"]: entry for entry in entries}
    if set(by_id) != ids or len(entries) != len(ids):
        raise ValueError("missing, duplicate or unexpected attempt")
    records = dataset / manifest["artifacts"]["records"]["path"]
    for line in records.read_text().splitlines():
        record = json.loads(line)
        attempt = record["patch_id"] + "_" + record["signal"]
        entry = by_id.pop(attempt)
        rb, = entry["parameter_readback"]
        if (entry["schema"] != "vital.render-trace/v1" or entry["outcome"] != "rendered"
                or entry["output"]["name"] != attempt + ".wav"
                or rb["parameter_id"] != "51696" or rb["index"] != 0
                or not math.isclose(rb["value"], record["param_vector"]["0"],
                                    abs_tol=5.1e-7, rel_tol=0)):
            raise ValueError("trace disagrees with record " + attempt)
    if by_id:
        raise ValueError("missing records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    verify(args.dataset, args.trace)
    print("Verified Vital dataset and complete attempt inventory.")
