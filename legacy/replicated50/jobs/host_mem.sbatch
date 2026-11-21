#!/bin/bash
#SBATCH --job-name=mars_hostmem
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=96G
#SBATCH --time=00:10:00
set -e
cd /mnt/lustre/master/mars/mars_bench_suite
echo "CLASS=host_mem HOST=$(hostname) JOB=$SLURM_JOB_ID"
./bin/host_mem_pressure 88 20
