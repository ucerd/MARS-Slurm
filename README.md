# MARS-Slurm

MARS-Slurm is a telemetry-driven resource-aware admission and placement
sidecar for Slurm GPU clusters.

This repository accompanies the manuscript:

**MARS-Slurm: Telemetry-Driven Memory- and Resource-Aware Admission and
Placement for Slurm GPU Clusters**

## Repository contents

- `analysis/` — MARS controller and campaign analysis tools
- `jobs/` — Slurm workload definitions used in the evaluation
- `src/` — benchmark source code and supporting scripts
- `config/` — policy configuration and frozen 50-job workload manifest
- `data/accepted/` — compact data from the six accepted experimental campaigns
- `characterization/` — platform and workload characterization measurements
- `environment/` — captured software/environment information

## Experimental dataset

The primary comparison consists of three baseline repetitions and three
MARS-Slurm repetitions. Each accepted repetition contains the fixed
50-job workload manifest.

MARS-Slurm is an external user-space admission and placement sidecar.
Slurm remains responsible for resource allocation, GRES enforcement,
job execution, and accounting.

## Metric interpretation

Slurm-resident queue wait is measured from Slurm submission to job start.

Post-submission turnaround is measured from Slurm submission to job end.

MARS admission can occur before Slurm submission. Therefore these
post-submission metrics do not include time spent waiting inside the
MARS admission controller.

GPU energy measurements represent accelerator-only energy derived from
sampled GPU power telemetry and do not represent whole-node or
whole-cluster energy consumption.

## Data availability

Compact experimental data are included in this repository.

A permanent archival dataset containing the complete raw experimental
artifacts will be linked here after archival publication.

## Citation

Citation metadata will be updated when the associated article and
archival dataset identifiers become available.
