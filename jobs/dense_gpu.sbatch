#!/bin/bash
#SBATCH --job-name=mars_dense
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
set -e
cd /mnt/lustre/master/mars/mars_bench_suite
source /usr/share/lmod/lmod/init/bash
module purge
module load cuda/12.2
echo "CLASS=dense_gpu HOST=$(hostname) JOB=$SLURM_JOB_ID"
./bin/gemm_fp16 8192 1500
