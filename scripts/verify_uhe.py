#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline external trace/plan check for the bounded native u-he profiles."""
import argparse
from pathlib import Path
from exercise_uhe import PROFILES, verify

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=PROFILES)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('trace', type=Path)
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    verify(Path(__file__).resolve().parents[1], args.dataset, args.trace, args.plan, args.profile)
    print('Verified dataset against external u-he trace and exact plan.')
