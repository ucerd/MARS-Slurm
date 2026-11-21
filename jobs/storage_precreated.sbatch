#!/bin/bash
#SBATCH --job-name=mars_storage
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00

set -euo pipefail

cd /mnt/lustre/master/mars/mars_bench_suite

mkdir -p results/workload_data

FILE="/mnt/lustre/master/mars/mars_bench_suite/results/workload_data/${SLURM_JOB_ID}_$(hostname).dat"

echo "CLASS=storage"
echo "HOST=$(hostname)"
echo "JOB=$SLURM_JOB_ID"
echo "FILE=$FILE"

# Remove temporary file on normal shell exit.
trap 'rm -f "$FILE"' EXIT

echo "FILE_SETUP_BEGIN=$(date -Ins)"

# Create a sparse 512-MiB file before starting fio.
truncate -s 512M "$FILE"

echo "FILE_SETUP_END=$(date -Ins)"

echo "FIO_WRITE_BEGIN=$(date -Ins)"

fio \
  --name=seqwrite \
  --filename="$FILE" \
  --size=512M \
  --rw=write \
  --bs=1M \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --fallocate=none \
  --allow_file_create=0 \
  --group_reporting

echo "FIO_WRITE_END=$(date -Ins)"

echo "FIO_READ_BEGIN=$(date -Ins)"

fio \
  --name=seqread \
  --filename="$FILE" \
  --size=512M \
  --rw=read \
  --bs=1M \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --allow_file_create=0 \
  --group_reporting

echo "FIO_READ_END=$(date -Ins)"

echo "STORAGE_JOB_COMPLETED=$(date -Ins)"
