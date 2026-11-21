#!/bin/bash
#SBATCH --job-name=mars_gpumem
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
set -e
cd /mnt/lustre/master/mars/mars_bench_suite
source /usr/share/lmod/lmod/init/bash
module purge
module load cuda/12.2
echo "CLASS=gpu_mem HOST=$(hostname) JOB=$SLURM_JOB_ID"
./bin/gpu_mem_pressure 10000 20
