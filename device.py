import torch

print(torch.__version__)
print(torch.version.cuda)
print("CUDA:", torch.cuda.is_available())
print(torch.cuda.device_count())
print("DEVICE:",torch.cuda.get_device_name(0))