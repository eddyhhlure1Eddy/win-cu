from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from harness import HERE, LOG, close_forms, log_lines, native

TASK = ("A window titled 'WinCU Test Form' is open on this PC. With the win-cu tools: click the Alpha button, "
        "tick 'Enable feature', type \u4f60\u597d Claude into the Name box, choose Blue in the dropdown list, and click the "
        "red square numbered 5 on the white canvas. Then tell me, in one line, the text shown in the status bar "
        "at the bottom-left of that window. Work efficiently.")
WANTED = {"Alpha clicked": r"^button Alpha$", "feature ticked": r"^check True$", "name typed": "^name \u4f60\u597d Claude$",
          "Blue chosen": r"^combo Blue$", "target 5 clicked": r"^down Left .* hit target=5 "}


def main() -> int:
    previous, cursor = native.foreground_window(), native.cursor_pos()
    server_log = os.path.join(HERE, "..", "logs", "win-cu.log")
    log_start = os.path.getsize(server_log) if os.path.exists(server_log) else 0
    subprocess.Popen([os.path.join(HERE, "TestForm.exe")])
    time.sleep(1.5)
    started = time.time()
    claude = os.path.expandvars(r"%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")
    try:
        run = subprocess.run(
            [claude, "-p", TASK, "--model", sys.argv[1] if len(sys.argv) > 1 else "claude-opus-5-5",
             "--effort", "medium", "--allowedTools", "mcp__win-cu", "--disallowedTools", "Bash,PowerShell,Write,Edit",
             "--output-format", "json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE, timeout=900)
    finally:
        elapsed = time.time() - started
        lines = log_lines() if os.path.exists(LOG) else []
        close_forms()
        if previous and native.IsWindow(previous) and not native.IsIconic(previous):
            native.activate(previous)
        native.SetCursorPos(*cursor)
        leftover = os.path.join(HERE, "memory_server.log")
        if os.path.exists(leftover):
            os.remove(leftover)
    try:
        result = json.loads(run.stdout)
    except ValueError:
        print("no JSON from claude:", run.stdout[:500], run.stderr[:500])
        return 2
    with open(server_log, encoding="utf-8", errors="replace") as f:
        f.seek(log_start)
        calls = [m.group(1) for m in re.finditer(r"INFO (\w+) \{.*\} -> (?:ok|refused)", f.read())]
    print("model:", list((result.get("modelUsage") or {}).keys()), "| turns:", result.get("num_turns"),
          f"| wall time: {elapsed:.0f}s | reported duration: {result.get('duration_ms', 0) / 1000:.0f}s")
    print("win-cu calls:", len(calls), calls)
    print("answer:", (result.get("result") or "").strip()[:300])
    print("last form event:", lines[-1] if lines else None)
    ok = True
    for label, pattern in WANTED.items():
        hit = any(re.search(pattern, ln) for ln in lines)
        if label == "name typed":
            names = [ln for ln in lines if ln.startswith("name ")]
            hit = bool(names) and re.search(pattern, names[-1]) is not None
        ok &= hit
        print(f"  {'PASS' if hit else 'FAIL'}  {label}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
