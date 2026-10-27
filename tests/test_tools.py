from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import io
import os
import re
import shutil
import sys
import tempfile
import time

from PIL import Image, ImageChops, ImageStat

from harness import (FORM, TARGETS, Client, canvas_screen, check, control_screen, find, in_window, last, log_lines,
                     miss, native, new_window, on_desktop, run_suite, server, start_form_behind, start_web_form_behind)

WEBVIEW2_LOADERS = (os.environ.get("WINCU_WEBVIEW2_LOADER", ""),)


async def observe(c: Client, form: int) -> None:
    print("observe")
    vx, vy, vw, vh = native.virtual_screen()
    scale = min(1.0, 2000 / max(vw, vh))
    text, err = await c.call("screenshot")
    size = Image.open(io.BytesIO(c.image)).size if c.image else None
    check(not err and f"desktop: {vw}x{vh}" in text and size == (round(vw * scale), round(vh * scale)),
          "screenshot shows the whole desktop at the stated size", f"{size} {text[:200]}")
    check(f'"id":{form}' in text and '"rect":[' in text, "desktop screenshot lists the windows and where they are", text[:400])
    text, err = await c.call("screenshot", window_id=form)
    size = Image.open(io.BytesIO(c.image)).size if c.image else None
    frame = native.frame_rect(form)
    check(not err and size == (frame[2] - frame[0], frame[3] - frame[1]), "screenshot of one window", f"{size} {text[:200]}")
    text, err = await c.call("zoom", region=[0, 0, 300, 200], window_id=form)
    check(not err and c.image and "for reading only" in text, "zoom returns an enlarged view", text)
    text, err = await c.call("get_window_state", window_id=form)
    check(not err and 'Button "Alpha"' in text and c.image is None, "get_window_state returns the tree, no picture", text[:200])
    text, err = await c.call("cursor_position")
    check(not err and re.search(r"pointer at \[\d+, \d+\]", text), "cursor_position", text)


async def desktop_pointer(c: Client, form: int) -> None:
    print("pointer, desktop frame")
    at = lambda i: on_desktop(canvas_screen(form, i))
    for name, button, clicks in (("left_click", "Left", 1), ("double_click", "Left", 2),
                                 ("right_click", "Right", 1), ("middle_click", "Middle", 1), ("triple_click", "Left", 1)):
        text, err = await c.call(name, coordinate=at(1))
        line = last("down")
        check(not err and line.startswith(f"down {button}") and f"clicks={clicks}" in line and "target=1 " in line
              and miss(line) <= 1.5 and c.image is None, f"{name} lands on the target and answers in text", line or text)
    text, err = await c.call("left_click", coordinate=at(2), text="shift")
    check(not err and "key ShiftKey, Shift" in log_lines()[-4:] and "target=2 " in last("down") and "holding shift" in text,
          "click with a held modifier", text)
    downs = len([ln for ln in log_lines() if ln.startswith("down")])
    text, err = await c.call("left_click", coordinate=at(2), text="a")
    check(err and "Only shift, ctrl and alt" in text and len([ln for ln in log_lines() if ln.startswith("down")]) == downs,
          "only modifier keys can be held during a click", text)
    await c.call("mouse_move", coordinate=at(3))
    text, err = await c.call("cursor_position")
    got = [int(v) for v in re.findall(r"\d+", text)]
    check(not err and abs(got[0] - at(3)[0]) <= 1 and abs(got[1] - at(3)[1]) <= 1, "mouse_move then cursor_position", text)
    text, err = await c.call("left_click")
    check(not err and "target=3 " in last("down") and "at the pointer" in text, "click where the pointer is", text)
    text, err = await c.call("left_click_drag", start_coordinate=at(4), coordinate=at(5))
    up = log_lines()[-1]
    check(not err and "target=4 " in last("down") and up.startswith("up Left") and int(up.split("moves=")[1]) >= 8,
          "left_click_drag", f"{last('down')} / {up}")
    await c.call("left_mouse_down", coordinate=at(6))
    await c.call("mouse_move", coordinate=at(7))
    text, err = await c.call("left_mouse_up")
    m = re.match(r"up Left (\d+),(\d+) moves=(\d+)", log_lines()[-1])
    check(not err and "target=6 " in last("down") and m is not None and abs(int(m.group(1)) - 610) <= 2
          and abs(int(m.group(2)) - 390) <= 2 and int(m.group(3)) >= 3, "mouse down, move, up as separate actions",
          f"{last('down')} / {log_lines()[-1]}")
    text, err = await c.call("scroll", coordinate=at(8), scroll_direction="down", scroll_amount=2)
    wheels = [ln for ln in log_lines() if ln.startswith("wheel")]
    check(not err and wheels[-2:] == ["wheel -120 at 260,260"] * 2, "scroll by wheel notches", str(wheels[-2:]))


