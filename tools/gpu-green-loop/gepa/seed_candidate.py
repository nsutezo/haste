"""Seed inference kernel for GEPA GPU search."""

import torch


def predict_batch(
    task: torch.nn.Module,
    images: torch.Tensor,
    device: torch.device,
) -> torch.Tensor:
    """Run one inference batch using A100 BF16 tensor cores."""
    with torch.amp.autocast("cuda", dtype=torch.bfloat16):
        return task(images.to(device, non_blocking=True))
