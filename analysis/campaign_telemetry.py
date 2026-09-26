#!/usr/bin/env python3
import argparse, subprocess, concurrent.futures, csv, time, signal
from pathlib import Path

stop = False
def handler(*_):
    global stop
    stop = True

signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

def query(node):
    cmd = (
        f"ssh -o BatchMode=yes -o ConnectTimeout=3 {node} "
        "\"nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu "
        "--format=csv,noheader,nounits | head -1\""
    )
    try:
        p = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=5)
        if p.returncode != 0:
            return node, None
        v = [x.strip() for x in p.stdout.strip().split(",")]
        return node, (float(v[0]), float(v[1]), float(v[2]), float(v[3]))
    except Exception:
        return node, None

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--nodes", nargs="+", required=True)
ap.add_argument("--interval", type=float, default=2.0)
a = ap.parse_args()

Path(a.out).parent.mkdir(parents=True, exist_ok=True)
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["epoch","node","gpu_util_pct","memory_used_mib","power_w","temp_c"])
    f.flush()
    while not stop:
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(a.nodes)) as ex:
            for node, val in ex.map(query, a.nodes):
                if val:
                    w.writerow([f"{start:.6f}", node, *val])
        f.flush()
        time.sleep(max(0.0, a.interval - (time.time()-start)))
