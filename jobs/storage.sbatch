#!/bin/bash
#SBATCH --job-name=mars_storage
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
set -e
cd /mnt/lustre/master/mars/mars_bench_suite
mkdir -p results/workload_data
FILE=/mnt/lustre/master/mars/mars_bench_suite/results/workload_data/${SLURM_JOB_ID}_$(hostname).dat
echo "CLASS=storage HOST=$(hostname) JOB=$SLURM_JOB_ID FILE=$FILE"
fio --name=seqwrite --filename="$FILE" --size=512M --rw=write --bs=1M --ioengine=libaio --iodepth=16 --direct=1 --fallocate=none --group_reporting
fio --name=seqread --filename="$FILE" --size=512M --rw=read --bs=1M --ioengine=libaio --iodepth=16 --direct=1 --group_reporting
rm -f "$FILE"
