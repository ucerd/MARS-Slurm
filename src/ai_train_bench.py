import os
import time
import argparse

import torch
import torch.nn as nn
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torchvision.models import resnet50


parser = argparse.ArgumentParser()
parser.add_argument("--batch-size", type=int, default=32)
parser.add_argument("--warmup", type=int, default=20)
parser.add_argument("--steps", type=int, default=100)
parser.add_argument("--image-size", type=int, default=224)
parser.add_argument("--classes", type=int, default=1000)
parser.add_argument("--fp32", action="store_true")
args = parser.parse_args()


world_size = int(os.environ.get("WORLD_SIZE", "1"))
rank = int(os.environ.get("RANK", "0"))
local_rank = int(os.environ.get("LOCAL_RANK", "0"))

distributed = world_size > 1

torch.cuda.set_device(local_rank)
device = torch.device("cuda", local_rank)

if distributed:
    dist.init_process_group(
        backend="nccl",
        init_method="env://",
        rank=rank,
        world_size=world_size
    )

torch.backends.cudnn.benchmark = True
torch.manual_seed(1234 + rank)

model = resnet50(weights=None, num_classes=args.classes)
model = model.to(device)

if distributed:
    model = DDP(
        model,
        device_ids=[local_rank],
        output_device=local_rank
    )

optimizer = torch.optim.SGD(
    model.parameters(),
    lr=0.01,
    momentum=0.9
)

criterion = nn.CrossEntropyLoss()

# Fixed synthetic tensors remove filesystem/dataloader effects.
images = torch.randn(
    args.batch_size,
    3,
    args.image_size,
    args.image_size,
    device=device
)

targets = torch.randint(
    0,
    args.classes,
    (args.batch_size,),
    device=device
)

use_amp = not args.fp32

if use_amp:
    scaler = torch.amp.GradScaler("cuda")


def train_step():
    optimizer.zero_grad(set_to_none=True)

    if use_amp:
        with torch.amp.autocast(
            "cuda",
            dtype=torch.float16
        ):
            outputs = model(images)
            loss = criterion(outputs, targets)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

    else:
        outputs = model(images)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

    return loss


# Warm-up
for _ in range(args.warmup):
    train_step()

torch.cuda.synchronize()

if distributed:
    dist.barrier()

torch.cuda.reset_peak_memory_stats()

start = time.perf_counter()

last_loss = None

for _ in range(args.steps):
    last_loss = train_step()

torch.cuda.synchronize()

if distributed:
    dist.barrier()

elapsed = time.perf_counter() - start

local_images = args.batch_size * args.steps
global_images = local_images * world_size

throughput = global_images / elapsed
step_ms = elapsed / args.steps * 1000.0

peak_mem_gib = (
    torch.cuda.max_memory_allocated(device)
    / (1024 ** 3)
)

if rank == 0:
    print("===== AI TRAINING BENCHMARK =====")
    print("model=ResNet50")
    print(f"world_size={world_size}")
    print(f"batch_per_gpu={args.batch_size}")
    print(f"global_batch={args.batch_size * world_size}")
    print(f"precision={'FP32' if args.fp32 else 'AMP_FP16'}")
    print(f"warmup_steps={args.warmup}")
    print(f"measured_steps={args.steps}")
    print(f"elapsed_seconds={elapsed:.6f}")
    print(f"mean_step_ms={step_ms:.3f}")
    print(f"throughput_images_per_sec={throughput:.3f}")
    print(f"peak_gpu_memory_GiB={peak_mem_gib:.3f}")
    print(f"final_loss={last_loss.item():.6f}")
    print(
        "gpu=",
        torch.cuda.get_device_name(local_rank)
    )

if distributed:
    dist.destroy_process_group()
