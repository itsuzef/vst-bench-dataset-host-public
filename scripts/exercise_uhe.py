#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded native u-he regression: two fresh CLI processes, three Output values.

Install each plugin separately under vendor terms. New output directories only.
This is a fixed-plan orchestration test, not RNG replay or human replication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import HTTPServer
from unittest.mock import patch

import numpy as np
import soundfile as sf
from vst_bench_ml import cli
from exercise_vital import load

PROFILES = {
    'podolski': ('D39D5B69D6AF42FA12345678506F646F', 'V1.2.3'),
    'triplecheese': ('D39D5B69D6AF42FA1234567863625379', 'V1.3.0'),
}


def verify(root, dataset, trace, plan, profile):
    checker = load('checker', root / 'scripts/verify_vital.py')
    checker.verify(dataset, trace, plan, identity=PROFILES[profile],
                   control_ids={0: '0'}, schema='uhe.render-trace/v1')


def worker(args, root):
    args.out.mkdir(parents=True, exist_ok=False)
    host_module = load('native_host', root / 'host/server.py')
    host = host_module.FixtureHost(args.runner.resolve(), root, args.out / 'trace.jsonl')
    plan = [('A', {0: .25}), ('B', {0: .5}), ('C', {0: .75})]
    (args.out / 'plan.json').write_text(json.dumps(plan) + '\n')
    original = host._runner_call
    calls = []

    def call(*values):
        result = original(*values)
        calls.append({'arguments': list(values), 'result': result})
        if values[0] == 'render':
            shutil.copyfile(values[3], args.out / f'raw-{len(calls)-1}.wav')
        return result

    host._runner_call = call
    server = HTTPServer(('127.0.0.1', 0), host_module.make_handler(host))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(cli.sampling, 'plan', return_value=plan):
            cli.main(['render', '--plugin', str(args.plugin.resolve()),
                      '--param-manifest', str(root / f'fixtures/{args.profile}-output.json'),
                      '--out', str(args.out / 'dataset'), '--n', '3',
                      '--signals', 'sus_c3', '--signal-mode', 'all', '--sr', '44100',
                      '--seconds', '1', '--seed-label', 'bon-4280-fixed-plan',
                      '--port', str(server.server_port)])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        (args.out / 'runner-calls.json').write_text(json.dumps(calls, indent=2) + '\n')
    verify(root, args.out / 'dataset', args.out / 'trace.jsonl', args.out / 'plan.json', args.profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.worker:
        worker(args, root)
        return
    args.out.mkdir(parents=True, exist_ok=False)
    for number in [1, 2]:
        command = [sys.executable, str(Path(__file__).resolve()),
                   '--plugin', str(args.plugin.resolve()), '--runner', str(args.runner.resolve()),
                   '--profile', args.profile, '--out', str((args.out / f'run-{number}').resolve()), '--worker']
        with (args.out / f'run-{number}.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    first, second = args.out / 'run-1', args.out / 'run-2'
    comparisons = []
    stored = []
    for a, b in zip(sorted((first / "dataset/audio").glob("*.npz")),
                    sorted((second / "dataset/audio").glob("*.npz")), strict=True):
        stored.append({"file": a.name, "bytes_equal": a.read_bytes() == b.read_bytes()})
    assert len(stored) == 3
    for a, b in zip(sorted(first.glob('raw-*.wav')), sorted(second.glob('raw-*.wav')), strict=True):
        x, sr = sf.read(a)
        y, other_sr = sf.read(b)
        assert sr == other_sr == 44100 and x.shape == y.shape == (44100, 2)
        assert np.isfinite(x).all() and np.isfinite(y).all() and np.max(np.abs(x)) > 0
        delta = x - y
        comparisons.append({'file': a.name, 'wav_bytes_equal': a.read_bytes() == b.read_bytes(),
                            'pcm_equal': bool(np.array_equal(x, y)),
                            'max_abs_difference': float(np.max(np.abs(delta))),
                            'rms_difference': float(np.sqrt(np.mean(delta**2))),
                            'raw_rms': float(np.sqrt(np.mean(x**2)))})
    assert len(comparisons) == 3
    # Show applied control has an observable raw-audio effect; normalization may remove gain differences.
    assert len({hashlib.sha256(p.read_bytes()).hexdigest() for p in first.glob('raw-*.wav')}) == 3
    rejected = {}
    checker = load('checker', root / 'scripts/verify_vital.py')
    for case in ['changed-output', 'missing-trace']:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / 'dataset'
            shutil.copytree(first / 'dataset', copied)
            trace = Path(tmp) / 'trace.jsonl'
            entries = checker.rows(first / 'trace.jsonl')
            if case == 'changed-output':
                manifest = json.loads((copied / 'manifest.json').read_text())
                output = copied / manifest['artifacts']['outputs'][0]['path']
                content = bytearray(output.read_bytes())
                content[-1] ^= 1
                output.write_bytes(content)
            else:
                entries = entries[:-1]
            trace.write_text(''.join(json.dumps(e) + '\n' for e in entries))
            try:
                verify(root, copied, trace, first / 'plan.json', args.profile)
            except ValueError as error:
                rejected[case] = str(error)
            else:
                raise AssertionError('accepted ' + case)
    result = {'profile': args.profile, 'identity': PROFILES[args.profile],
              'fixed_output_values': [.25, .5, .75], 'comparisons': comparisons,
              'stored_comparisons': stored, 'negative_cases_rejected': rejected,
              'scope': 'AI-agent native run; fresh Python and native processes; fixed plan, no RNG replay; no human replication; external consistency, not authentication',
              'hashes': {str(p.relative_to(args.out)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(args.out.rglob('*')) if p.is_file()}}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
