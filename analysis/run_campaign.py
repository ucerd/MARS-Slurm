#!/usr/bin/env python3
import argparse, csv, json, subprocess, time
from pathlib import Path
from datetime import datetime
from mars_policy import choose_node

def run(cmd, check=True):
    return subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check)

def active_states(submitted):
    ids = [x["job_id"] for x in submitted]
    if not ids:
        return []
    p = run("squeue -h -j "+",".join(ids)+" -o '%i|%T'", check=False)
    states = {}
    for line in p.stdout.splitlines():
        if "|" in line:
            jid, st = line.strip().split("|", 1)
            states[jid] = st
    out = []
    for x in submitted:
        st = states.get(x["job_id"])
        if st in ("PENDING","RUNNING"):
            y = dict(x)
            y["state"] = st
            y["node"] = x.get("selected_node","")
            out.append(y)
    return out

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["baseline","mars"], required=True)
ap.add_argument("--rep", type=int, required=True)
ap.add_argument("--cadence", type=float, default=2.0)
ap.add_argument("--manifest", default="workload_manifest.csv")
ap.add_argument("--policy", default="policy.json")
a = ap.parse_args()

base = Path.cwd()
policy = json.load(open(a.policy))
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
rd = base/"results"/"campaigns"/f"{a.mode}_rep{a.rep}_{stamp}"
(rd/"logs").mkdir(parents=True, exist_ok=True)
print("RUN_DIR=", rd, flush=True)

nodes = policy["candidate_nodes"]
tele = subprocess.Popen([
    "python3","campaign_telemetry.py","--out",str(rd/"campaign_gpu.csv"),
    "--nodes",*nodes,"--interval","2"
])

manifest = list(csv.DictReader(open(a.manifest)))
submitted = []
decisions = []
t0 = time.monotonic()

try:
    for i, spec in enumerate(manifest):
        target = t0 + i*a.cadence
        if time.monotonic() < target:
            time.sleep(target-time.monotonic())

        selected = ""
        candidates = []
        decision_ms = 0.0

        if a.mode == "mars":
            while True:
                t = time.perf_counter()
                chosen, candidates = choose_node(spec, policy, active_states(submitted))
                decision_ms += (time.perf_counter()-t)*1000.0
                if chosen is not None:
                    selected = chosen["node"]
                    break
                time.sleep(2)

        out = rd/"logs"/f'{spec["jobtag"]}_%j.out'
        err = rd/"logs"/f'{spec["jobtag"]}_%j.err'

        common = (
            f"sbatch --parsable --output='{out}' --error='{err}' "
            f"--export=ALL,RUN_DIR='{rd}',JOBTAG='{spec['jobtag']}',WORKLOAD_CLASS='{spec['class']}' "
        )
        if a.mode == "baseline":
            common += "--exclude=" + ",".join(policy["excluded_nodes"]) + " "
        else:
            common += f"--nodelist={selected} "

        p = run(common + spec["script"])
        jid = p.stdout.strip().split(";")[0]

        row = {
            "job_id":jid,"jobtag":spec["jobtag"],"class":spec["class"],"mode":a.mode,
            "selected_node":selected,"cpus":spec["cpus"],"mem_gib":spec["mem_gib"],
            "gpus":spec["gpus"],"gpu_mem_gib":spec["gpu_mem_gib"]
        }
        submitted.append(row)
        decisions.append({
            **row,
            "decision_ms":f"{decision_ms:.3f}",
            "candidate_json":json.dumps(candidates, separators=(",",":"))
        })
        print(f"{i+1:02d}/50 {jid} {spec['jobtag']} {selected or 'SLURM'}", flush=True)

    with open(rd/"jobs.csv","w",newline="") as f:
        fields = list(submitted[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(submitted)

    with open(rd/"decisions.csv","w",newline="") as f:
        fields = list(decisions[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(decisions)

    ids = [x["job_id"] for x in submitted]
    while True:
        p = run("squeue -h -j "+",".join(ids), check=False)
        if not p.stdout.strip():
            break
        time.sleep(5)

finally:
    tele.terminate()
    try:
        tele.wait(timeout=10)
    except Exception:
        tele.kill()

subprocess.run([
    "python3","collect_sacct.py","--jobs",str(rd/"jobs.csv"),
    "--out",str(rd/"sacct.csv")
], check=False)
subprocess.run(["python3","analyze_campaign.py",str(rd)], check=False)
print("FINISHED", rd)
