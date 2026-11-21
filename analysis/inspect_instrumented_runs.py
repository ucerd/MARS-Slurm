#!/usr/bin/env python3
"""List campaign results, including incomplete runs; no pooling across protocols."""
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path)
    a=p.parse_args()
    if not a.root.is_dir(): p.error('Missing root directory')
    rows=[]
    for d in sorted(a.root.rglob('summary.json')):
        try: s=json.loads(d.read_text())
        except (ValueError, OSError) as exc: raise SystemExit(f'{d}: {exc}')
        def mean(k): return s.get('metrics',{}).get(k,{}).get('mean')
        e,r=mean('eligible_to_end_s'),mean('start_to_end_s')
        rows.append(dict(run=str(d.parent.relative_to(a.root)),mode=s.get('mode'),rep=s.get('rep'),expected=s.get('n_jobs'),submitted=s.get('n_submitted'),completed=s.get('n_valid_completed'),eligible_to_end_s=e,eligible_to_start_s=e-r if e is not None and r is not None else None,release_to_end_s=mean('release_to_end_s'),pre_submit_delay_s=mean('pre_submit_delay_s'),start_to_end_s=r,decision_time_s=mean('decision_time_s'),makespan_s=s.get('campaign_makespan_from_first_planned_release_s')))
    known={str(d.parent) for d in a.root.rglob('summary.json')}
    for d in sorted(a.root.rglob('release_jobs.csv')):
        if str(d.parent) not in known:
            with d.open(newline='') as f: jobs=list(csv.DictReader(f))
            rows.append(dict(run=str(d.parent.relative_to(a.root)),mode='',rep='',expected=len(jobs),submitted=sum(bool(j.get('job_id')) for j in jobs),completed=None,eligible_to_end_s=None,eligible_to_start_s=None,release_to_end_s=None,pre_submit_delay_s=None,start_to_end_s=None,decision_time_s=None,makespan_s=None))
    if not rows: raise SystemExit('No original summary.json or release_jobs.csv found; export cluster artifacts first.')
    for r in rows: print(json.dumps(r))
    if a.out:
        with a.out.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

if __name__=='__main__': main()
