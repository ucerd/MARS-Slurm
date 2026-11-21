# MARS-Slurm

**Telemetry-driven resource-aware admission and placement for Slurm GPU clusters**

MARS-Slurm is an open-source Python user-space sidecar that combines live resource telemetry, hard feasibility guards and workload-class-specific normalized ranking with standard Slurm job submission. Slurm retains authority over resource allocation, GRES assignment, task launch, execution and accounting. No changes to `slurmctld` are required.

This artifact accompanies the manuscript **Telemetry-Driven Resource-Aware Job Handling in Slurm GPU Clusters: An Open-Source Admission and Placement Framework**, prepared for *Concurrency and Computation: Practice and Experience*.

## Architecture

1. Collect live Slurm, Linux, GPU, Lustre and network-link observations for the candidate node pool.
2. Check node state, schedulable host memory with pending reservations, GPU availability and memory, shared-storage capacity and temperature. Network-link capability is a ranking input, not a separate hard guard.
3. Rank feasible nodes using workload-class-specific normalized weights. If no feasible node exists, defer admission and retry after 2 s.
4. Submit a single-node job through native `sbatch`; full MARS pins one feasible node using `--nodelist`. Record decision context and Slurm accounting.

The experimental pool is node02–node04, each with 80 logical CPUs, approximately 125 GiB Slurm-advertised memory, one RTX 4070 Ti GPU (12,282 MiB), and 10-GbE connectivity. The evaluation uses Slurm 22.05.9, Rocky Linux 9-series, CUDA 12.2 and shared Lustre 2.16.0. The prototype is designed for single-node jobs with exclusive GPU allocation; it does not implement multinode placement, GPU sharing, migration or automatic workload classification.

## Repository contents

- `analysis/` — policy implementation, campaign runners and analysis utilities
- `config/` — unchanged policy configuration and workload manifests for the 50-, 40- and 25-job protocols
- `jobs/` — Slurm workload definitions; the precreated-file storage variant is used for the exploratory mixed-resource protocol
- `src/` — benchmark sources and build scripts
- `data/accepted/` — six completed 50-job campaigns, including original job logs from the frozen archive
- `data/instrumented/` — original 25- and 40-job campaign records, audit attempts and generated summary CSV
- `legacy/` — frozen historical policy and diagnostic code (not the current implementation)
- `data/replicated50_audit/` — excluded historical run and driver logs
- `docs/` — reproduction, validation and release provenance
- `characterization/`, `environment/` — platform characterization and software/environment records

## Experimental protocols

| Protocol | Configurations | Campaigns | Scope |
|---|---|---|---|
| Compute-focused | Native Slurm, feasibility-only, full MARS | One per mode; 40 jobs each | Ten jobs each of dense GPU, AI training, GPU-memory and host-memory pressure |
| Exploratory mixed-resource | Same three modes | One reported campaign per mode; 25 jobs each | Five jobs each of the preceding four classes and Lustre I/O |
| Replicated mixed-resource | Native Slurm, MARS | Three completed campaigns per mode; 50 jobs each | Ten jobs per class including Lustre I/O; submission-based accounting and GPU monitoring |

The instrumented comparison uses independently scheduled release events at a nominal 2-s cadence, a 2-s retry interval, and a 900-s admission timeout. Native Slurm uses the common three-node pool. Feasibility-only admission restricts Slurm's candidate set using `--exclude`, without using the ranking to choose a single node. Full MARS selects one node via `--nodelist`. The two MARS modes also differ in controller-side node reservation tracking; this is not an isolated ranking ablation.

## Compute-focused experimental results (40 jobs per campaign)

| Metric | Native Slurm | Feasibility-only | Full MARS |
|---|---:|---:|---:|
| Successful jobs | 40/40 | 40/40 | 40/40 |
| End − Eligible (s) | 97.35 | 167.65 | 31.53 |
| End − Submit (s) | 97.35 | 167.65 | 31.53 |
| Start − Eligible (s, derived) | 67.50 | 137.15 | 1.13 |
| End − Release (s) | 97.32 | 168.02 | 100.40 |
| Release-to-acknowledgement delay (s) | 0.009 | 0.746 | 69.327 |
| End − Start (s) | 29.85 | 30.50 | 30.40 |
| Controller decision time (s) | 0.00 | 0.74 | 5.51 |
| Campaign makespan (s) | 257.97 | 428.37 | 261.33 |

Full MARS reduced Slurm eligibility-to-start waiting by 98.33% and eligibility-to-completion time by 67.62% in the observed campaign. Complete turnaround and makespan were 3.17% and 1.30% higher than native Slurm, respectively, and 40.2% and 39.0% lower than feasibility-only admission. Execution times were comparable. These single-campaign observations are descriptive, not evidence of statistical equivalence or universal speedup.

## Exploratory mixed-resource results (25 jobs per campaign)

