"""PyTorch 2.6+ compatibility for checkpoint loading.

torch.load() defaults to weights_only=True from PyTorch 2.6 onward, which breaks
loading of fairseq hubert checkpoints and RVC .pth files that rely on full
pickle unpickling.

This module monkey-patches torch.load once per process so that callers without
an explicit weights_only=... keep the pre-2.6 behavior (weights_only=False).
Call sites that set weights_only themselves are not overridden.

Only trustworthy local model files under this project's models/ directory are
loaded (hubert embedders, RVC checkpoints, training caches).
"""

import functools

_applied = False


def apply_torch_load_compat_patch():
    global _applied
    if _applied:
        return

    import torch

    _original_torch_load = torch.load

    @functools.wraps(_original_torch_load)
    def _torch_load_compat(*args, **kwargs):
        if "weights_only" not in kwargs:
            kwargs["weights_only"] = False
        return _original_torch_load(*args, **kwargs)

    torch.load = _torch_load_compat
    _applied = True


apply_torch_load_compat_patch()
