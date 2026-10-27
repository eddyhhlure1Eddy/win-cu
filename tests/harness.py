from __future__ import annotations

import asyncio
import base64
import contextlib
import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import sys
import time

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from wincu import native

OUT = os.path.join(HERE, "out")
FORM = os.path.join(HERE, "TestForm.exe")
WEB_FORM = os.path.join(HERE, "WebForm.exe")
LOG = os.path.join(HERE, "testform.log")
FORM_TITLES = ("WinCU Test Form", "WinCU Question", "WinCU Web Form", "WinCU Web Form ready")
TARGETS = [(40, 40), (600, 30), (320, 90), (120, 180), (520, 200), (30, 300), (610, 390), (260, 260),
           (420, 340), (180, 380), (350, 20), (480, 110)]

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((bool(ok), label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not ok else ""))


def log_lines() -> list[str]:
    with open(LOG, encoding="utf-8") as f:
        return [line.split(" ", 1)[1].rstrip("\n") for line in f if " " in line]


def last(prefix: str) -> str:
    lines = [ln for ln in log_lines() if ln.startswith(prefix)]
    return lines[-1] if lines else ""


def miss(line: str) -> float:
    m = re.search(r"off=([\d.]+)", line)
    return float(m.group(1)) if m else 99.0


class Client:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.step = 0
        self.image: bytes | None = None

    async def call(self, tool: str, **arguments) -> tuple[str, bool]:
        self.step += 1
        result = await asyncio.wait_for(self.session.call_tool(tool, arguments), 60)
        text, self.image = "", None
        for block in result.content:
            if block.type == "text":
                text += block.text
            elif block.type == "image":
                self.image = base64.b64decode(block.data)
                with open(os.path.join(OUT, f"{self.step:02d}_{tool}.{block.mimeType.split('/')[-1]}"), "wb") as f:
                    f.write(self.image)
        return text, bool(result.isError)

    async def cancel_after(self, seconds: float, tool: str, **arguments) -> str:
        self.step += 1
        request_id = self.session._request_id
        call = asyncio.create_task(self.session.call_tool(tool, arguments))
        await asyncio.sleep(seconds)
        await self.session.send_notification(types.ClientNotification(types.CancelledNotification(
            params=types.CancelledNotificationParams(requestId=request_id, reason="the user interrupted"))))
        try:
            result = await asyncio.wait_for(call, 30)
        except McpError as e:
            return str(e)
        return "finished: " + "".join(block.text for block in result.content if block.type == "text")


@contextlib.asynccontextmanager
async def server(config: str | None = None):
    os.makedirs(OUT, exist_ok=True)
    env = {**os.environ, **({"WINCU_CONFIG": config} if config else {})}
    params = StdioServerParameters(command=sys.executable, env=env,
                                   args=["-u", "-X", "utf8", os.path.join(HERE, "..", "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield Client(session)


def find(tree: str, kind: str, name: str | None = None) -> int:
    for m in re.finditer(r'\[(\d+)\] (\w+)(?: "((?:[^"\\]|\\.)*)")?', tree):
        if m.group(2) == kind and (name is None or m.group(3) == name):
            return int(m.group(1))
    raise AssertionError(f"no {kind} {name!r} in tree:\n{tree}")


def new_window(text: str) -> int:
    return int(re.search(r'windows: \[\{"id":(\d+)', text).group(1))


def canvas_screen(form: int, index: int) -> tuple[int, int]:
    canvas = next(c for c in native.enum_child_windows(form)
                  if (lambda r: (r[2] - r[0], r[3] - r[1]))(native.window_rect(c)) == (640, 440))
    pt = wt.POINT(*TARGETS[index - 1])
    ctypes.windll.user32.ClientToScreen(wt.HWND(canvas), ctypes.byref(pt))
    return pt.x, pt.y


def control_screen(form: int, text: str | None = None, edit_width: int | None = None) -> tuple[int, int]:
    for c in native.enum_child_windows(form):
        l, t, r, b = native.window_rect(c)
        if (text is not None and native.window_text(c) == text) or \
                (edit_width is not None and r - l == edit_width and "EDIT" in native.window_class(c).upper()):
            return (l + r) // 2, (t + b) // 2
    raise AssertionError(f"no control {text or edit_width}")


def in_window(form: int, point: tuple[int, int], scale: tuple[float, float] = (1.0, 1.0)) -> list[int]:
    frame = native.frame_rect(form)
    return [int((point[0] - frame[0]) * scale[0]), int((point[1] - frame[1]) * scale[1])]


def on_desktop(point: tuple[int, int], edge: int = 2000) -> list[int]:
    vx, vy, vw, vh = native.virtual_screen()
    scale = min(1.0, edge / max(vw, vh))
    return [int((point[0] - vx) * scale), int((point[1] - vy) * scale)]


def start_form_behind() -> int:
    front = native.foreground_window()
    l, t, _, _ = native.frame_rect(front) if front else (150, 150, 0, 0)
    subprocess.Popen([FORM, "background", str(max(l, 0) + 40), str(max(t, 0) + 40)])
    for _ in range(50):
        time.sleep(0.1)
        for h in native.enum_windows():
            if native.window_text(h) == FORM_TITLES[0] and native.IsWindowVisible(h):
                time.sleep(0.4)
                return h
    raise AssertionError("the test form did not appear")


def start_web_form_behind(loader: str, data: str) -> tuple[subprocess.Popen, int]:
    l, t, _, _ = native.frame_rect(native.foreground_window()) if native.foreground_window() else (150, 150, 0, 0)
    process = subprocess.Popen([WEB_FORM, loader, data, "background", str(max(l, 0) + 60), str(max(t, 0) + 60)])
    for _ in range(150):
        time.sleep(0.1)
        for h in native.enum_windows():
            if native.window_text(h) == "WinCU Web Form ready":
                time.sleep(1.5)
                return process, h
    process.kill()
    raise AssertionError("the web form did not appear")


def close_forms() -> None:
    for h in native.enum_windows():
        if native.window_text(h) in FORM_TITLES and native.IsWindowVisible(h):
            ctypes.windll.user32.PostMessageW(wt.HWND(h), 0x0010, 0, 0)


def run_suite(coroutine) -> int:
    previous, cursor = native.foreground_window(), native.cursor_pos()
    started = time.time()
    try:
        asyncio.run(coroutine)
    finally:
        close_forms()
        time.sleep(0.3)
        if previous and native.IsWindow(previous) and not native.IsIconic(previous):
            native.activate(previous)
        native.SetCursorPos(*cursor)
    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed in {time.time() - started:.0f}s")
    for label in failed:
        print("FAILED:", label)
    return 1 if failed else 0
