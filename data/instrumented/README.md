# Instrumented experimental datasets

Original files are retained without modifying numeric observations. The reported campaign summary CSV is generated from the six primary `summary.json` files and verified against `job_metrics.csv` (valid completed jobs only). Full precision is retained in the CSV. See `../../docs/data_verification.txt`.

- `compute40/`: three reported 40-job compute-focused campaigns, 40/40 completed each; manuscript Table 5.
- `mixed25/`: three reported 25-job mixed-resource campaigns; native and full MARS complete 25/25, feasibility-only 22/25 (three storage timeouts); manuscript Table 7. The baseline snapshot predates the collector fix, but native submission does not invoke the placement collector.
- `audit/`: incomplete and diagnostic runs, storage diagnostics and controller logs. Missing summaries or accounting files are preserved as missing, not fabricated. In particular, the pre-fix MARS configurations each submitted 20/25 jobs; the other five encountered admission timeouts. These are not reported successful campaigns. Storage stalls do not establish a defective node or a policy-induced failure.
- `cluster_source_hashes.txt`: unchanged source-checksum list from the server, with original experiment-relative paths.

Run directories contain the original snapshots, manifest, settings, release/jobs/accounting data, summary, job stdout/stderr and monitoring where present. The compute-focused campaigns contain GPU samples and raw estimates; the exploratory admission-only campaign has no samples. The manuscript does not evaluate instrumented utilization or energy effects. Do not interpret raw estimates as validated comparative energy evidence.

`pre_submit_delay_s` measures release to successful sbatch acknowledgement, not exactly Slurm Submit. Decision time is included in that interval. Cross-clock timestamps differ in precision. Makespan is measured from first planned release to final completion, and is null for incomplete workloads. Separate the protocols rather than pool them.
