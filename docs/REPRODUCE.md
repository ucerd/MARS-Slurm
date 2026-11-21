# Reproduction and offline verification

## Offline analysis (no Slurm jobs submitted)

From the repository root, run:

```sh
python3 analysis/verify_release.py
python3 analysis/inspect_instrumented_runs.py data/instrumented
sha256sum -c SHA256SUMS
```

The first command verifies the means and sample standard deviations in the published campaign summaries against saved job metrics, snapshot provenance, and the replicated aggregate against the six archived summaries. It does not require Slurm or CUDA. Checksums are for this exact distribution; edit only in a separate working copy.

## Original experimental environment

Slurm 22.05.9, Rocky Linux 9-series, three workers (node02–node04), each with Slurm-advertised 80 logical CPUs, 125 GiB memory, RTX 4070 Ti, 10-GbE, shared Lustre 2.16.0. Linux `nproc` may vary from advertised CPU count. Refer to `environment/` and `characterization/`. The policy uses a site-specific interface subnet and assumes trusted node names and SSH access. When Slurm allocation-memory fields cannot be obtained, the implementation falls back to Linux memory observations; this is not hard memory enforcement. Review all site-specific paths and shell usage before adapting.

The exact executed scripts retain original filenames, comments, and default output roots. The 40- and 25-job scripts validate their own workload counts even though inherited docstrings/error messages refer to 50 jobs. Explicitly set the manifest and output root. The archived source must not be substituted for the corrected policy in new experiments.

## Site-specific staging and dry run

The job scripts reference `/mnt/lustre/master/mars/mars_bench_suite`. The build script expects the benchmark sources under `src/`, while the Python AI benchmark is located at the benchmark root. Do not overwrite the original experiment. On an authorized test installation, prepare that layout with copies of the source files, CUDA, MPI, fio, Lmod and PyTorch modules as documented by the original environment. Build from the benchmark root with `bash src/build.sh` (copy the build script there if using the original layout), and put `src/ai_train_bench.py` at the benchmark root. The benchmark scripts use fixed paths; adapt them explicitly for other sites. Do not submit jobs until the allocated nodes are idle and permission is granted.

From a separate working directory on the controller, with `REPO` set to the absolute checkout path:

```sh
cp "$REPO"/analysis/{mars_policy,campaign_telemetry,run_reviewer1_compute40,run_reviewer1_pilot,run_reviewer1_validation}.py .
cp "$REPO"/config/{policy.json,workload_manifest_compute40.csv,pilot_25_jobs_precreated.csv,workload_manifest_precreated.csv} .
cp -a "$REPO/jobs" .
python3 run_reviewer1_compute40.py --mode baseline --rep 1 \
  --manifest workload_manifest_compute40.csv --policy policy.json \
  --out-root results/compute40 --cadence 2 --max-admission-sec 900 --dry-run
```

The dry run checks manifest rows and script paths and requires Slurm executables, but does not submit jobs. For an authorized rerun, remove `--dry-run`, then repeat sequentially with `--mode admission_only` and `--mode mars`, allowing the pool to drain. For the 25-job protocol select `run_reviewer1_pilot.py` and `pilot_25_jobs_precreated.csv`, with a separate output root. The validation driver and precreated 50-job manifest are provided for provenance/diagnostics; no complete new 50-job comparison is claimed. The original replicated dataset uses the separate historical serial-release protocol and must not be pooled with instrumented data. Repeating the evaluation with the corrected implementation, balanced execution order and additional independent repetitions is recommended for stronger inference.

The current scripts were verified offline for syntax and data consistency; no live cluster run or hardware validation was performed during packaging. Source and log snapshots include the original local paths and infrastructure identifiers; confirm these are acceptable for public release.