async def window_pointer(c: Client, form: int) -> None:
    print("pointer, window frame")
    at = lambda i: in_window(form, canvas_screen(form, i))
    for i in (1, 2, 7, 10):
        text, err = await c.call("left_click", window_id=form, coordinate=at(i))
        tx, ty = TARGETS[i - 1]
        check(not err and last("down") == f"down Left {tx},{ty} clicks=1 hit target={i} off=0.0",
              f"window-frame click lands exactly on target {i}", last("down") or text)
    await c.call("scroll", window_id=form, coordinate=at(8), scroll_direction="up", scroll_amount=1)
    check(log_lines()[-1] == "wheel 120 at 260,260", "window-frame scroll", log_lines()[-1])
    await c.call("left_click_drag", window_id=form, start_coordinate=at(4), coordinate=at(5))
    check(last("down").startswith("down Left 120,180") and log_lines()[-1].startswith("up Left 520,200"),
          "window-frame drag", f"{last('down')} / {log_lines()[-1]}")
    text, err = await c.call("left_click", window_id=form, coordinate=at(9))
    check(not err and "The picture changed." in text, "an action that changes the window says so", text)
    text, err = await c.call("mouse_move", window_id=form, coordinate=at(9))
    check(not err and "Nothing visible changed." in text, "an action without visible effect says so", text)
    text, err = await c.call("left_click", window_id=form, coordinate=[5000, 10])
    check(err and "outside the window's screenshot" in text, "coordinates outside the window's screenshot are refused", text)


async def keyboard(c: Client, form: int) -> None:
    print("keyboard")
    name_box = on_desktop(control_screen(form, edit_width=300))
    await c.call("left_click", coordinate=name_box)
    sample = "Hello, \u4f60\u597d\u4e16\u754c – ünïcödé 😀 #1"
    text, err = await c.call("type", text=sample)
    check(not err and last("name ") == "name " + sample and text.startswith("Typed"), "type with CJK, accents and emoji",
          last("name ") or text)
    text, err = await c.call("key", text="ctrl+a BackSpace")
    check(not err and last("name ") == "name ", "key runs several combinations in order", last("name "))
    text, err = await c.call("type", text="abc\n")
    check(not err and last("name ") == "name abc" and last("key ") == "key Return" and "pressed Enter" in text,
          "a line break at the end of typed text presses Enter", f"{text} / {last('name ')} / {last('key ')}")
    for chord, want in (("Control_L+a", "key A, Control"), ("ctrl+shift+period", "key OemPeriod, Shift, Control"),
                        ("F5", "key F5"), ("KP_5", "key NumPad5"), ("Escape", "key Escape"),
                        ("shift+F6", "key F6, Shift"), ("Page_Down", "key Next"), ("alt+Left", "key Left, Alt"),
                        ("KP_9", "key NumPad9"), ("Numpad_0", "key NumPad0"), ("Numpad_Add", "key Add"),
                        ("Numpad_Subtract", "key Subtract"), ("Numpad_Multiply", "key Multiply"),
                        ("Numpad_Divide", "key Divide"), ("Numpad_Decimal", "key Decimal"),
                        ("Numpad_Enter", "key Return"), ("period", "key OemPeriod"), ("greater", "key OemPeriod, Shift"),
                        ("less", "key Oemcomma, Shift"), ("comma", "key Oemcomma"), ("slash", "key OemQuestion"),
                        ("question", "key OemQuestion, Shift"),
                        ("Control_L + Shift_L + period", "key OemPeriod, Shift, Control")):
        text, err = await c.call("key", window_id=form, text=chord)
        check(not err and last("key ") == want, f"key {chord}", last("key ") or text)
    before = len([ln for ln in log_lines() if ln == "key F7"])
    text, err = await c.call("key", text="F7", repeat=3)
    check(not err and len([ln for ln in log_lines() if ln == "key F7"]) - before == 3, "key with repeat", text)
    text, err = await c.call("hold_key", text="shift+F8", duration=0.3)
    check(not err and last("key ") == "key F8, Shift", "hold_key", last("key "))
    text, err = await c.call("key", text="win+r")
    check(err and "Windows key" in text, "the Windows key is refused", text)

    await c.call("write_clipboard", text="clipboard before paste")
    await c.call("click_element", window_id=form, element_name="Notes")
    text, err = await c.call("type", text="\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c line two")
    check(not err and text.startswith("Pasted") and last("notes ") == "notes \u7b2c\u4e00\u884c\\n\u7b2c\u4e8c\u884c line two",
          "multi-line text is pasted, line breaks intact", f"{text} / {last('notes ')}")
    text, err = await c.call("read_clipboard")
    check(not err and text == "clipboard before paste", "the clipboard is put back after a paste", text)
    text, err = await c.call("wait", duration=0.3)
    check(not err and text.startswith("Waited 0.3s"), "wait", text)


