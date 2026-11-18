#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Vital records and terminal events against an external native trace and plan.

This is consistency checking, not authentication. Mixed runs require the exact
plan as JSON [[tier, {index: normalized_value}], ...]. No resealing is performed.
"""
import argparse
import json
import math
from pathlib import Path

from vst_bench_ml.provenance import verify_manifest, sampling_plan_identity

CONTROL_IDS = {0: '51696', 1: '50800', 2: '54455'}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def verify(dataset: Path, trace: Path, plan_path: Path | None = None) -> None:
    manifest = verify_manifest(dataset / 'manifest.json')
    request = manifest['request']
    plugin = manifest['identities']['plugin']
    if (plugin['identifier'], plugin['version']) != ('ABCDEF019182FAEB4F70656E5669616C', '1.0.6'):
        raise ValueError('unexpected Vital identity')
    if request['signal_mode'] != 'all':
        raise ValueError('expected all signals per patch')
    plan = None
    if plan_path is not None:
        plan = [(tier, {int(k): v for k, v in vector.items()}) for tier, vector in json.loads(plan_path.read_text())]
        identity = sampling_plan_identity(plan)
        rng = manifest['identities']['rng']
        if identity['sha256'] != rng['plan_sha256'] or identity['patches'] != request['requested_patches']:
            raise ValueError('plan digest/count mismatch')
    elif manifest['outcomes']['dropped'] or manifest['outcomes']['failures']:
        raise ValueError('mixed outcomes require the exact plan')
    ids = {f'p{i:06d}_{signal}' for i in range(request['requested_patches']) for signal in request['signals']}
    entries = rows(trace)
    by_id = {e['attempt_id']: e for e in entries}
    if not ids or set(by_id) != ids or len(entries) != len(ids):
        raise ValueError('missing, duplicate or unexpected attempt')
    records = rows(dataset / manifest['artifacts']['records']['path'])
    events = rows(dataset / manifest['artifacts']['failure_ledger']['path'])
    terminal = [(r, 'kept') for r in records] + [(e, e['status']) for e in events]
    counts = {'kept': 0, 'dropped': 0, 'failures': 0}
    for record, status in terminal:
        attempt = record['patch_id'] + '_' + record['signal']
        if attempt not in by_id:
            raise ValueError('duplicate or unexpected terminal entry')
        entry = by_id.pop(attempt)
        if entry['schema'] != 'vital.render-trace/v1':
            raise ValueError('unexpected trace schema')
        if status not in ('kept', 'drop', 'failure'):
            raise ValueError('unknown terminal status')
        counts[{'kept':'kept', 'drop':'dropped', 'failure':'failures'}[status]] += 1
        expected = None
        if plan is not None:
            tier, expected = plan[int(record['patch_id'][1:])]
            if tier != record['tier']:
                raise ValueError('tier mismatch')
            if entry.get('requested_parameters') != {str(k): v for k, v in expected.items()}:
                raise ValueError('trace does not match planned parameters')
        if status == 'failure':
            if entry['outcome'] != 'failed' or record['stage'] != 'render_or_process':
                raise ValueError('failure trace mismatch (only render failures supported)')
            continue
        if entry['outcome'] != 'rendered' or entry['output']['name'] != attempt + '.wav':
            raise ValueError('render trace mismatch')
        readback = entry['parameter_readback']
        vector = expected if expected is not None else {int(k): v for k,v in record['param_vector'].items()}
        bound = {r['index']: r for r in readback}
        if len(bound) != len(readback) or set(bound) != set(vector):
            raise ValueError('readback index mismatch')
        for index, value in vector.items():
            rb = bound[index]
            if rb['parameter_id'] != CONTROL_IDS[index] or not math.isclose(rb['value'], value, abs_tol=5.1e-7, rel_tol=0):
                raise ValueError('parameter readback mismatch')
        if status == 'kept' and any(not math.isclose(record['param_vector'][str(k)], v, abs_tol=5.1e-7, rel_tol=0) for k,v in vector.items()):
            raise ValueError('record parameter mismatch')
    if by_id or counts != manifest['outcomes']:
        raise ValueError('missing terminal entry or outcome count mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    verify(args.dataset, args.trace, args.plan)
    print('Verified Vital dataset and complete attempt inventory.')
