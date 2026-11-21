import shlex
#!/usr/bin/env python3
import subprocess, concurrent.futures, re

def run(cmd, timeout=8):
    try:
        return subprocess.run(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=e.stdout or "",
            stderr=f"TIMEOUT after {timeout}s"
        )

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def slurm_states(nodes):
    p = run("sinfo -N -h -o '%N|%T'")
    states = {}
    for line in p.stdout.splitlines():
        if "|" in line:
            n, s = line.strip().split("|", 1)
            states[n] = s.lower()
    return {n: states.get(n, "unknown") for n in nodes}

def query_node(node):
    remote = (
        "set -e; "
        "echo MEM $(free -b | awk '/Mem:/ {print $2, $7}'); "
        "echo LOAD $(awk '{print $1}' /proc/loadavg) $(nproc); "
        "echo LUSTRE $(df -Pk /mnt/lustre | tail -1 | awk '{print $4}'); "
        "echo GPU $(nvidia-smi --query-gpu=memory.total,memory.free,utilization.gpu,power.draw,temperature.gpu "
        "--format=csv,noheader,nounits | head -1); "
        "echo IPADDR_BEGIN; ip -o -4 addr show; echo IPADDR_END"
    )
    cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=3 {node} {shlex.quote(remote)}"
    p = run(cmd, timeout=20)
    if p.returncode != 0:
        return {"node": node, "ok": False, "error": p.stderr.strip()}

    d = {"node": node, "ok": True}
    lines = p.stdout.splitlines()
    iface = ""
    for line in lines:
        if line.startswith("MEM "):
            _, total, avail = line.split()
            d["mem_total_gib"] = int(total) / (1024**3)
            d["mem_avail_gib"] = int(avail) / (1024**3)
        elif line.startswith("LOAD "):
            _, load1, ncpu = line.split()
            d["load1"] = float(load1)
            d["ncpu"] = int(ncpu)
        elif line.startswith("LUSTRE "):
            _, kb = line.split()
            d["lustre_free_gib"] = int(kb) / (1024**2)
        elif line.startswith("GPU "):
            vals = [x.strip() for x in line[4:].split(",")]
            d["gpu_total_gib"] = float(vals[0]) / 1024.0
            d["gpu_free_gib"] = float(vals[1]) / 1024.0
            d["gpu_util"] = float(vals[2])
            d["gpu_power_w"] = float(vals[3])
            d["gpu_temp_c"] = float(vals[4])
        if "192.168.20." in line:
            parts = line.split()
            if len(parts) >= 2 and not iface:
                iface = parts[1]

    # Slurm schedulable memory is used for the HARD placement constraint.
    # Linux MemAvailable remains observational telemetry.
    q = run(f"scontrol show node {node} -o", timeout=5)

    m_real = re.search(r"RealMemory=(\d+)", q.stdout)
    m_alloc = re.search(r"AllocMem=(\d+)", q.stdout)

    if m_real and m_alloc:
        real_mb = float(m_real.group(1))
        alloc_mb = float(m_alloc.group(1))

        d["slurm_real_memory_gib"] = real_mb / 1024.0
        d["slurm_alloc_memory_gib"] = alloc_mb / 1024.0
        d["slurm_free_memory_gib"] = (real_mb - alloc_mb) / 1024.0
    else:
        d["slurm_real_memory_gib"] = d["mem_total_gib"]
        d["slurm_alloc_memory_gib"] = 0.0
        d["slurm_free_memory_gib"] = d["mem_avail_gib"]

    d["iface"] = iface
    d["net_mbps"] = 0.0
    if iface:
        q = run(
            f"ssh -o BatchMode=yes -o ConnectTimeout=3 {node} "
            f"'cat /sys/class/net/{iface}/speed 2>/dev/null || echo 0'",
            timeout=5
        )
        try:
            d["net_mbps"] = float(q.stdout.strip().splitlines()[-1])
        except Exception:
            d["net_mbps"] = 0.0
    return d

def collect(nodes):
    states = slurm_states(nodes)
    out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as ex:
        futs = {ex.submit(query_node, n): n for n in nodes}
        for fut in concurrent.futures.as_completed(futs):
            d = fut.result()
            d["slurm_state"] = states.get(d["node"], "unknown")
            out.append(d)
    return sorted(out, key=lambda x: x["node"])