async def elements(c: Client, form: int) -> None:
    print("elements")
    tree, _ = await c.call("get_window_state", window_id=form)
    text, err = await c.call("click_element", window_id=form, element_name="Alpha")
    check(not err and last("button") == "button Alpha" and 'Button "Alpha"' in text, "click_element by name", text)
    text, err = await c.call("click_element", window_id=form, element_index=find(tree, "CheckBox", "Enable feature"))
    check(not err and log_lines()[-1] == "check True", "click_element by index", text)
    text, err = await c.call("perform_secondary_action", window_id=form, element_name="Fruits", action="Expand",
                             include_text=True)
    check(not err and 'TreeItem "Apple"' in text and log_lines()[-1] == "expanded Fruits", "perform_secondary_action Expand",
          text[:300])
    text, err = await c.call("click_element", window_id=form, element_name="Apple")
    check(not err and log_lines()[-1] == "tree Apple", "click an element revealed by Expand", log_lines()[-1])
    text, err = await c.call("click_element", window_id=form, element_name="Beta")
    check(not err and log_lines()[-1] == "button Beta", "names still resolve after indexes shifted", text)
    events = len(log_lines())
    text, err = await c.call("click_element", window_id=form, element_index=find(tree, "Button", "Alpha"))
    check(err and "indexes of this window changed" in text and len(log_lines()) == events,
          "an index from before a name lookup read the tree again is refused", text)
    text, err = await c.call("click_element", window_id=form, element_name="Alpah")
    check(err and '"Alpha"' in text, "an unknown name suggests close ones", text)
    text, err = await c.call("set_value", window_id=form, element_name="Name", value="\u8bbe\u5b9a\u503c 42")
    check(not err and last("name ") == "name \u8bbe\u5b9a\u503c 42", "set_value on an edit box", text)
    text, err = await c.call("set_value", window_id=form, element_name="Level", value="40")
    check(not err and log_lines()[-1] == "slider 40", "set_value on a slider", text)
    text, err = await c.call("perform_secondary_action", window_id=form, element_name="Enable feature", action="toggle")
    check(not err and log_lines()[-1] == "check False", "perform_secondary_action Toggle", text)
    text, err = await c.call("perform_secondary_action", window_id=form, element_name="Alpha", action="Expand")
    check(err and "does not support" in text, "an unsupported action is reported", text)
    text, err = await c.call("click_element", window_id=form, element_index=9999)
    check(err and "not in the latest" in text, "an unknown index is refused", text)

    print("popups and dialogs")
    tree, _ = await c.call("get_window_state", window_id=form)
    text, err = await c.call("set_value", window_id=form, element_index=find(tree, "ComboBox"), value="Green")
    check(not err and log_lines()[-1] == "combo Green" and 'Chose "Green"' in text,
          "set_value on a pick-only list chooses the item the way a person would", f"{text} / {log_lines()[-1]}")
    tree, _ = await c.call("get_window_state", window_id=form)
    text, err = await c.call("set_value", window_id=form, element_index=find(tree, "ComboBox"), value="Purple")
    check(err and '"Blue"' in text and '"Red"' in text, "a missing list item is reported with the choices", text)
    tree, _ = await c.call("get_window_state", window_id=form)
    text, err = await c.call("click_element", window_id=form, element_index=find(tree, "ComboBox"), include_text=True)
    check(not err and 'ListItem "Blue"' in text, "an open dropdown is part of the window's tree", text[:300])
    text, err = await c.call("click_element", window_id=form, element_name="Blue")
    check(not err and log_lines()[-1] == "combo Blue", "click an item of the dropdown", text)
    text, err = await c.call("click_element", window_id=form, element_name="File", include_text=True)
    check(not err and 'MenuItem "Open"' in text, "an open menu is part of the window's tree", text[:300])
    text, err = await c.call("screenshot", window_id=form)
    check(not err and c.image is not None, "window screenshot with the menu open")
    text, err = await c.call("click_element", window_id=form, element_name="Open")
    check(not err and log_lines()[-1] == "menu Open", "click a menu item", log_lines()[-1])
    text, err = await c.call("click_element", window_id=form, element_name="Dialog")
    check(not err and "new_windows" in text and "WinCU Question" in text, "a dialog is reported in new_windows", text[:300])
    dialog = new_window(text)
    text, err = await c.call("get_window_state", window_id=form, include_text=False, include_screenshot=True)
    check(not err and "blocked by a modal dialog" in text and str(dialog) in text and c.image is not None,
          "a look at the blocked owner names its dialog", text[:300])
    text, err = await c.call("left_click", window_id=form, coordinate=[50, 50])
    check(err and "modal dialog" in text and str(dialog) in text, "the blocked owner points to its dialog", text)
    state, _ = await c.call("get_window_state", window_id=dialog)
    text, err = await c.call("click_element", window_id=dialog, element_name="\u786e\u5b9a" if '"\u786e\u5b9a"' in state else "OK")
    check(not err and log_lines()[-1] == "dialog OK" and "no longer open" in text, "closing the dialog is reported", text)

    started = time.time()
    text, err = await c.call("perform_secondary_action", window_id=form, element_name="Dialog", action="Invoke")
    check(not err and "has not come back" in text and "WinCU Question" in text and time.time() - started < 8,
          "Invoke that opens a modal dialog returns promptly and says so", f"{time.time() - started:.1f}s {text[:200]}")
    dialog = new_window(text)
    text, err = await c.call("key", window_id=dialog, text="Return")
    check(not err and log_lines()[-1] == "dialog OK", "that dialog is handled by keyboard", text)
    text, err = await c.call("get_window_state", window_id=form)
    check(not err and 'Button "Alpha"' in text, "the tree is readable again afterwards", text[:200])


