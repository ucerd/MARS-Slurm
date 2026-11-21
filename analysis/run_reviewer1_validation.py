#!/usr/bin/env python3
"""MARS-Slurm Reviewer 1: fresh, independently released validation campaigns.

Version 2: baseline and admission-only use --exclude, preventing the
Slurm --nodelist=three-nodes versus #SBATCH --nodes=1 mismatch.

Place in mars_bench_suite/mars_final_experiment alongside mars_policy.py and
campaign_telemetry.py. Run there; do NOT replace original run_campaign.py.

Modes:
  baseline        Native Slurm chooses any node in the *same* candidate pool.
  admission_only  MARS guards gate submission; Slurm chooses among all nodes
                  passing those guards (feasible-set restriction; not pure
                  unrestricted native Slurm).
  mars            Original MARS guards and ranking choose one pinned node.

All three use 50 independent, monotonic-clock scheduled release events. Admission
workers execute concurrently, while telemetry assessment + sbatch are serialized
for atomic reservation visibility. This new workload driver is a NEW experiment;
its results must not be combined with the September 2026 experiments.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from mars_policy import choose_node

JOB_FIELDS = [
    'index', 'jobtag', 'class', 'mode', 'rep', 'job_id', 'selected_node',
    'eligible_node_set', 'cpus', 'mem_gib', 'gpus', 'gpu_mem_gib',
    'planned_release', 'actual_release', 'submitted_at',
    'release_delay_s', 'pre_submit_delay_s', 'decision_time_s',
    'admission_poll_count', 'sbatch_error', 'candidate_json'
]
ACCOUNTING_FIELDS = [
    'JobIDRaw', 'JobName', 'Partition', 'Submit', 'Eligible', 'Start', 'End',
    'State', 'ExitCode', 'NodeList', 'ReqTRES', 'AllocTRES'
]


def now():
    return datetime.now().astimezone()


def iso(dt):
    return dt.isoformat(timespec='microseconds')


def seconds_from_string(s):
    if not s or s in {'Unknown', 'None', 'N/A', 'Invalid'}:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # sacct timestamps reflect the local time zone of this master node.
            dt = dt.replace(tzinfo=now().tzinfo)
        return dt
    except (ValueError, TypeError):
        return None


def timedifference(later, earlier):
    a, b = seconds_from_string(later), seconds_from_string(earlier)
    return (a - b).total_seconds() if a and b else None


def call(args, timeout=None, check=True):
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)
    if check and proc.returncode:
        raise RuntimeError(f"Command failed {args!r}: {proc.stderr.strip()}")
    return proc


def csv_write(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def save_text(path, txt):
    path.write_text(txt, encoding='utf-8')


def slurm_placement_options(mode, allowed_nodes, cluster_nodes):
    """Keep single-node workloads within the permitted node set.

    A multi-node --nodelist conflicts with #SBATCH --nodes=1 on the
    experiment's Slurm release (observed error: -N 3-1). Instead, for
    baseline/admission-only, exclude all other nodes and let Slurm pick
    any one of the remaining nodes. Retain exact pinning only for MARS.
    """
    allowed = set(allowed_nodes)
    inventory = set(cluster_nodes)
    if not allowed:
        raise ValueError('Cannot submit without permitted nodes')
    if not allowed <= inventory:
        raise ValueError('Permitted nodes not all registered in Slurm: '
                         + ','.join(sorted(allowed-inventory)))
    if mode == 'mars':
        if len(allowed) != 1:
            raise ValueError('MARS mode must select exactly one node')
        return ['--nodelist=' + next(iter(allowed))]
    if mode not in {'baseline', 'admission_only'}:
        raise ValueError('Unknown scheduling mode: ' + mode)
    excluded = sorted(inventory - allowed)
    return ['--exclude=' + ','.join(excluded)] if excluded else []


def get_active_jobs(submitted):
    """Match original experiment's active-state handling; only tracked jobs."""
    ids = [x['job_id'] for x in submitted if x.get('job_id')]
    if not ids:
        return []
    p = call(['squeue', '-h', '-j', ','.join(ids), '-o', '%i|%T'], check=False)
    states = {}
    for line in p.stdout.splitlines():
        if '|' in line:
            jid, state = line.strip().split('|', 1)
            states[jid] = state
    active = []
    for record in submitted:
        state = states.get(record.get('job_id'))
        if state in {'PENDING', 'RUNNING'}:
            item = dict(record)
            item['state'] = state
            item['node'] = record.get('selected_node', '')
            active.append(item)
    return active


