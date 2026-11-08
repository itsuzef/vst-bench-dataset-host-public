#!/usr/bin/env python3
"""Check installed versions against the companion's hashed, exact requirements lock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from provenance_gate import GateError, dependency_lock_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--expected-sha256")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        identity = dependency_lock_identity(
            args.dependency_lock, args.python, args.expected_sha256
        )
    except GateError as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    if args.json:
        print(json.dumps(identity, indent=2, sort_keys=True))
    else:
        print(f"PASS: installed versions match lock ({len(identity['items'])} distributions)")


if __name__ == "__main__":
    main()
