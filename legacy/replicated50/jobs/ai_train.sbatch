#!/bin/bash
#SBATCH --job-name=mars_ai
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
set -e
cd /mnt/lustre/master/mars/mars_bench_suite
source /usr/share/lmod/lmod/init/bash
module purge
module load pytorch/2.5.1
echo "CLASS=ai_train HOST=$(hostname) JOB=$SLURM_JOB_ID"
python3 ai_train_bench.py --batch-size 32 --warmup 20 --steps 500
