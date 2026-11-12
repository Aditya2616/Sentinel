"""Best-effort description of how busy the machine is, recorded next to timing measurements."""

from __future__ import annotations

import os
import time


def cpu_busy_percent(sample_s: float = 1.0) -> float | None:
    """System-wide CPU utilisation over a short sample, or None when it cannot be measured."""
    try:
        import psutil

        return float(psutil.cpu_percent(interval=sample_s))
    except ImportError:
        pass
    if hasattr(os, "getloadavg"):
        return min(100.0, os.getloadavg()[0] / (os.cpu_count() or 1) * 100)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class FT(ctypes.Structure):
            _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

        def sample() -> tuple[int, int, int]:
            idle, kernel, user = FT(), FT(), FT()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
            val = lambda f: (f.hi << 32) | f.lo  # noqa: E731
            return val(idle), val(kernel), val(user)

        i0, k0, u0 = sample()
        time.sleep(sample_s)
        i1, k1, u1 = sample()
        total = (k1 - k0) + (u1 - u0)  # kernel time includes idle time
        return 100.0 * (1 - (i1 - i0) / total) if total else None
    return None


def load_note() -> str:
    p = cpu_busy_percent()
    return "system load not recorded" if p is None else f"system-wide CPU utilisation {p:.0f}% just before the run"
