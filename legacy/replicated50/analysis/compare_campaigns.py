#!/usr/bin/env python3
import argparse, json, statistics
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("campaign_root", nargs="?", default="results/campaigns")
a = ap.parse_args()

summaries = []
for p in Path(a.campaign_root).glob("*/summary.json"):
    try:
        d = json.loads(p.read_text())
        d["_path"] = str(p.parent)
        summaries.append(d)
    except Exception:
        pass

groups = {"baseline":[], "mars":[]}
for d in summaries:
    name = Path(d["_path"]).name
    if name.startswith("baseline_"):
        groups["baseline"].append(d)
    elif name.startswith("mars_"):
        groups["mars"].append(d)

metrics = [
    "mean_turnaround_s","mean_queue_s","mean_runtime_s","makespan_s",
    "mean_cluster_gpu_util_pct","accelerator_energy_kwh","completed","failed"
]
out = {}
for mode, rows in groups.items():
    out[mode] = {"n_runs":len(rows)}
    for m in metrics:
        vals = [float(r[m]) for r in rows if m in r]
        if vals:
            out[mode][m+"_mean"] = statistics.mean(vals)
            out[mode][m+"_sd"] = statistics.stdev(vals) if len(vals) > 1 else 0.0

if groups["mars"]:
    vals = [float(r["mean_decision_ms"]) for r in groups["mars"] if "mean_decision_ms" in r]
    if vals:
        out["mars"]["mean_decision_ms_mean"] = statistics.mean(vals)

if groups["baseline"] and groups["mars"]:
    imp = {}
    for metric in ["mean_turnaround_s","mean_queue_s","mean_runtime_s","makespan_s","accelerator_energy_kwh"]:
        kb = metric+"_mean"
        if kb in out["baseline"] and kb in out["mars"] and out["baseline"][kb]:
            imp[metric+"_reduction_pct"] = (
                100.0*(out["baseline"][kb]-out["mars"][kb])/out["baseline"][kb]
            )
    if "mean_cluster_gpu_util_pct_mean" in out["baseline"] and "mean_cluster_gpu_util_pct_mean" in out["mars"]:
        imp["gpu_util_gain_pp"] = (
            out["mars"]["mean_cluster_gpu_util_pct_mean"] -
            out["baseline"]["mean_cluster_gpu_util_pct_mean"]
        )
    out["improvement"] = imp

print(json.dumps(out, indent=2))
Path(a.campaign_root, "comparison.json").write_text(json.dumps(out, indent=2))
