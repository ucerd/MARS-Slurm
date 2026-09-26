#!/usr/bin/env python3
import argparse, csv, subprocess, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--jobs", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

jobs = list(csv.DictReader(open(a.jobs)))
fields = ["job_id","jobtag","class","mode","selected_node","State","Submit","Start","End",
          "ElapsedRaw","NodeList","ExitCode","AllocTRES","ReqMem"]
rows = []

for j in jobs:
    jid = j["job_id"]
    cmd = ["sacct","-j",jid,"-n","-P",
           "--format=JobIDRaw,State,Submit,Start,End,ElapsedRaw,NodeList,ExitCode,AllocTRES,ReqMem"]
    best = None
    for _ in range(10):
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in p.stdout.splitlines():
            parts = line.split("|")
            if parts and parts[0] == jid and len(parts) >= 10:
                best = parts[:10]
                break
        if best:
            break
        time.sleep(2)

    if best:
        _, state, submit, start, end, elapsed, nodelist, exitcode, alloctres, reqmem = best
    else:
        state = submit = start = end = elapsed = nodelist = exitcode = alloctres = reqmem = ""

    rows.append({
        "job_id":jid,"jobtag":j["jobtag"],"class":j["class"],"mode":j["mode"],
        "selected_node":j.get("selected_node",""),"State":state,"Submit":submit,"Start":start,
        "End":end,"ElapsedRaw":elapsed,"NodeList":nodelist,"ExitCode":exitcode,
        "AllocTRES":alloctres,"ReqMem":reqmem
    })

Path(a.out).parent.mkdir(parents=True, exist_ok=True)
with open(a.out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
