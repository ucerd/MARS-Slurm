#!/usr/bin/env python3
import argparse, csv, json, statistics, datetime, math
from pathlib import Path
from collections import defaultdict

def parse_ts(s):
    if not s or s in ("Unknown","None"):
        return None
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return None

ap = argparse.ArgumentParser()
ap.add_argument("run_dir")
a = ap.parse_args()
rd = Path(a.run_dir)

jobs = list(csv.DictReader(open(rd/"sacct.csv")))
valid = []
byclass = defaultdict(list)

for r in jobs:
    sub, sta, end = parse_ts(r["Submit"]), parse_ts(r["Start"]), parse_ts(r["End"])
    if sub and sta and end:
        x = {
            "job_id":r["job_id"], "class":r["class"], "state":r["State"],
            "queue_s":sta-sub, "runtime_s":end-sta, "turnaround_s":end-sub
        }
        valid.append(x)
        byclass[r["class"]].append(x)

summary = {
    "run_dir":str(rd),
    "jobs_total":len(jobs),
    "jobs_with_timestamps":len(valid),
    "completed":sum(1 for r in jobs if r["State"].startswith("COMPLETED")),
    "failed":sum(1 for r in jobs if r["State"] and not r["State"].startswith("COMPLETED")),
}

if valid:
    tt = [x["turnaround_s"] for x in valid]
    summary.update({
        "mean_queue_s":statistics.mean(x["queue_s"] for x in valid),
        "mean_runtime_s":statistics.mean(x["runtime_s"] for x in valid),
        "mean_turnaround_s":statistics.mean(tt),
        "median_turnaround_s":statistics.median(tt),
        "p95_turnaround_s":sorted(tt)[max(0, math.ceil(0.95*len(tt))-1)],
        "makespan_s":max(parse_ts(r["End"]) for r in jobs if parse_ts(r["End"])) -
                     min(parse_ts(r["Submit"]) for r in jobs if parse_ts(r["Submit"])),
    })

tel_path = rd/"campaign_gpu.csv"
if tel_path.exists():
    tel = list(csv.DictReader(open(tel_path)))
    if tel:
        summary["mean_cluster_gpu_util_pct"] = statistics.mean(float(x["gpu_util_pct"]) for x in tel)
        bynode = defaultdict(list)
        for x in tel:
            bynode[x["node"]].append(x)
        total_j = 0.0
        for node, vals in bynode.items():
            vals.sort(key=lambda x: float(x["epoch"]))
            for p, q in zip(vals, vals[1:]):
                t0, t1 = float(p["epoch"]), float(q["epoch"])
                pw0, pw1 = float(p["power_w"]), float(q["power_w"])
                total_j += 0.5*(pw0+pw1)*max(0.0, t1-t0)
        summary["accelerator_energy_wh"] = total_j/3600.0
        summary["accelerator_energy_kwh"] = total_j/3_600_000.0

dec = rd/"decisions.csv"
if dec.exists():
    dr = list(csv.DictReader(open(dec)))
    ms = [float(x["decision_ms"]) for x in dr if x.get("decision_ms")]
    if ms:
        summary["mean_decision_ms"] = statistics.mean(ms)
        summary["p95_decision_ms"] = sorted(ms)[max(0, math.ceil(0.95*len(ms))-1)]

summary["per_class"] = {}
for cls, xs in byclass.items():
    summary["per_class"][cls] = {
        "n":len(xs),
        "mean_queue_s":statistics.mean(x["queue_s"] for x in xs),
        "mean_runtime_s":statistics.mean(x["runtime_s"] for x in xs),
        "mean_turnaround_s":statistics.mean(x["turnaround_s"] for x in xs),
    }

(rd/"summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
