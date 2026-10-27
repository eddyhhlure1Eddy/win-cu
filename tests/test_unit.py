from __future__ import annotations

import json
import os
import sys
import threading
import time

from harness import check, native, results

from wincu import core as core_module
from wincu.apps import find_executable
from wincu.core import Cancelled, ComputerUse, CUError, _uncovered
from wincu.keys import ChordError, parse_chord
from wincu.uia import Snapshot


def refused(call, *words: str) -> bool:
    try:
        call()
    except CUError as e:
        return all(w in str(e) for w in words)
    return False


def cancelled(call) -> float | None:
    started = time.monotonic()
    try:
        call()
    except Cancelled:
        return time.monotonic() - started
    return None


def main() -> int:
    cu = ComputerUse({"show_banner": False, "yield_to_user": False})

    print("after the user pressed Esc")
    cu.presence._stopped_until = time.monotonic() + 30
    check(refused(lambda: cu.call("left_click", {"coordinate": [5, 5]}), "pressed Esc"), "a click is refused")
    check(refused(lambda: cu.call("type", {"text": "x"}), "pressed Esc"), "typing is refused")
    said = cu.call("computer_batch", {"actions": [{"action": "key", "text": "F13"}], "screenshot_after": False}).text
    check("1. FAILED" in said and "pressed Esc" in said, "a batch step is refused", said)
    check(cu.call("left_mouse_up", {}).text.startswith("Released the left button"), "releasing the button is still allowed")
    check(cu.call("wait", {"duration": 0.05}).text.startswith("Waited"), "waiting is still allowed")
    check(cu.call("cursor_position", {}).text.startswith("pointer at"), "looking is still allowed")
    cu.presence._stopped_until = 0.0

    print("letting go of a button")
    closed = next(h for h in range(0x7FF00000, 0x7FF01000, 4) if not native.IsWindow(h))
    native._buttons_down.add("left")
    check(refused(lambda: cu.call("left_mouse_up", {"window_id": closed}), "no longer open", "has been released")
          and not native._buttons_down, "the button comes up even when its window has closed")
    try:
        cu.call("left_click", {"window_id": closed, "coordinate": [5, 5]})
        said = ""
    except CUError as e:
        said = str(e)
    check("no longer open" in said and "released" not in said, "other actions on a closed window say only that", said)

    print("a cancelled call")
    stop = threading.Event()
    stop.set()
    took = cancelled(lambda: cu.call("wait", {"duration": 5}, stop))
    check(took is not None and took < 0.5, "a call cancelled before it starts ends at its first checkpoint", str(took))
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    took = cancelled(lambda: cu.call("wait", {"duration": 10}, stop))
    check(took is not None and took < 0.6, "a long wait ends as soon as its call is cancelled", str(took))
    pressed = []
    real_press = native.press_chord
    native.press_chord = lambda chord, hold=0.0: pressed.append(chord)
    try:
        stop = threading.Event()
        threading.Timer(0.4, stop.set).start()
        took = cancelled(lambda: cu.call("computer_batch", {"actions": [
            {"action": "wait", "duration": 0.1}, {"action": "wait", "duration": 10}, {"action": "key", "text": "F13"}],
            "screenshot_after": False}, stop))
    finally:
        native.press_chord = real_press
    check(took is not None and took < 1.0 and not pressed, "a cancelled batch stops at once and runs no further step",
          f"{took} {pressed}")
    native._buttons_down.add("left")
    stop = threading.Event()
    stop.set()
    check(cancelled(lambda: cu.call("wait", {"duration": 1}, stop)) is not None and not native._buttons_down,
          "a button held when the call is cancelled comes up")
    check(cu._cancel is None and cu.call("wait", {"duration": 0.05}).text.startswith("Waited"),
          "the next call runs normally")
    cu._sending, cu.presence._stopped_until = True, time.monotonic() + 30
    check(refused(cu._checkpoint, "pressed Esc"), "Esc ends a gesture under way at its next checkpoint")
    cu._sending, cu.presence._stopped_until = False, 0.0

    print("one Claude session at a time")
    owner_file = core_module._OWNER_FILE
    saved = open(owner_file, encoding="utf-8").read() if os.path.exists(owner_file) else None
    try:
        os.makedirs(os.path.dirname(owner_file), exist_ok=True)
        with open(owner_file, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getppid(), "time": time.time()}, f)
        check(refused(lambda: cu.call("type", {"text": "x"}), "Another Claude session"), "a session that just acted keeps the desktop")
        with open(owner_file, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getppid(), "time": time.time() - 60}, f)
        check(not cu._other_session(), "the claim lapses after a while")
        with open(owner_file, "w", encoding="utf-8") as f:
            json.dump({"pid": 4194300, "time": time.time()}, f)
        check(not cu._other_session(), "a session that has ended holds nothing")
    finally:
        if saved is None:
            os.remove(owner_file)
        else:
            with open(owner_file, "w", encoding="utf-8") as f:
                f.write(saved)

    print("text and keys")
    typed, pressed, pasted = [], [], []
    real = (native.type_unicode, native.press_chord, native.paste_text)
    native.type_unicode = lambda text, still=None: typed.append(text)
    native.press_chord = lambda chord, hold=0.0: pressed.append(chord[0][0])
    native.paste_text = lambda text: pasted.append(text) or False
    try:
        said = cu._enter_text("query\n", lambda: True)
        check(typed == ["query"] and pressed == [0x0D] and said == "Typed 5 characters and pressed Enter",
              "a final line break is one Enter", said)
        typed.clear(); pressed.clear()
        said = cu._enter_text("one\ntwo\r\n\r\n", lambda: True)
        check(pasted == ["one\ntwo"] and pressed == [0x0D, 0x0D] and not typed, "inner line breaks are pasted, final ones pressed", said)
        pressed.clear()
        check(cu._enter_text("\n", lambda: True) == "Pressed Enter" and pressed == [0x0D], "a lone line break is Enter")
        check(refused(lambda: cu._enter_text("x\n", lambda: False), "focus moved"), "Enter is withheld once the focus has moved")
    finally:
        native.type_unicode, native.press_chord, native.paste_text = real
    check([vk for vk, _ in parse_chord("Control_L+Shift_L+period")] == [0x11, 0x10, 0xBE], "X keysym names")
    check([vk for vk, _ in parse_chord("ctrl+A")] == [0x11, 0x41] and [vk for vk, _ in parse_chord("A")] == [0x10, 0x41],
          "ctrl+A is Ctrl+A, a bare A is Shift+A")
    check([vk for vk, _ in parse_chord("greater")] == [0x10, 0xBE], "shifted keysyms bring their Shift")
    for bad in ("win+r", "Super_L", "cmd+space", "ctrl++", "nosuchkey"):
        try:
            parse_chord(bad)
            check(False, f"{bad} is rejected")
        except ChordError:
            check(True, f"{bad} is rejected")
    check(refused(lambda: cu._modifiers("a"), "Only shift, ctrl and alt"), "letters cannot be held during a click")
    wanted = {**{f"KP_{i}": [0x60 + i] for i in range(10)}, "Numpad_0": [0x60], "Numpad_Add": [0x6B],
              "Numpad_Subtract": [0x6D], "Numpad_Multiply": [0x6A], "Numpad_Divide": [0x6F], "Numpad_Decimal": [0x6E],
              "Numpad_Enter": [0x0D], "period": [0xBE], "greater": [0x10, 0xBE], "less": [0x10, 0xBC],
              "comma": [0xBC], "slash": [0xBF], "question": [0x10, 0xBF]}
    wrong = {name: [vk for vk, _ in parse_chord(name)] for name in wanted
             if [vk for vk, _ in parse_chord(name)] != wanted[name]}
    check(not wrong, "every keysym of ChatGPT's list maps to its key", str(wrong))

    def extended(name: str) -> bool:
        vk, ext = parse_chord(name)[-1]
        return bool(native.key_events(vk, False, ext).ki.dwFlags & native.KEYEVENTF_EXTENDEDKEY)

    check(extended("Numpad_Enter") and extended("Numpad_Divide") and not extended("Return") and not extended("slash")
          and not extended("KP_0"), "numpad Enter and / go out as the extended keys apps tell apart")
    check([[vk for vk, _ in c] for c in cu._chords("Control_L + Shift_L + period  F5")] == [[0x11, 0x10, 0xBE], [0x74]],
          "spaces around + are only spacing; other spaces separate combinations")

    print("launching by name")
    calc = os.path.normcase(os.path.join(os.environ["SystemRoot"], "System32", "calc.exe"))
    check(os.path.normcase(cu._executable("calc.exe")) == calc, "an .exe name is found on PATH", cu._executable("calc.exe"))
    check(os.path.normcase(cu._executable(r"%SystemRoot%\System32\calc.exe")) == calc, "variables in a path are expanded")
    edge = os.path.join(os.environ["ProgramFiles(x86)"], r"Microsoft\Edge\Application\msedge.exe")
    if os.path.isfile(edge):
        check(os.path.normcase(find_executable("msedge.exe")) == os.path.normcase(edge),
              "an .exe name is found through App Paths", find_executable("msedge.exe"))
    check(cu._executable("no-such-program-4711.exe") == "" and cu._executable(r"C:\nowhere\x.exe") == ""
          and cu._executable("calc") == "", "only an existing .exe counts")
    check(refused(lambda: cu.call("open_application", {"app": "cmd.exe"}), "may not control cmd.exe"),
          "an off-limits program named by its .exe is refused")
    check(refused(lambda: cu.call("open_application", {"app": "no-such-program-4711.exe"}), "Unknown app", ".exe"),
          "an unknown program says what to pass instead")

    print("indexes and a tree read again")
    fake = 0x7FF0FFF0
    cu._trees[fake] = Snapshot(lines=['[0] Button "A"', '[1] Button "B"'], elements=["A", "B"],
                               labels=[(50000, "A"), (50000, "B")])
    check(cu._element(fake, 1) == ("B", 1), "an index of the tree the caller saw picks its element")
    cu._unseen.add(fake)
    check(refused(lambda: cu._element(fake, 1), "indexes of this window changed", "get_window_state"),
          "after a name lookup read the tree again, an old index is refused")
    check(refused(lambda: cu._element(fake, 7), "not in the latest", "get_window_state"),
          "an index outside the tree says how to get a current one")
    cu._forget(fake)

    print("a locked desktop")
    real_desktop = native.input_desktop_name
    native.input_desktop_name = lambda: None
    try:
        check(refused(lambda: cu.call("screenshot", {}), "locked", "ask the user"), "a screenshot says the desktop is locked")
        check(refused(lambda: cu.call("left_click", {"coordinate": [5, 5]}), "locked"), "input is refused")
        said = cu.call("computer_batch", {"actions": [{"action": "wait", "duration": 0.05}]}).text
        check("1. Waited" in said and "No screenshot" in said and "locked" in said,
              "a batch still reports its steps when its screenshot cannot be taken", said)
    finally:
        native.input_desktop_name = real_desktop

    print("geometry")
    parts = _uncovered((0, 0, 10, 10), [(5, -5, 20, 5), (-5, 8, 3, 30)])
    check(sum((p[2] - p[0]) * (p[3] - p[1]) for p in parts) == 100 - 25 - 6, "uncovered area after two overlaps")
    vx, vy, vw, vh = native.virtual_screen()
    width, height, scale = cu._desktop_size()
    corners = [cu._locate(0, [0, 0]), cu._locate(0, [width - 1, height - 1])]
    check(corners[0] == (vx, vy) or abs(corners[0][0] - vx) <= 1, "desktop frame: first pixel maps to the screen corner", str(corners))
    check(vx + vw - 2 <= corners[1][0] <= vx + vw - 1 and vy + vh - 2 <= corners[1][1] <= vy + vh - 1,
          "desktop frame: last pixel maps inside the screen", str(corners))
    check(refused(lambda: cu._locate(0, [width, 0]), "outside the desktop screenshot"), "desktop frame: one past the edge is refused")

    print("the pointer's path")
    path = native.glide_path((100, 500), (900, 500), 30, 100)
    check(path[-1] == (900, 500) and max(y for _, y in path) - 500 in (99, 100) and min(y for _, y in path) == 500
          and all(a[0] <= b[0] for a, b in zip(path, path[1:])),
          "a glide bows by its bow halfway, never turns back, and ends on its target", str(path[:8]))
    moved = []
    real = (native.cursor_pos, native.mouse_move, native.pause)
    native.cursor_pos, native.pause = (lambda: (100, 500)), (lambda seconds: None)
    native.mouse_move = lambda x, y: moved.append((x, y))
    try:
        native.mouse_glide(900, 500)
        bowed = max(abs(y - 500) for _, y in moved)
        moved.clear()
        native._buttons_down.add("left")
        native.mouse_glide(900, 500)
    finally:
        native._buttons_down.discard("left")
        native.cursor_pos, native.mouse_move, native.pause = real
    check(800 * native.GLIDE_BOW[0] - 1 <= bowed <= native.GLIDE_BOW_MAX_PX and len(moved) > 10
          and all(y == 500 for _, y in moved) and moved[-1] == (900, 500),
          "a move arcs on its way; with a button held it goes straight", f"bow {bowed}, held {moved[:4]}")

    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for label in failed:
        print("FAILED:", label)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
