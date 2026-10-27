from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import re
import sys
import tempfile

from PIL import Image

from harness import (FORM, canvas_screen, check, in_window, last, miss, native, new_window, on_desktop, run_suite,
                     server)

EDGE = 500


async def run(config: str) -> None:
    async with server(config) as c:
        text, _ = await c.call("open_application", app=FORM)
        form = new_window(text)

        print("window frame, scaled")
        text, err = await c.call("screenshot", window_id=form)
        m = re.search(r"screenshot: (\d+)x(\d+) \(scaled x([\d.]+) from (\d+)x(\d+)", text)
        check(not err and m is not None, "a large window is scaled down to the edge limit", text)
        width, height, full_w, full_h = int(m.group(1)), int(m.group(2)), int(m.group(4)), int(m.group(5))
        check(max(width, height) == EDGE and Image.open(io.BytesIO(c.image)).size == (width, height),
              "the picture has the stated size", f"{width}x{height}")
        scale = (width / full_w, height / full_h)
        for i in (1, 2, 7, 9, 12):
            text, err = await c.call("left_click", window_id=form, coordinate=in_window(form, canvas_screen(form, i), scale))
            check(not err and f"hit target={i} " in last("down") and miss(last("down")) <= 1.5,
                  f"scaled click hits target {i} within 1.5 px", last("down") or text)
        x, y = in_window(form, canvas_screen(form, 4), scale)
        text, err = await c.call("zoom", window_id=form, region=[x - 30, y - 20, x + 30, y + 20])
        check(not err and c.image and "for reading only" in text, "zoom on a scaled window", text)
        text, err = await c.call("left_click", window_id=form, coordinate=[x, y])
        check(not err and "hit target=4 " in last("down"), "coordinates still refer to the full screenshot after a zoom",
              last("down"))

        print("desktop frame, scaled")
        text, err = await c.call("screenshot")
        size = Image.open(io.BytesIO(c.image)).size if c.image else None
        check(not err and size is not None and max(size) == EDGE, "the desktop screenshot is scaled to the edge limit", f"{size}")
        text, err = await c.call("left_click", coordinate=on_desktop(canvas_screen(form, 5), EDGE))
        check(not err and "target=5 " in last("down") and miss(last("down")) <= 6, "scaled desktop click reaches the target",
              last("down") or text)

        print("moved and resized windows")
        ctypes.windll.user32.SetWindowPos(wt.HWND(form), None, 300, 160, 0, 0, 0x0001 | 0x0004 | 0x0010)
        text, err = await c.call("left_click", window_id=form, coordinate=in_window(form, canvas_screen(form, 8), scale))
        check(not err and "hit target=8 " in last("down"), "the mapping follows a moved window", text + last("down"))
        ctypes.windll.user32.SetWindowPos(wt.HWND(form), None, 0, 0, 1000, 760, 0x0002 | 0x0004 | 0x0010)
        text, err = await c.call("left_click", window_id=form, coordinate=[100, 100])
        check(err and "changed size" in text, "a resized window needs a fresh screenshot", text)
        await c.call("key", window_id=form, text="alt+F4")


def main() -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"max_image_edge": EDGE}, f)
    try:
        return run_suite(run(f.name))
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    sys.exit(main())
