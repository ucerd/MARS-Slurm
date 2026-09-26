#!/usr/bin/env bash
set -euo pipefail
mkdir -p bin results
nvcc -O3 -o bin/gemm_fp16 src/gemm_fp16.cu -lcublas
nvcc -O3 -std=c++14 -o bin/gpu_mem_pressure src/gpu_mem_pressure.cu
g++ -O3 -std=c++11 -o bin/host_mem_pressure src/host_mem_pressure.cpp
mpicc -O3 -o bin/mpi_allreduce src/mpi_allreduce.c
ls -lh bin