| Metric | Native Slurm | Feasibility-only | Full MARS |
|---|---:|---:|---:|
| Successful jobs | 25/25 | 22/25 | 25/25 |
| End − Eligible (s) | 55.04 | 82.82 | 26.64 |
| End − Release (s) | 54.10 | 82.73 | 47.93 |
| Release-to-acknowledgement delay (s) | 0.010 | 0.744 | 21.791 |
| End − Start (s) | 26.16 | 29.95 | 25.56 |
| Controller decision time (s) | 0.00 | 0.74 | 3.72 |
| Campaign makespan (s) | 159.06 | — | 137.85 |

Feasibility-only timing means are over the 22 successful jobs; they are not directly comparable with the full 25-job means. No complete-workload makespan is reported for that run.

In the exploratory 25-job protocol, full MARS exhibited 11.4% lower complete turnaround and 13.3% lower makespan relative to native Slurm. Both completed 25/25 jobs; feasibility-only completed 22/25, with three Lustre write timeouts. The failed samples are retained, not imputed. The replicated 50-job protocol exhibited lower post-submission latency but an 11.84% higher makespan under MARS. The protocols differ in composition, instrumentation and replication and must not be pooled.

## Replicated mixed-resource results (50 jobs per campaign)

| Metric (mean ± sample SD across three campaigns) | Native Slurm | MARS-Slurm |
|---|---:|---:|
| Submit-to-start waiting (s) | 66.06 ± 2.55 | 1.50 ± 0.09 |
| End − Submit (s) | 91.51 ± 3.63 | 27.04 ± 0.41 |
| Execution (s) | 25.45 ± 1.19 | 25.54 ± 0.48 |
| Makespan (s) | 276.00 ± 13.75 | 308.67 ± 9.07 |
| GPU utilization (%) | 50.91 ± 0.66 | 45.74 ± 1.67 |
| Accelerator energy (kWh) | 0.024400 ± 0.000719 | 0.024377 ± 0.000156 |

These are accounting and monitoring observations from the historical collector variant. They do not establish end-to-end turnaround or validated node-specific placement.

## Telemetry provenance

The placement collector used by the reported external admission and full-MARS configurations uses `shlex.quote` for the remote SSH command, preventing local shell evaluation of node telemetry expressions. The collector variant used in the archived 50-job experiments lacked this protection. A diagnostic comparison showed 5,978 MiB free GPU memory from the affected collector versus 11,885 MiB measured directly on the workers. With shell-safe quoting and unchanged guards, the idle workers satisfied the GPU-memory feasibility test. Archived submission-based accounting and monitoring observations are retained, but they do not establish correctly measured node-specific placement. Reproduce the archived experiment only using its corresponding archived software version; do not equate it with the corrected implementation.

## Reproduction

See [docs/REPRODUCE.md](docs/REPRODUCE.md) for exact site layout, dry-run commands, offline analysis and limitations. The published instrumented drivers are byte-identical to their saved campaign snapshots; source hashes, original campaign records, and the historical policy variant are included. No reconstructed driver is used in this release.

## Metric definitions

- End − Release: end-to-end completion time, including external admission waiting (instrumented protocols).
- End − Eligible: time from Slurm eligibility to completion.
- Start − Eligible: Slurm-resident eligibility-to-start wait.
- End − Submit: post-submission turnaround, excluding external admission waiting.
- Release-to-acknowledgement delay: external release to successful `sbatch` acknowledgement; cumulative controller decision time is included, not added again.
- End − Start: Slurm-recorded execution interval, including job startup and cleanup.
- Makespan: first planned release to last completion in the instrumented protocols; first submission to final completion in the archived 50-job protocol.
- Accelerator energy: integration of sampled GPU power, not whole-node or cluster energy. Manuscript utilization and energy analysis is restricted to the replicated 50-job protocol. Some instrumented summaries also retain raw GPU samples and computed estimates; the mixed25 admission-only run has no GPU samples. These estimates are not part of the manuscript performance claims.

Slurm accounting has second-level resolution; controller release timestamps include fractions of a second. Negative fractional release-to-eligibility discrepancies can arise from this resolution difference. Latency averages exclude unsuccessful jobs; report completion rates and distinguish incomplete campaign makespan. No claims are made of general throughput improvement, reduced controller overhead, application acceleration, or isolated thermal/storage reliability benefits.

## Data and code availability

The actual cluster-exported experiment code, configuration, workload manifests, accounting and release records, raw monitoring samples, job logs and diagnostic attempts are included here. The six replicated runs are preserved under `data/accepted/`, and the instrumented datasets under `data/instrumented/`. The incomplete campaigns are retained separately and excluded from the corresponding complete-workload comparisons. See [data/instrumented/README.md](data/instrumented/README.md) and [docs/REPRODUCE.md](docs/REPRODUCE.md). No archival DOI has been assigned in the supplied materials.

## Citation and license

Use `CITATION.cff` for software citation, and cite the associated manuscript when bibliographic details become available. The software uses the MIT License; see `LICENSE`.
