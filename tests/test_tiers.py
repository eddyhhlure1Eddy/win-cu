from __future__ import annotations

import json
import os
import sys
import tempfile

from harness import FORM, canvas_screen, check, control_screen, in_window, last, log_lines, new_window, on_desktop, run_suite, server


async def run(config: str) -> None:
    async with server(config) as c:
        text, _ = await c.call("open_application", app=FORM)
        form = new_window(text)
        at = lambda i: in_window(form, canvas_screen(form, i))

        print("allowed")
        text, err = await c.call("screenshot", window_id=form)
        check(not err and c.image is not None, "looking is allowed")
        text, err = await c.call("left_click", window_id=form, coordinate=at(1))
        check(not err and "target=1 " in last("down"), "a plain left click is allowed", text)
        text, err = await c.call("double_click", window_id=form, coordinate=at(2))
        check(not err and "target=2 " in last("down"), "a double left click is allowed", text)
        text, err = await c.call("scroll", window_id=form, coordinate=at(8), scroll_direction="down", scroll_amount=1)
        check(not err and log_lines()[-1] == "wheel -120 at 260,260", "scrolling is allowed", text)
        text, err = await c.call("click_element", window_id=form, element_name="Alpha")
        check(not err and last("button") == "button Alpha", "clicking an element is allowed", text)

        print("refused")
        events = len(log_lines())
        refused = (
            ("type", {"window_id": form, "text": "rm -rf"}),
            ("key", {"window_id": form, "text": "Return"}),
            ("hold_key", {"window_id": form, "text": "a", "duration": 0.2}),
            ("right_click", {"window_id": form, "coordinate": at(3)}),
            ("left_click", {"window_id": form, "coordinate": at(3), "text": "ctrl"}),
            ("left_click_drag", {"window_id": form, "start_coordinate": at(4), "coordinate": at(5)}),
            ("left_mouse_down", {"window_id": form, "coordinate": at(4)}),
            ("set_value", {"window_id": form, "element_name": "Name", "value": "x"}),
            ("perform_secondary_action", {"window_id": form, "element_name": "Alpha", "action": "Invoke"}),
            ("click_element", {"window_id": form, "element_name": "Alpha", "mouse_button": "right"}),
            ("type", {"text": "rm -rf"}),
            ("right_click", {"coordinate": on_desktop(canvas_screen(form, 3))}),
        )
        for tool, arguments in refused:
            text, err = await c.call(tool, **arguments)
            frame = "desktop frame" if "window_id" not in arguments else "window frame"
            check(err and "code editor" in text, f"{tool} is refused ({frame})", text)
        check(len(log_lines()) == events, "none of the refused actions reached the app", str(log_lines()[events:]))
        text, err = await c.call("left_click", coordinate=on_desktop(control_screen(form, "Beta")))
        check(not err and last("button") == "button Beta", "a plain left click through the desktop frame is allowed", text)


def main() -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"click_only_apps": ["TestForm.exe"]}, f)
    try:
        return run_suite(run(f.name))
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    sys.exit(main())