def choose_node(spec, policy, active_jobs):
    nodes = policy["candidate_nodes"]
    guards = policy["guards"]
    weights = policy["weights"][spec["class"]]
    telemetry = collect(nodes)

    pending = {n: {"mem":0.0,"gpus":0,"gpu_mem":0.0} for n in nodes}
    running_gpu = {n: 0 for n in nodes}
    for a in active_jobs:
        n = a.get("node")
        if n not in pending:
            continue
        if a.get("state") == "PENDING":
            pending[n]["mem"] += float(a.get("mem_gib", 0))
            pending[n]["gpus"] += int(a.get("gpus", 0))
            pending[n]["gpu_mem"] += float(a.get("gpu_mem_gib", 0))
        elif a.get("state") == "RUNNING":
            running_gpu[n] += int(a.get("gpus", 0))

    candidates = []
    for d in telemetry:
        n = d["node"]
        rec = {"node":n,"telemetry":d,"feasible":False,"reason":"","score":-1.0}
        if not d.get("ok"):
            rec["reason"] = "telemetry_failed"
            candidates.append(rec)
            continue

        st = d.get("slurm_state", "")
        if any(x in st for x in ("down","drain","fail","maint","unk")):
            rec["reason"] = f"slurm_state={st}"
            candidates.append(rec)
            continue

        if d.get("lustre_free_gib", 0) < guards["lustre_free_gib"]:
            rec["reason"] = "lustre_guard"
            candidates.append(rec)
            continue

        if d.get("gpu_temp_c", 999) > guards["max_gpu_temp_c"]:
            rec["reason"] = "thermal_guard"
            candidates.append(rec)
            continue

        p = pending[n]
        req_mem = float(spec["mem_gib"])
        # Capacity feasibility follows Slurm allocation state rather than
        # Linux MemAvailable, which can vary because of reclaimable cache.
        effective_mem = d["slurm_free_memory_gib"] - p["mem"]
        if effective_mem < req_mem + guards["host_memory_gib"]:
            rec["reason"] = "host_memory_guard"
            candidates.append(rec)
            continue

        if int(spec["gpus"]) > 0:
            if p["gpus"] > 0 or running_gpu[n] > 0:
                rec["reason"] = "gpu_reserved"
                candidates.append(rec)
                continue
            effective_gpu = d["gpu_free_gib"] - p["gpu_mem"]
            if effective_gpu < float(spec["gpu_mem_gib"]) + guards["gpu_memory_gib"]:
                rec["reason"] = "gpu_memory_guard"
                candidates.append(rec)
                continue

        host_headroom = clamp(
            (effective_mem - req_mem - guards["host_memory_gib"]) /
            max(d.get("slurm_real_memory_gib", d["mem_total_gib"]), 1.0)
        )
        if int(spec["gpus"]) > 0:
            gpu_headroom = clamp(
                (d["gpu_free_gib"] - float(spec["gpu_mem_gib"]) - guards["gpu_memory_gib"]) /
                max(d["gpu_total_gib"], 1.0)
            )
            gpu_idle = clamp(1.0 - d["gpu_util"]/100.0)
        else:
            gpu_headroom = 1.0
            gpu_idle = 1.0

        terms = {
            "host_headroom": host_headroom,
            "gpu_headroom": gpu_headroom,
            "gpu_idle": gpu_idle,
            "network": clamp(d.get("net_mbps", 0.0)/10000.0),
            "load_idle": clamp(1.0 - d.get("load1", 0.0)/max(d.get("ncpu", 1), 1)),
            "thermal": clamp(1.0 - d.get("gpu_temp_c", guards["max_gpu_temp_c"]) /
                             guards["max_gpu_temp_c"]),
        }
        score = sum(float(weights[k]) * terms[k] for k in weights)
        rec.update({"feasible":True,"reason":"ok","score":score,"terms":terms})
        candidates.append(rec)

    feasible = [x for x in candidates if x["feasible"]]
    if not feasible:
        return None, candidates
    feasible.sort(key=lambda x: (-x["score"], x["node"]))
    return feasible[0], candidates
