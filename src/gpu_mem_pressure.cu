#include <cstdio>
#include <cstdlib>
#include <thread>
#include <chrono>
#include <cuda_runtime.h>
int main(int argc,char**argv){if(argc<3){fprintf(stderr,"usage: %s MiB seconds\n",argv[0]);return 2;} long m=atol(argv[1]);int s=atoi(argv[2]);size_t b=(size_t)m*1024ull*1024ull;void*p=nullptr;cudaError_t e=cudaMalloc(&p,b);if(e!=cudaSuccess){fprintf(stderr,"cudaMalloc %ld MiB failed: %s\n",m,cudaGetErrorString(e));return 3;} e=cudaMemset(p,0xA5,b);if(e!=cudaSuccess){fprintf(stderr,"cudaMemset failed: %s\n",cudaGetErrorString(e));return 4;} cudaDeviceSynchronize();printf("allocated_gpu_mib=%ld hold_seconds=%d\n",m,s);fflush(stdout);std::this_thread::sleep_for(std::chrono::seconds(s));cudaFree(p);return 0;}
