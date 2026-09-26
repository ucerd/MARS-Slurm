#include <cstdio>
#include <cstdlib>
#include <unistd.h>
#include <thread>
#include <chrono>
int main(int argc,char**argv){if(argc<3){fprintf(stderr,"usage: %s GiB seconds\n",argv[0]);return 2;}double g=atof(argv[1]);int s=atoi(argv[2]);size_t b=(size_t)(g*1024.0*1024.0*1024.0);unsigned char*p=(unsigned char*)malloc(b);if(!p){perror("malloc");return 3;}long pg=sysconf(_SC_PAGESIZE);for(size_t i=0;i<b;i+=(size_t)pg)p[i]=(unsigned char)(i&255);printf("allocated_host_gib=%.2f hold_seconds=%d\n",g,s);fflush(stdout);std::this_thread::sleep_for(std::chrono::seconds(s));free(p);return 0;}
