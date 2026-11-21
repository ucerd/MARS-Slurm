#!/usr/bin/env python3
"""Offline verification of the research release; does not submit jobs."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

RUNS = {
    ('compute40', 'baseline'): ('baseline_rep1_20261114_181632', 40, 40),
    ('compute40', 'admission_only'): ('admission_only_rep1_20261114_185022', 40, 40),
    ('compute40', 'mars'): ('mars_rep1_20261114_193801', 40, 40),
    ('mixed25', 'baseline'): ('baseline_rep1_20261114_151321', 25, 25),
    ('mixed25', 'admission_only'): ('admission_only_rep2_20261114_172053', 25, 22),
    ('mixed25', 'mars'): ('mars_rep2_20261114_171734', 25, 25),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def equal(a, b):
    return math.isclose(float(a), float(b), abs_tol=1e-8, rel_tol=1e-10)


def read_csv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def read_json(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    root = p.parse_args().root.resolve()
    instrumented = root / 'data/instrumented'
    # Verify the exact server-recorded source checksums against repository paths.
    for line in (instrumented / 'cluster_source_hashes.txt').read_text().splitlines():
        expected, name = line.split()
        rel = name if name.startswith('jobs/') else ('analysis/' if name.endswith('.py') else 'config/') + name
        require(digest(root / rel) == expected, f'source checksum {rel}')
    print('PASS: all five recorded server source hashes')
    summaries = {(r['protocol'], r['mode']): r for r in read_csv(instrumented / 'reported_campaign_summary.csv')}
    require(set(summaries) == set(RUNS), 'reported summary run keys')
    for (protocol, mode), (run, expected, completed) in RUNS.items():
        folder = instrumented / protocol / run
        s = read_json(folder / 'summary.json')
        rows = read_csv(folder / 'job_metrics.csv')
        valid = [r for r in rows if r['valid_completed'] == 'True']
        require((s['n_jobs'], s['n_valid_completed'], len(rows), len(valid)) == (expected, completed, expected, completed), run + ': counts')
        require(s['mode'] == mode, run + ': mode')
        release = read_csv(folder / 'release_jobs.csv')
        require(len(release) == expected and sum(bool(r['job_id']) for r in release) == expected, run + ': release counts')
        for k, m in s['metrics'].items():
            values = [float(r[k]) for r in valid if r.get(k) not in ('', None)]
            require(len(values) == m['n'] and equal(statistics.mean(values), m['mean']), run + ': mean ' + k)
            if len(values) > 1:
                require(equal(statistics.stdev(values), m['sample_std']), run + ': SD ' + k)
        driver = 'run_reviewer1_compute40.py' if protocol == 'compute40' else 'run_reviewer1_pilot.py'
        manifest = 'workload_manifest_compute40.csv' if protocol == 'compute40' else 'pilot_25_jobs_precreated.csv'
        for local, public in [('driver_snapshot.py', 'analysis/' + driver), ('policy.json', 'config/policy.json'), ('workload_manifest.csv', 'config/' + manifest)]:
            require(digest(folder / local) == digest(root / public), run + ': snapshot ' + local)
        if (protocol, mode) == ('mixed25', 'baseline'):
            # Baseline does not invoke admission/placement policy.
            require(digest(folder / 'mars_policy_snapshot.py') == digest(root / 'legacy/diagnostics/mars_policy.py.before_ssh_fix'), run + ': baseline snapshot provenance')
        else:
            require(digest(folder / 'mars_policy_snapshot.py') == digest(root / 'analysis/mars_policy.py'), run + ': corrected collector snapshot')
        r = summaries[(protocol, mode)]
        require((r['run'], int(r['n_jobs']), int(r['completed'])) == (run, expected, completed), run + ': summary CSV counts')
        for a, b in {'eligible_to_end_s':'eligible_to_end_s', 'submit_to_end_s':'submit_to_end_s', 'release_to_end_s':'release_to_end_s', 'release_to_ack_s':'pre_submit_delay_s', 'execution_s':'start_to_end_s', 'decision_time_s':'decision_time_s'}.items():
            require(equal(r[a], s['metrics'][b]['mean']), run + ': summary CSV ' + a)
        require(equal(r['eligible_to_start_s'], s['metrics']['eligible_to_end_s']['mean'] - s['metrics']['start_to_end_s']['mean']), run + ': derived waiting')
        makespan = s['campaign_makespan_from_first_planned_release_s']
        require((makespan is None and r['makespan_s'] == '') or (makespan is not None and equal(r['makespan_s'], makespan)), run + ': makespan')
        print(f'PASS: {protocol}/{mode}: {completed}/{expected} completed; summaries and snapshots agree')
    comparison = read_json(root / 'data/comparison.json')
    for mode in ('baseline', 'mars'):
        runs = [read_json(p) for p in (root / 'data/accepted').glob(mode + '_*/summary.json')]
        require(len(runs) == 3 and all(r['completed'] == 50 for r in runs), mode + ': historical counts')
        for k in ('mean_queue_s', 'mean_turnaround_s', 'mean_runtime_s', 'makespan_s', 'mean_cluster_gpu_util_pct', 'accelerator_energy_kwh'):
            v = [r[k] for r in runs]
            require(equal(statistics.mean(v), comparison[mode][k + '_mean']) and equal(statistics.stdev(v), comparison[mode][k + '_sd']), mode + ': replicated aggregate ' + k)
        print(f'PASS: replicated50/{mode}: 3 x 50 completed, archived aggregate agrees')
    print('All offline checks passed. No live Slurm jobs were submitted.')


if __name__ == '__main__':
    main()