def account(ids, directory, trials=24, wait_seconds=3):
    """Read actual Slurm Eligible timestamps; do not invent missing values."""
    complete = {}
    header = ACCOUNTING_FIELDS
    for attempt in range(trials):
        p = call(['sacct', '-X', '-n', '-P', '-j', ','.join(ids),
                  '--format=' + ','.join(header)], check=False)
        if p.returncode:
            print('sacct warning:', p.stderr.strip(), flush=True)
        for line in p.stdout.splitlines():
            parts = line.split('|')
            if len(parts) < len(header):
                continue
            row = dict(zip(header, parts))
            if row['JobIDRaw'] in ids:
                complete[row['JobIDRaw']] = row
        if len(complete) == len(ids) and all(
                x.get('Eligible') not in ('', 'Unknown', 'None')
                and x.get('End') not in ('', 'Unknown', 'None')
                for x in complete.values()):
            break
        time.sleep(wait_seconds)
    ordered = [complete.get(j, {'JobIDRaw': j}) for j in ids]
    csv_write(directory / 'slurm_accounting.psv.csv', ordered, header)
    return complete


def summarize(jobs, accounting, directory, mode, rep, t0):
    rows = []
    metric_names = [
        'pre_submit_delay_s', 'release_to_eligible_s',
        'release_to_start_s', 'release_to_end_s',
        'submit_to_start_s', 'submit_to_end_s',
        'eligible_to_end_s', 'start_to_end_s',
        'decision_time_s', 'release_delay_s'
    ]
    columns = list(dict.fromkeys(JOB_FIELDS + ACCOUNTING_FIELDS + metric_names + ['valid_completed']))
    for row in jobs:
        data = dict(row)
        ac = accounting.get(row['job_id'], {})
        data.update(ac)
        intervals = {
            'release_to_eligible_s': ('Eligible', 'actual_release'),
            'release_to_start_s': ('Start', 'actual_release'),
            'release_to_end_s': ('End', 'actual_release'),
            'submit_to_start_s': ('Start', 'Submit'),
            'submit_to_end_s': ('End', 'Submit'),
            'eligible_to_end_s': ('End', 'Eligible'),
            'start_to_end_s': ('End', 'Start')
        }
        for key, (endkey, startkey) in intervals.items():
            data[key] = timedifference(data.get(endkey, ''), data.get(startkey, ''))
        state = ac.get('State', '')
        exitcode = ac.get('ExitCode', '')
        time_ok = all(
            data.get(x) is not None and data[x] >= -1.0
            for x in ['release_to_end_s', 'eligible_to_end_s', 'start_to_end_s']
        )
        # Up to one-second discrepancies can arise from Slurm second-resolution
        # timestamps versus microsecond-resolution external release timestamps.
        data['valid_completed'] = (
            state == 'COMPLETED' and exitcode == '0:0' and time_ok
        )
        rows.append(data)
    csv_write(directory / 'job_metrics.csv', rows, columns)
    valid = [x for x in rows if x['valid_completed']]
    bymetric = {}
    for key in metric_names:
        values = [float(x[key]) for x in valid if x.get(key) not in ('', None)]
        bymetric[key] = {
            'n': len(values),
            'mean': statistics.mean(values) if values else None,
            'sample_std': statistics.stdev(values) if len(values) > 1 else None
        }
    ends = [seconds_from_string(x.get('End')) for x in valid]
    ends = [x for x in ends if x]
    t0dt = seconds_from_string(t0)
    campaign_makespan = (max(ends) - t0dt).total_seconds() if len(valid) == len(jobs) and ends else None
    # Sampled accelerator telemetry: same GPU-only measurement scope as the
    # original campaign. These are estimates, NOT facility-level energy.
    gpu_mean_util, gpu_energy_kwh, gpu_samples = None, None, 0
    gpu_csv = directory / 'campaign_gpu.csv'
    if len(valid) == len(jobs) and ends and gpu_csv.exists():
        first_epoch = t0dt.timestamp()
        last_epoch = max(ends).timestamp()
        bynode = {}
        with gpu_csv.open(newline='') as f:
            for item in csv.DictReader(f):
                try:
                    epoch = float(item['epoch'])
                    util = float(item['gpu_util_pct'])
                    watts = float(item['power_w'])
                except (KeyError, ValueError, TypeError):
                    continue
                if first_epoch <= epoch <= last_epoch:
                    bynode.setdefault(item['node'], []).append((epoch, util, watts))
        utils, energy_wh = [], 0.0
        for node, samples in bynode.items():
            samples.sort()
            utils += [q[1] for q in samples]
            for a, b in zip(samples, samples[1:]):
                dt = max(0, b[0] - a[0])
                energy_wh += (a[2] + b[2]) / 2 * dt / 3600.0
        gpu_samples = len(utils)
        if utils:
            gpu_mean_util = statistics.mean(utils)
            gpu_energy_kwh = energy_wh / 1000.0
    report = {
        'mode': mode, 'rep': rep, 'n_jobs': len(jobs),
        'n_submitted': sum(bool(x['job_id']) for x in jobs),
        'n_sacct_records': sum(bool(accounting.get(x['job_id'])) for x in jobs),
        'n_valid_completed': len(valid),
        'campaign_makespan_from_first_planned_release_s': campaign_makespan,
        'mean_gpu_utilization_pct': gpu_mean_util,
        'sampled_gpu_energy_kwh': gpu_energy_kwh,
        'gpu_samples': gpu_samples,
        'metrics': bymetric,
        'limitations': [
            'New experiment, not the archived September 2026 campaign.',
            'Admission_only excludes nodes outside the feasible set; Slurm chooses from feasible nodes.',
            'Seconds in Slurm accounting; release timestamp has subsecond precision.',
            'Only tracked experiment jobs are used for MARS campaign reservations.',
            'Synchronous telemetry + sbatch is serialized to avoid simultaneous selection races.'
        ]
    }
    (directory / 'summary.json').write_text(json.dumps(report, indent=2))
    print('\n================ VALIDATION SUMMARY ================')
    print(f"{mode} rep{rep}: {len(valid)}/{len(jobs)} completed with valid timestamps")
    print('campaign makespan from first planned release:', campaign_makespan)
    for name in ['eligible_to_end_s', 'submit_to_end_s', 'release_to_end_s',
                 'pre_submit_delay_s', 'start_to_end_s', 'decision_time_s']:
        print(f'  {name}: {bymetric[name]["mean"]} s (n={bymetric[name]["n"]})')
    print('====================================================')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', required=True, choices=['baseline', 'admission_only', 'mars'])
    parser.add_argument('--rep', required=True, type=int)
    parser.add_argument('--cadence', type=float, default=2.0)
    parser.add_argument('--manifest', default='workload_manifest.csv')
    parser.add_argument('--policy', default='policy.json')
    parser.add_argument('--out-root', default='reviewer1_validation')
    parser.add_argument('--max-admission-sec', type=float, default=900)
    parser.add_argument('--max-completion-sec', type=float, default=3600)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.cadence <= 0 or args.rep <= 0:
        parser.error('cadence and rep must be positive')
    base = Path.cwd()
    policy_file = Path(args.policy).resolve()
    manifest_file = Path(args.manifest).resolve()
    policy = json.loads(policy_file.read_text())
    manifest = list(csv.DictReader(manifest_file.open(newline='')))
    if len(manifest) != 50:
        parser.error(f'Expected original 50-job workload, got {len(manifest)}')
    nodes = policy['candidate_nodes']
    if len(nodes) != 3:
        parser.error(f'For the matched three-node study require exactly 3 candidate_nodes, got {nodes}')
    if len(set(nodes)) != 3:
        parser.error('Candidate node list contains duplicates')
    for spec in manifest:
        for key in ['jobtag', 'class', 'script', 'cpus', 'mem_gib', 'gpus', 'gpu_mem_gib']:
            if not spec.get(key):
                parser.error(f'Missing {key} in manifest job {spec}')
        script = Path(spec['script'])
        if not (base / script).is_file():
            parser.error(f'Missing job script {spec["script"]}; run from mars_final_experiment directory')
        if spec['class'] not in policy['weights']:
            parser.error(f'Missing policy weights for class {spec["class"]}')
    for exe in ('sacct', 'sbatch', 'squeue', 'sinfo'):
        if shutil.which(exe) is None:
            parser.error(f'Missing Slurm command: {exe}')
    if not Path('campaign_telemetry.py').exists():
        parser.error('campaign_telemetry.py not in working directory')
    print('Working directory:', base)
    print('Mode:', args.mode, 'Rep:', args.rep, 'Nodes:', ','.join(nodes))
    print('Workload:', len(manifest), 'jobs at', args.cadence, 'seconds apart')
    print('First and last:', manifest[0]['jobtag'], manifest[-1]['jobtag'])
    if args.dry_run:
        print('DRY RUN ONLY: no jobs will be submitted.')
        return
    # Protect other users: refuse if any experimental node is currently occupied.
    existing = call(['squeue', '-h', '-w', ','.join(nodes), '-o', '%i|%j|%T|%N'], check=False)
    if existing.stdout.strip():
        parser.error('Jobs already exist on candidate nodes; do not mix campaigns:\n' + existing.stdout)
    statecheck = call(['sinfo', '-N', '-h', '-n', ','.join(nodes), '-o', '%N|%T'])
    actual = {}
    for line in statecheck.stdout.splitlines():
        if '|' in line:
            n, st = line.strip().split('|', 1)
            actual[n] = st.lower()
    if any('idle' not in actual.get(n, '') for n in nodes):
        parser.error('All candidate nodes must be idle before starting. Observed: ' + str(actual))
    # Query all Slurm nodes once. An exclusion list is a safe way to allow
    # ONE-node jobs to run anywhere inside the desired subset.
    inventory_result = call(['sinfo', '-N', '-h', '-o', '%N'])
    cluster_nodes = sorted(set(x.strip() for x in inventory_result.stdout.splitlines()
                               if x.strip()))
    if not set(nodes).issubset(cluster_nodes):
        parser.error('Candidate nodes missing from Slurm node inventory: '
                     + str(sorted(set(nodes) - set(cluster_nodes))))
    print('Registered Slurm nodes:', ','.join(cluster_nodes), flush=True)
    tag = now().strftime('%Y%m%d_%H%M%S')
    root = Path(args.out_root).resolve()
    directory = root / f'{args.mode}_rep{args.rep}_{tag}'
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'logs').mkdir()
    shutil.copy2(manifest_file, directory / 'workload_manifest.csv')
    shutil.copy2(policy_file, directory / 'policy.json')
    shutil.copy2(Path(__file__).resolve(), directory / 'driver_snapshot.py')
    shutil.copy2(Path('mars_policy.py'), directory / 'mars_policy_snapshot.py')
    save_text(directory / 'initial_sinfo.txt', statecheck.stdout)
    save_text(directory / 'cluster_datetime.txt', iso(now()) + '\n')
    print('RUN_DIR=', directory, flush=True)
    # Start monitoring before release. This logs GPU utilization/power as original.
    telemetry_out = (directory / 'campaign_gpu.csv')
    tele = subprocess.Popen([sys.executable, 'campaign_telemetry.py', '--out',
                             str(telemetry_out), '--nodes', *nodes, '--interval', '2'])
    gate = threading.RLock()
    submitted = []
    tasks = []
    start_dt = now()
    t0 = time.monotonic()
    if args.mode == 'baseline':
        print('Baseline: Slurm chooses one node among the candidate pool (using --exclude).', flush=True)
    if args.mode == 'admission_only':
        print('Admission-only: guards restrict to FEASIBLE nodes using --exclude; ranking ignored.', flush=True)

    def job_worker(i, spec, planned, released):
        poll_count = 0
        decision_s = 0.0
        selected = ''
        allowed = ''
        candidates = []
        submit_dt = None
        job_id = ''
        error = ''
        release_clock = time.monotonic()
        try:
            while True:
                with gate:
                    if args.mode == 'baseline':
                        allowed_nodes = list(nodes)
                    else:
                        before = time.perf_counter()
                        chosen, candidates = choose_node(spec, policy, get_active_jobs(submitted))
                        decision_s += time.perf_counter() - before
                        poll_count += 1
                        feasible = [c['node'] for c in candidates if c.get('feasible')]
                        if args.mode == 'mars':
                            selected = chosen['node'] if chosen else ''
                            allowed_nodes = [selected] if selected else []
                        else:
                            allowed_nodes = sorted(feasible)
                    if allowed_nodes:
                        allowed = ','.join(allowed_nodes)
                        out = directory / 'logs' / (spec['jobtag'] + '_%j.out')
                        err = directory / 'logs' / (spec['jobtag'] + '_%j.err')
                        # Original batch scripts require --nodes=1. Passing a
                        # multi-node --nodelist caused Slurm's '-N 3-1' error.
                        placement = slurm_placement_options(args.mode, allowed_nodes,
                                                            cluster_nodes)
                        opts = [
                            'sbatch', '--parsable', *placement,
                            '--output=' + str(out), '--error=' + str(err),
                            '--export=ALL,RUN_DIR=' + str(directory) + ',JOBTAG=' +
                            spec['jobtag'] + ',WORKLOAD_CLASS=' + spec['class'],
                            str(Path(spec['script']).resolve())
                        ]
                        p = call(opts, check=False)
                        if p.returncode:
                            error = p.stderr.strip() or p.stdout.strip()
                            break
                        submit_dt = now()
                        job_id = p.stdout.strip().split(';')[0]
                        if not re.fullmatch(r'\d+', job_id):
                            error = 'Cannot parse sbatch job id: ' + p.stdout.strip()
                            break
                        submitted.append({
                            'job_id': job_id, 'selected_node': selected,
                            'node': selected, 'mem_gib': spec['mem_gib'],
                            'gpus': spec['gpus'], 'gpu_mem_gib': spec['gpu_mem_gib']
                        })
                        break
                if time.monotonic() - release_clock > args.max_admission_sec:
                    error = f'Admission timed out after {args.max_admission_sec} seconds'
                    break
                time.sleep(2)
        except Exception as exc:
            error = str(exc)
        record = {
            'index': i, 'jobtag': spec['jobtag'], 'class': spec['class'],
            'mode': args.mode, 'rep': args.rep, 'job_id': job_id,
            'selected_node': selected, 'eligible_node_set': allowed,
            'cpus': spec['cpus'], 'mem_gib': spec['mem_gib'],
            'gpus': spec['gpus'], 'gpu_mem_gib': spec['gpu_mem_gib'],
            'planned_release': iso(planned), 'actual_release': iso(released),
            'submitted_at': iso(submit_dt) if submit_dt else '',
            'release_delay_s': round((released-planned).total_seconds(), 6),
            'pre_submit_delay_s': round((submit_dt-released).total_seconds(), 6) if submit_dt else '',
            'decision_time_s': round(decision_s, 6),
            'admission_poll_count': poll_count, 'sbatch_error': error,
            'candidate_json': json.dumps(candidates, separators=(',', ':'))
        }
        print(f"{i+1:02d}/{len(manifest)} job={job_id or 'NONE'} tag={spec['jobtag']} "
              f"node(s)={allowed or 'NONE'} poll={poll_count} "
              f"error={error[:90]}", flush=True)
        return record

    records = []
    try:
        with ThreadPoolExecutor(max_workers=len(manifest)) as pool:
            futures = []
            for i, spec in enumerate(manifest):
                target = t0 + i * args.cadence
                gap = target - time.monotonic()
                if gap > 0:
                    time.sleep(gap)
                planned = start_dt + timedelta(seconds=i * args.cadence)
                released = now()
                futures.append(pool.submit(job_worker, i, spec, planned, released))
            # Each job was independently released at its scheduled time, even if
            # earlier jobs are still waiting for MARS admission.
            for future in as_completed(futures):
                records.append(future.result())
        records.sort(key=lambda x: int(x['index']))
        csv_write(directory / 'release_jobs.csv', records, JOB_FIELDS)
        ids = [x['job_id'] for x in records if x['job_id']]
        if len(ids) != len(manifest):
            print('ERROR: Not all jobs were submitted. Inspect release_jobs.csv.', flush=True)
        else:
            started = time.monotonic()
            while True:
                q = call(['squeue', '-h', '-j', ','.join(ids)], check=False)
                if not q.stdout.strip():
                    break
                if time.monotonic() - started > args.max_completion_sec:
                    raise RuntimeError('Jobs still pending/running after completion timeout. '
                                       'No jobs were cancelled automatically.')
                time.sleep(5)
            # Stop GPU monitoring at the end of the actual workload campaign;
            # otherwise slow sacct collection would inflate measured GPU energy.
            if tele.poll() is None:
                tele.terminate()
                try:
                    tele.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    tele.kill()
            print('Slurm queue drained. Querying sacct eligibility/accounting...', flush=True)
            ac = account(ids, directory)
            summarize(records, ac, directory, args.mode, args.rep, iso(start_dt))
    finally:
        if tele.poll() is None:
            tele.terminate()
            try:
                tele.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tele.kill()
        if records and not (directory / 'release_jobs.csv').exists():
            csv_write(directory / 'release_jobs.csv', records, JOB_FIELDS)
        save_text(directory / 'campaign_end.txt', iso(now()) + '\n')
    print('FINISHED', directory, flush=True)


if __name__ == '__main__':
    main()

