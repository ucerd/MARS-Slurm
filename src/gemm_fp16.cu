#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <cublas_v2.h>
#define CUDA_OK(x) do{cudaError_t e=(x);if(e!=cudaSuccess){fprintf(stderr,"CUDA %s\n",cudaGetErrorString(e));return 1;}}while(0)
#define CUBLAS_OK(x) do{cublasStatus_t s=(x);if(s!=CUBLAS_STATUS_SUCCESS){fprintf(stderr,"CUBLAS status=%d\n",(int)s);return 1;}}while(0)
__global__ void initv(__half* p,size_t n,float v){size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;if(i<n)p[i]=__float2half(v);} 
int main(int argc,char**argv){
 int N=argc>1?atoi(argv[1]):8192; int reps=argc>2?atoi(argv[2]):20; size_t elems=(size_t)N*N, bytes=elems*sizeof(__half);
 cudaDeviceProp prop{}; CUDA_OK(cudaGetDeviceProperties(&prop,0)); printf("GPU=%s N=%d reps=%d\n",prop.name,N,reps);
 __half *A,*B,*C; CUDA_OK(cudaMalloc(&A,bytes)); CUDA_OK(cudaMalloc(&B,bytes)); CUDA_OK(cudaMalloc(&C,bytes));
 int th=256; int bl=(int)((elems+th-1)/th); initv<<<bl,th>>>(A,elems,0.5f); initv<<<bl,th>>>(B,elems,0.25f); CUDA_OK(cudaMemset(C,0,bytes)); CUDA_OK(cudaDeviceSynchronize());
 cublasHandle_t h; CUBLAS_OK(cublasCreate(&h)); CUBLAS_OK(cublasSetMathMode(h,CUBLAS_TENSOR_OP_MATH)); float a=1.0f,b=0.0f;
 for(int i=0;i<5;i++) CUBLAS_OK(cublasGemmEx(h,CUBLAS_OP_N,CUBLAS_OP_N,N,N,N,&a,A,CUDA_R_16F,N,B,CUDA_R_16F,N,&b,C,CUDA_R_16F,N,CUBLAS_COMPUTE_32F,CUBLAS_GEMM_DEFAULT_TENSOR_OP));
 CUDA_OK(cudaDeviceSynchronize()); cudaEvent_t st,en; CUDA_OK(cudaEventCreate(&st)); CUDA_OK(cudaEventCreate(&en)); CUDA_OK(cudaEventRecord(st));
 for(int i=0;i<reps;i++) CUBLAS_OK(cublasGemmEx(h,CUBLAS_OP_N,CUBLAS_OP_N,N,N,N,&a,A,CUDA_R_16F,N,B,CUDA_R_16F,N,&b,C,CUDA_R_16F,N,CUBLAS_COMPUTE_32F,CUBLAS_GEMM_DEFAULT_TENSOR_OP));
 CUDA_OK(cudaEventRecord(en)); CUDA_OK(cudaEventSynchronize(en)); float ms=0; CUDA_OK(cudaEventElapsedTime(&ms,st,en)); double sec=(ms/1000.0)/reps; double flops=2.0*(double)N*N*N; printf("mean_seconds=%.6f TFLOPS=%.3f\n",sec,flops/sec/1e12);
 cublasDestroy(h); cudaFree(A);cudaFree(B);cudaFree(C); return 0; }