async def batch(c: Client, form: int) -> None:
    print("batch")
    name_box = on_desktop(control_screen(form, edit_width=300))
    text, err = await c.call("computer_batch", actions=[
        {"action": "left_click", "coordinate": on_desktop(control_screen(form, "Alpha"))},
        {"action": "left_click", "coordinate": name_box},
        {"action": "key", "text": "ctrl+a"},
        {"action": "type", "text": "\u4e00\u6b21\u8c03\u7528"},
        {"action": "key", "text": "F6"},
        {"action": "wait", "duration": 0.2},
    ])
    lines = log_lines()
    alpha = max(i for i, ln in enumerate(lines) if ln == "button Alpha")
    typed = max((i for i, ln in enumerate(lines) if ln == "name \u4e00\u6b21\u8c03\u7528"), default=-1)
    check(not err and "6. Waited" in text and typed > alpha and lines[-1] == "key F6" and c.image is not None
          and "desktop:" in text, "six desktop steps in one call, in order, one screenshot", text[:400])
    text, err = await c.call("computer_batch", actions=[
        {"action": "click_element", "window_id": form, "element_name": "Beta"},
        {"action": "set_value", "window_id": form, "element_name": "Name", "value": "\u6279\u91cf\u8bbe\u503c"},
        {"action": "key", "window_id": form, "text": "F9"},
    ])
    lines = log_lines()
    beta = max((i for i, ln in enumerate(lines) if ln == "button Beta"), default=-1)
    named = max((i for i, ln in enumerate(lines) if ln == "name \u6279\u91cf\u8bbe\u503c"), default=-1)
    check(not err and -1 < beta < named and lines[-1] == "key F9" and f"pass window_id={form}" in text
          and c.image is not None, "element steps and window-frame steps in a batch", text[:400] + str(lines[-8:]))
    text, err = await c.call("computer_batch", screenshot_after=False, actions=[
        {"action": "click_element", "window_id": form, "element_name": "Alpha"},
        {"action": "left_click", "coordinate": [99999, 5]},
        {"action": "type", "text": "never"},
    ])
    check(not err and "2. FAILED" in text and "Steps 3-3 were not run" in text and last("button") == "button Alpha"
          and "never" not in last("name ") and c.image is None, "a batch stops at the failing step", text[:300])
    text, err = await c.call("computer_batch", actions=[{"action": "screenshot"}])
    check((err and "not one of" in text) or "not a batch step" in text, "a screenshot is not a batch step", text[:200])


