import torch

print("CUDA:", torch.cuda.is_available())
print("DEVICE:", torch.cuda.get_device_name(0))

print(torch.cuda.memory_allocated())