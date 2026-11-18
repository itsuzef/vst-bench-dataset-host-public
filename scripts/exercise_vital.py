#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded native Vital regression; writes new evidence, never overwrites a run.

Uses a hand-specified plan (not an RNG sampling test). Injects one runner RPC
failure on the last attempt of the mixed run. All successful renders are native.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from http.server import HTTPServer
from unittest.mock import patch

from vst_bench_ml import cli


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.out.mkdir(parents=True, exist_ok=False)
    host_module = load('native_host', root / 'host/server.py')
    checker = load('vital_checker', root / 'scripts/verify_vital.py')
    results = {}
    for name in ['all-kept', 'mixed']:
        folder = args.out / name
        folder.mkdir()
        trace = folder / 'trace.jsonl'
        host = host_module.FixtureHost(args.runner.resolve(), root, trace)
        # Exact normalized values; 24/96 and 72/96 are discrete transpose levels.
        plan = [('A', {0: .65, 1: .25, 2: .5}),
                ('B', {0: 0.0 if name == 'mixed' else .7, 1: .75, 2: .25}),
                ('C', {0: .6, 1: .5, 2: .75}),
                ('C', {0: .7, 1: .5, 2: .5})]
        plan_file = folder / 'plan.json'
        plan_file.write_text(json.dumps(plan) + '\n')
        original = host._runner_call
        calls = 0

        def call(*values):
            nonlocal calls
            if values[0] == 'render':
                calls += 1
                if name == 'mixed' and calls == 4:
                    raise host_module.RpcError(-32020, 'explicit BON-4281 runner failure injection')
            return original(*values)

        host._runner_call = call
        server = HTTPServer(('127.0.0.1', 0), host_module.make_handler(host))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(cli.sampling, 'plan', return_value=plan):
                try:
                    cli.main(['render', '--plugin', str(args.plugin.resolve()),
                              '--param-manifest', str(root / 'fixtures/vital-1.0.6-controls.json'),
                              '--out', str(folder / 'dataset'), '--n', '4', '--signals', 'sus_c3',
                              '--signal-mode', 'all', '--sr', '44100', '--seconds', '1',
                              '--seed-label', 'bon-4281-hand-plan', '--port', str(server.server_port)])
                except SystemExit as exc:
                    if name != 'mixed' or 'failure injection' not in str(exc):
                        raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        checker.verify(folder / 'dataset', trace, plan_file)
        manifest = json.loads((folder / 'dataset/manifest.json').read_text())
        expected = {'kept': 4, 'dropped': 0, 'failures': 0} if name == 'all-kept' else {'kept': 2, 'dropped': 1, 'failures': 1}
        assert manifest['outcomes'] == expected, manifest['outcomes']
        entries = checker.rows(trace)
        mutations = {'missing-attempt': entries[:-1], 'duplicate-attempt': entries + entries[:1]}
        import copy
        bad = copy.deepcopy(entries)
        bad[0]['parameter_readback'][0]['value'] = .123
        mutations['readback-tamper'] = bad
        bad = copy.deepcopy(entries)
        bad[0]['requested_parameters']['1'] = .123
        mutations['plan-correspondence-tamper'] = bad
        bad = copy.deepcopy(entries)
        bad[-1]['outcome'] = 'unknown'
        mutations['terminal-outcome-tamper'] = bad
        rejected = []
        for label, changed in mutations.items():
            target = folder / (label + '.jsonl')
            target.write_text(''.join(json.dumps(row) + '\n' for row in changed))
            try:
                checker.verify(folder / 'dataset', target, plan_file)
            except ValueError:
                rejected.append(label)
            else:
                raise AssertionError('accepted ' + label)
        results[name] = {'outcomes': expected, 'tamper_cases_rejected': rejected,
                         'host': manifest['identities']['host'], 'plugin': manifest['identities']['plugin']}
    results['scope'] = 'Agent-run native renders; hand-specified plan; injected last runner failure; no human replication or general plugin support'
    results['hashes'] = {str(p.relative_to(args.out)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(args.out.rglob('*')) if p.is_file()}
    (args.out / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
