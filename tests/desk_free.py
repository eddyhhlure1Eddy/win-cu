from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from wincu import native

IDLE_S = 45


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def main() -> int:
    import time
    deadline = time.monotonic() + (float(sys.argv[1]) if len(sys.argv) > 1 else 0)
    while True:
        code = check()
        if code == 0 or time.monotonic() >= deadline:
            return code
        time.sleep(5)


def check() -> int:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    idle = ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000
    overlays = [native.window_text(h) for h in native.enum_windows()
                if native.window_class(h) == "CodexComputerUseCursorOverlay"]
    recent = ""
    log = os.path.join(HERE, "..", "logs", "win-cu.log")
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            lines = [ln for ln in f.readlines()[-200:] if "TestForm" not in ln and " started " not in ln]
        cutoff = datetime.datetime.now() - datetime.timedelta(minutes=2)
        for line in reversed(lines):
            m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
            if m and datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") > cutoff and "-> ok" in line \
                    and not re.search(r"\b(list_windows|list_apps|get_window|get_window_state)\b", line):
                recent = line.strip()[:120]
                break
    free = idle >= IDLE_S and not overlays
    print(f"idle {idle:.0f}s | ChatGPT overlays: {overlays} | recent win-cu input (may be this test's own): {recent or 'none'} "
          f"| foreground: {native.window_text(native.foreground_window())!r} -> {'free' if free else 'busy'}")
    return 0 if free else 3


if __name__ == "__main__":
    sys.exit(main())