async def interrupted(c: Client, form: int) -> None:
    print("interrupted")
    at = lambda i: in_window(form, canvas_screen(form, i))
    events = len(log_lines())
    said = await c.cancel_after(1.5, "computer_batch", actions=[
        {"action": "click_element", "window_id": form, "element_name": "Alpha"},
        {"action": "wait", "duration": 20},
        {"action": "click_element", "window_id": form, "element_name": "Beta"},
        {"action": "type", "window_id": form, "text": "never"},
    ])
    started = time.monotonic()
    text, err = await c.call("left_click", window_id=form, coordinate=at(1))
    took = time.monotonic() - started
    check("cancelled" in said and not err and took < 4 and "target=1 " in last("down"),
          "a call right after a cancelled batch runs at once", f"{said} / {took:.1f}s / {text}")
    await asyncio.sleep(1)
    after = log_lines()[events:]
    check("button Alpha" in after and "button Beta" not in after and not any("never" in ln for ln in after),
          "the steps after the cancellation never reach the window", str(after))

    events = len(log_lines())
    await c.cancel_after(2, "computer_batch", actions=[
        {"action": "left_mouse_down", "window_id": form, "coordinate": at(6)},
        {"action": "mouse_move", "window_id": form, "coordinate": at(7)},
        {"action": "wait", "duration": 20},
        {"action": "left_mouse_up", "window_id": form, "coordinate": at(9)},
    ])
    await asyncio.sleep(0.5)
    after = log_lines()[events:]
    check(any(ln.startswith("down Left 30,300 ") for ln in after) and after[-1].startswith("up Left 610,390 "),
          "a button held when the call is cancelled comes up where the pointer is", str(after))

    pressed = lambda: len([ln for ln in log_lines() if ln == "key F7"])
    before = pressed()
    await c.cancel_after(1, "key", window_id=form, text="F7", repeat=100)
    await asyncio.sleep(0.3)
    count = pressed() - before
    await asyncio.sleep(1)
    check(0 < count < 50 and pressed() - before == count, "repeated key presses stop when the call is cancelled",
          f"{count}, then {pressed() - before}")

    said = await c.cancel_after(1, "hold_key", window_id=form, text="shift+F8", duration=20)
    await asyncio.sleep(0.3)
    check(last("key ") == "key F8, Shift" and not native.held_modifiers() and not native.GetAsyncKeyState(0x77) & 0x8000,
          "keys held when the call is cancelled come up", f"{said} / {last('key ')} / {native.held_modifiers()}")


async def guards(c: Client, form: int) -> None:
    print("guards")
    text, err = await c.call("left_click", coordinate=[99999, 5])
    check(err and "outside the desktop screenshot" in text, "coordinates outside the desktop screenshot are refused", text)
    vx, vy, vw, vh = native.virtual_screen()
    point = None
    for h in native.enum_windows():
        exe = native.process_image_path(native.window_pid_tid(h)[0]).lower()
        if native.IsWindowVisible(h) and not native.IsIconic(h) and not native.is_cloaked(h) \
                and exe.endswith(("\\claude.exe", "\\windowsterminal.exe")):
            l, t, r, b = native.frame_rect(h)
            for sx, sy in ((r - 30, t + 40), (l + 30, b - 40), ((l + r) // 2, (t + b) // 2)):
                if vx <= sx < vx + vw and vy <= sy < vy + vh and native.window_root(native.window_from_point(sx, sy)) == h:
                    point = on_desktop((sx, sy))
                    break
        if point:
            break
    if point:
        text, err = await c.call("left_click", coordinate=point)
        check(err and "off-limits" in text, "a click on an off-limits window is refused", text)
    else:
        print("  SKIP  no off-limits window is showing")
    await c.call("activate_window", window_id=form)
    keys = len([ln for ln in log_lines() if ln.startswith("key F7")])
    text, err = await c.call("key", text="alt+F4 F7")
    check(err and "focus moved" in text and len([ln for ln in log_lines() if ln.startswith("key F7")]) == keys,
          "keys stop once the focus has moved to another window", text)
    text, err = await c.call("screenshot", window_id=form)
    check(err and "no longer open" in text, "a closed window is refused", text)


async def covered_window(c: Client) -> None:
    print("covered window")
    front = native.foreground_window()
    form = start_form_behind()
    check(native.foreground_window() == front, "the form opened underneath without taking the focus")
    text, err = await c.call("screenshot", window_id=form)
    image = Image.open(io.BytesIO(c.image)) if c.image else None
    px = image.getpixel(tuple(in_window(form, canvas_screen(form, 1)))) if image else None
    check(not err and px is not None and px[0] > 180 and px[1] < 80, "screenshot of a covered window shows the window itself",
          f"{px} {text[:200]}")
    text, err = await c.call("left_click", window_id=form, coordinate=in_window(form, canvas_screen(form, 12)))
    check(not err and last("down") == "down Left 480,110 clicks=1 hit target=12 off=0.0" and native.foreground_window() == form,
          "an action on a covered window brings it forward and lands exactly", last("down") or text)
    text, err = await c.call("open_application", app=FORM)
    check(not err and "already open" in text and str(form) in text, "open_application brings a running app forward", text)
    text, err = await c.call("open_application", app="TestForm.exe")
    check(not err and "already open" in text and str(form) in text, "a running program is found by its .exe name", text)
    text, err = await c.call("key", window_id=form, text="alt+F4")
    check(not err and "no longer open" in text, "closing the window is reported", text)


async def web_page(c: Client) -> None:
    print("web page")
    loader = next((p for p in WEBVIEW2_LOADERS if p and os.path.isfile(p)), None)
    if loader is None:
        print("  SKIP  no WebView2Loader.dll on this PC; set WINCU_WEBVIEW2_LOADER to one")
        return
    data = tempfile.mkdtemp(prefix="wincu-webview2-")
    process, page = start_web_form_behind(loader, data)
    try:
        text, err = await c.call("get_window_state", window_id=page)
        check(not err and 'Button "Probe button"' in text and 'Edit "Probe field"' in text,
              "the first reading of a new web view includes its page", text[:400])
        pictures = []
        for _ in range(2):
            text, err = await c.call("screenshot", window_id=page)
            pictures.append(Image.open(io.BytesIO(c.image)).convert("L") if c.image else None)
            await asyncio.sleep(0.6)
        moved = None not in pictures and ImageStat.Stat(ImageChops.difference(*pictures)).mean[0] > 0.2
        check(moved, "a covered web view is pictured as it is now: its counter moves between screenshots")
    finally:
        process.kill()
        time.sleep(1.5)
        shutil.rmtree(data, ignore_errors=True)


async def launching(c: Client) -> None:
    print("launching by name")
    text, err = await c.call("open_application", app="calc.exe")
    opened = [int(i) for i in re.findall(r'"id":(\d+)', text)]
    check(not err and text.startswith("Started calc.exe") and opened, "an .exe name starts its program", text)
    for h in opened:
        ctypes.windll.user32.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
    deadline = time.monotonic() + 5
    while any(native.IsWindow(h) and native.IsWindowVisible(h) for h in opened) and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
    check(not any(native.IsWindow(h) and native.IsWindowVisible(h) for h in opened), "and it closes again")


async def run() -> None:
    async with server() as c:
        text, err = await c.call("open_application", app=FORM)
        check(not err and text.startswith("Started TestForm.exe") and "WinCU Test Form" in text, "open_application starts the app", text)
        form = new_window(text)
        await observe(c, form)
        await desktop_pointer(c, form)
        await window_pointer(c, form)
        await keyboard(c, form)
        await elements(c, form)
        await batch(c, form)
        await interrupted(c, form)
        await guards(c, form)
        await covered_window(c)
        await web_page(c)
        await launching(c)


if __name__ == "__main__":
    sys.exit(run_suite(run()))
