from __future__ import annotations

import contextlib
import difflib
import inspect
import io
import json
import os
import re
import threading
import time
import zlib
from dataclasses import dataclass

from comtypes import COMError
from PIL import Image, ImageChops, ImageDraw, ImageStat

from . import native
from .apps import AppCatalog, find_executable, launch as shell_launch
from .keys import ChordError, parse_chord
from .presence import Presence
from .uia import (CT_COMBOBOX, CT_DOCUMENT, CT_LISTITEM, INTERACTIVE, Accessibility, ElementGone, Snapshot,
                  TreeUnavailable)


class CUError(Exception):
    pass


class Cancelled(Exception):
    pass


DEFAULT_CONFIG = {
    "max_image_edge": 2000,
    "max_png_bytes": 300000,
    "settle_ms": 200,
    "settle_max_ms": 2500,
    "launch_wait_s": 8,
    "show_banner": True,
    "banner_linger_s": 10,
    "yield_to_user": True,
    "session_hold_s": 20,
    "max_tree_elements": 1500,
    "max_tree_tokens": 10000,
    "max_document_chars": 4000,
    "busy_markers": [
        {"class": "CodexComputerUseCursorOverlay"},
    ],
    "denied_apps": [
        "WindowsTerminal.exe", "OpenConsole.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
        "powershell_ise.exe", "wt.exe", "wsl.exe", "bash.exe", "mintty.exe", "wezterm-gui.exe",
        "alacritty.exe", "putty.exe", "Tabby.exe", "Hyper.exe", "ConEmu.exe", "ConEmu64.exe",
        "microsoft.windowsterminal",
        "LockApp.exe", "LogonUI.exe", "consent.exe", "CredentialUIBroker.exe",
        "SecHealthUI.exe", "SecurityHealthHost.exe", "sechealthui",
        "1Password.exe", "Bitwarden.exe", "KeePass.exe", "KeePassXC.exe", "LastPass.exe", "Dashlane.exe",
        "Enpass.exe", "NordPass.exe", "RoboForm.exe", "Proton Pass.exe", "keeperpasswordmanager.exe",
        "claude.exe", "claude_pzs8sxrjxfjjc",
        "SearchHost.exe", "StartMenuExperienceHost.exe",
    ],
    "denied_window_classes": [
        "ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow", "mintty",
        "VirtualConsoleClass", "PuTTY",
    ],
    "click_only_apps": [
        "Code.exe", "Code - Insiders.exe", "Cursor.exe", "Windsurf.exe", "Trae.exe", "Zed.exe", "devenv.exe",
        "idea64.exe", "pycharm64.exe", "webstorm64.exe", "clion64.exe", "goland64.exe", "rider64.exe",
        "phpstorm64.exe", "rubymine64.exe", "datagrip64.exe", "studio64.exe",
    ],
}

_OFF_LIMITS = ("Computer Use may not control {what}: terminals, Windows security and sign-in prompts, "
               "password managers and Claude's own windows are off limits.")
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
_SHELL_HOSTS = {"startmenuexperiencehost.exe", "searchhost.exe", "shellexperiencehost.exe",
                "textinputhost.exe", "shellhost.exe"}
_START_AND_SEARCH = {"startmenuexperiencehost.exe", "searchhost.exe"}
_RUN_DIALOG_TITLES = {"run", "\u8fd0\u884c", "\u57f7\u884c"}
_BUTTONS = {"left": "left", "l": "left", "right": "right", "r": "right", "middle": "middle", "m": "middle"}
_MODIFIER_KEYS = {0x10, 0x11, 0x12, 0xA1, 0xA3, 0xA5}
_OWNER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "owner.json")
_STOPPED = ("The user pressed Esc to stop computer use. Do not send more input until the user asks you to continue.")
_LOCKED = "The Windows desktop is locked or showing a secure prompt. Stop and ask the user to unlock it."

DESKTOP = 0
_CLICKS = {"left_click": ("left", 1, "Clicked"), "right_click": ("right", 1, "Right-clicked"),
           "middle_click": ("middle", 1, "Middle-clicked"), "double_click": ("left", 2, "Double-clicked"),
           "triple_click": ("left", 3, "Triple-clicked")}
_SCROLL = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OBSERVE_ACTIONS = ("screenshot", "zoom", "cursor_position")
INPUT_ACTIONS = ("left_click", "right_click", "middle_click", "double_click", "triple_click", "left_click_drag",
                 "mouse_move", "left_mouse_down", "left_mouse_up", "scroll", "type", "key", "hold_key", "wait")
COMPUTER_ACTIONS = OBSERVE_ACTIONS + INPUT_ACTIONS
_POINTER_ACTIONS = (*_CLICKS, "left_click_drag", "mouse_move", "left_mouse_down", "left_mouse_up", "scroll")
_ELEMENT_TOOLS = ("click_element", "set_value", "activate_window")
_SETTLE = {"mouse_move": (60, 300), "left_mouse_down": (60, 300), "wait": (0, 0)}
_BATCH_BUDGET_S = 75


@dataclass
class Result:
    text: str
    image: bytes | None = None
    mime: str | None = None


@dataclass
class Shot:
    id: str
    hwnd: int
    off_x: float
    off_y: float
    sx: float
    sy: float
    width: int
    height: int
    frame_size: tuple[int, int]
    zoom: bool


@dataclass
class _Before:
    windows: set
    focus: int
    watch: object
    mark: int | None


def _intersects(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _uncovered(rect, covers) -> list[tuple]:
    parts = [tuple(rect)]
    for c in covers:
        remaining = []
        for p in parts:
            if not _intersects(p, c):
                remaining.append(p)
                continue
            if c[1] > p[1]:
                remaining.append((p[0], p[1], p[2], c[1]))
            if c[3] < p[3]:
                remaining.append((p[0], c[3], p[2], p[3]))
            top, bottom = max(p[1], c[1]), min(p[3], c[3])
            if c[0] > p[0]:
                remaining.append((p[0], top, c[0], bottom))
            if c[2] < p[2]:
                remaining.append((c[2], top, p[2], bottom))
        parts = remaining
        if not parts:
            break
    return parts


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _is_point(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)


class ComputerUse:
    def __init__(self, config: dict | None = None) -> None:
        self.cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.acc = Accessibility()
        self.catalog = AppCatalog()
        self.lock = native.NamedMutex("Local\\ClaudeWinCU.Input", 15000, "another session is sending input; try again")
        self.presence = Presence(show_banner=self.cfg["show_banner"], linger_s=self.cfg["banner_linger_s"],
                                 yield_quiet_s=0.8 if self.cfg["yield_to_user"] else 0.0)
        self.presence.on_stop = native.release_buttons
        self._shots: dict[str, Shot] = {}
        self._latest: dict[int, str] = {}
        self._trees: dict[int, Snapshot] = {}
        self._stale: set[int] = set()
        self._unseen: set[int] = set()
        self._slow_web: set[int] = set()
        self._integrity: int | None = None
        self._ident: dict[int, tuple[float, str, str]] = {}
        self._seq = 0
        self._denied_apps = [s.lower() for s in self.cfg["denied_apps"]]
        self._denied_classes = {s.lower() for s in self.cfg["denied_window_classes"]}
        self._click_only = {s.lower() for s in self.cfg["click_only_apps"]}
        self._cancel: threading.Event | None = None
        self._sending = False
        native.set_checkpoint(self._checkpoint)

    def _identity(self, hwnd: int) -> tuple[str, str]:
        pid, _ = native.window_pid_tid(hwnd)
        if native.window_class(hwnd) == "ApplicationFrameWindow":
            for child in native.enum_child_windows(hwnd):
                if native.window_class(child) == "Windows.UI.Core.CoreWindow":
                    child_pid, _ = native.window_pid_tid(child)
                    if child_pid and child_pid != pid:
                        pid = child_pid
                        break
        hit = self._ident.get(pid)
        now = time.monotonic()
        if hit and now - hit[0] < 10:
            return hit[1], hit[2]
        exe, aumid = native.process_image_path(pid), native.process_aumid(pid)
        self._ident[pid] = (now, exe, aumid)
        return exe, aumid

    def _app_denied(self, exe: str, app_id: str) -> bool:
        base = os.path.basename(exe).lower()
        ident = app_id.lower()
        for pattern in self._denied_apps:
            if pattern.endswith(".exe"):
                if base == pattern or os.path.basename(ident) == pattern:
                    return True
            elif pattern in ident:
                return True
        return False

    def _denial(self, hwnd: int) -> str | None:
        cls = native.window_class(hwnd)
        exe, aumid = self._identity(hwnd)
        base = os.path.basename(exe)
        if not exe:
            return "Computer Use cannot identify the app that owns this window, so it is off limits."
        if cls.lower() in self._denied_classes or self._app_denied(exe, aumid or exe):
            if base.lower() in _START_AND_SEARCH:
                return "The Start menu and Windows search are off limits. Open apps with open_application."
            return _OFF_LIMITS.format(what=base or cls)
        if (base.lower() == "explorer.exe" and cls == "#32770"
                and native.window_text(hwnd).strip().lower() in _RUN_DIALOG_TITLES):
            return "The Windows Run dialog is off limits for Computer Use."
        return None

    def _full_control(self, hwnd: int, what: str) -> None:
        if not hwnd:
            return
        base = os.path.basename(self._identity(hwnd)[0])
        if base.lower() in self._click_only:
            raise CUError(f"{base} is a code editor with a built-in terminal, so Computer Use may only look, "
                          f"left-click and scroll there; {what} is refused. Edit files and run commands with "
                          "the file and shell tools instead.")

    def _busy(self) -> str | None:
        markers = self.cfg["busy_markers"]
        if not markers:
            return None
        for h in native.enum_windows():
            if not native.IsWindowVisible(h) or native.is_cloaked(h):
                continue
            cls, title = native.window_class(h), native.window_text(h)
            for m in markers:
                if m.get("class", cls) == cls and m.get("title_contains", "").lower() in title.lower():
                    return title or cls
        return None

    def _other_session(self) -> bool:
        try:
            with open(_OWNER_FILE, encoding="utf-8") as f:
                owner = json.load(f)
        except (OSError, ValueError):
            return False
        other = owner.get("pid")
        return bool(other and other != os.getpid() and time.time() - owner.get("time", 0) < self.cfg["session_hold_s"]
                    and native.process_image_path(other))

    @staticmethod
    def _claim() -> None:
        try:
            os.makedirs(os.path.dirname(_OWNER_FILE), exist_ok=True)
            scratch = f"{_OWNER_FILE}.{os.getpid()}"
            with open(scratch, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "time": time.time()}, f)
            os.replace(scratch, _OWNER_FILE)
        except OSError:
            pass

    def _checkpoint(self) -> None:
        if self._cancel is not None and self._cancel.is_set():
            raise Cancelled("the client cancelled the call")
        if self._sending and self.presence.stopped():
            raise CUError(_STOPPED)

    def _guard(self) -> None:
        if native.input_desktop_name() != "Default":
            raise CUError(_LOCKED)
        holder = self._busy()
        if holder:
            raise CUError(f"Another agent is controlling this desktop right now ({holder!r}), so nothing was sent. "
                          "Wait for it to finish, or ask the user how to proceed.")
        if self._other_session():
            raise CUError("Another Claude session is using this computer right now, so nothing was sent. "
                          "Wait for it to finish, or ask the user which session should carry on.")
        refusal = self.presence.begin_action()
        if refusal:
            raise CUError(refusal)
        self._claim()
        deadline = time.monotonic() + 1.5
        while (held := native.held_modifiers()) and time.monotonic() < deadline:
            time.sleep(0.05)
        if held:
            self.presence.end_action(False)
            raise CUError(f"{' and '.join(held)} is being held down on the keyboard, so nothing was sent.")

    @contextlib.contextmanager
    def _input(self, guarded: bool = True, sends: bool = True):
        with self.lock:
            if guarded:
                self._guard()
            self._sending = guarded
            try:
                yield
            except BaseException:
                native.release_buttons()
                self._stale.update(self._trees)
                raise
            finally:
                self._sending = False
                self.presence.end_action(sends)

    def _reachable(self, hwnd: int) -> None:
        pid, _ = native.window_pid_tid(hwnd)
        theirs = native.process_integrity(pid)
        if self._integrity is None:
            self._integrity = native.process_integrity(native.GetCurrentProcessId()) or 0
        if theirs is not None and theirs > self._integrity:
            raise CUError("That window belongs to an app running with higher privileges than Claude Code, and "
                          "Windows discards input sent to it. It can only be operated by hand, or with Claude "
                          "Code started as administrator.")

    def _is_candidate(self, hwnd: int) -> bool:
        if not native.IsWindowVisible(hwnd) or native.is_cloaked(hwnd):
            return False
        if native.window_class(hwnd) in _SHELL_CLASSES:
            return False
        ex = native.window_exstyle(hwnd)
        if ex & (native.WS_EX_TOOLWINDOW | native.WS_EX_NOACTIVATE) and not ex & native.WS_EX_APPWINDOW:
            return False
        if not native.window_text(hwnd) and native.window_style(hwnd) & native.WS_CAPTION != native.WS_CAPTION:
            return False
        if not native.IsIconic(hwnd):
            l, t, r, b = native.frame_rect(hwnd)
            if r - l < 8 or b - t < 8:
                return False
        exe, _ = self._identity(hwnd)
        return os.path.basename(exe).lower() not in _SHELL_HOSTS

    def _windows(self) -> list[int]:
        return [h for h in native.enum_windows() if self._is_candidate(h) and not self._denial(h)]

    def _window(self, hwnd: int) -> dict:
        exe, aumid = self._identity(hwnd)
        w = {"id": hwnd, "app": aumid or exe, "title": native.window_text(hwnd)}
        if native.IsIconic(hwnd):
            w["minimized"] = True
        else:
            vx, vy, vw, vh = native.virtual_screen()
            width, height, _ = self._desktop_size()
            l, t, r, b = native.frame_rect(hwnd)
            w["rect"] = [int((l - vx) * width / vw), int((t - vy) * height / vh),
                         int((r - vx) * width / vw), int((b - vy) * height / vh)]
        if hwnd == native.foreground_window():
            w["foreground"] = True
        return w

    def _target(self, window_id) -> int:
        hwnd = int(window_id)
        if not native.IsWindow(hwnd):
            raise CUError(f"Window {hwnd} is no longer open. Call list_windows for current windows.")
        reason = self._denial(hwnd)
        if reason:
            raise CUError(reason)
        if not self._is_candidate(hwnd):
            raise CUError(f"{hwnd} is not a targetable window. Use an id returned by list_windows or list_apps.")
        return hwnd

    @staticmethod
    def _owned_by(hwnd: int, owner: int) -> bool:
        cur = hwnd
        for _ in range(16):
            cur = native.window_owner(cur)
            if not cur:
                return False
            if cur == owner:
                return True
        return False

    def _is_transient(self, h: int) -> bool:
        if not native.IsWindowVisible(h) or native.is_cloaked(h):
            return False
        if native.window_exstyle(h) & native.WS_EX_TRANSPARENT or native.window_class(h) in _SHELL_CLASSES:
            return False
        l, t, r, b = native.frame_rect(h)
        return r - l >= 2 and b - t >= 2 and not self._is_candidate(h)

    def _same_app(self, h: int, hwnd: int, parents: dict[int, int]) -> bool:
        pid, _ = native.window_pid_tid(hwnd)
        cur, _ = native.window_pid_tid(h)
        if cur != pid and not parents:
            parents.update(native.parent_pids())
        for _ in range(6):
            if cur == pid:
                return True
            cur = parents.get(cur, 0)
            if not cur:
                break
        return False

    def _popups(self, hwnd: int) -> list[int]:
        parents: dict[int, int] = {}
        in_front = self._has_focus(hwnd)
        out = []
        for h in native.enum_windows():
            if h == hwnd or not self._is_transient(h):
                continue
            if self._owned_by(h, hwnd) or (in_front and self._same_app(h, hwnd, parents)):
                out.append(h)
        out.reverse()
        return out

    @staticmethod
    def _window_image(hwnd: int) -> Image.Image | None:
        if native.IsHungAppWindow(hwnd):
            return None
        img = native.print_window(hwnd)
        if img is None:
            return None
        wl, wt, _, _ = native.window_rect(hwnd)
        fl, ft, fr, fb = native.frame_rect(hwnd)
        img = img.crop((fl - wl, ft - wt, fr - wl, fb - wt))
        return None if native.is_blank(img) else img

    @staticmethod
    def _frame(target: int) -> tuple[int, int, int, int]:
        if target != DESKTOP:
            return native.frame_rect(target)
        vx, vy, vw, vh = native.virtual_screen()
        return vx, vy, vx + vw, vy + vh

    def _capture(self, hwnd: int) -> tuple[Image.Image, int, int, str]:
        if hwnd == DESKTOP:
            return self._desktop_capture()
        frame = native.frame_rect(hwnd)
        union = list(frame)
        chosen: list[tuple[int, tuple]] = []
        pending = [(p, native.frame_rect(p)) for p in self._popups(hwnd)]
        z_order = [p for p, _ in pending]
        grew = True
        while grew:
            grew = False
            near = (union[0] - 24, union[1] - 24, union[2] + 24, union[3] + 24)
            for item in pending[:]:
                if _intersects(item[1], near):
                    r = item[1]
                    union = [min(union[0], r[0]), min(union[1], r[1]), max(union[2], r[2]), max(union[3], r[3])]
                    chosen.append(item)
                    pending.remove(item)
                    grew = True
        vx, vy, vw, vh = native.virtual_screen()
        union = [max(union[0], vx), max(union[1], vy), min(union[2], vx + vw), min(union[3], vy + vh)]
        if union[2] - union[0] < 1 or union[3] - union[1] < 1:
            raise CUError("The window is entirely off screen.")

        base = self._window_image(hwnd)
        if base is None:
            return native.grab_screen(*union), union[0], union[1], "screen"
        canvas = Image.new("RGB", (union[2] - union[0], union[3] - union[1]), (24, 24, 24))
        canvas.paste(base, (frame[0] - union[0], frame[1] - union[1]))
        for popup, rect in sorted(chosen, key=lambda item: z_order.index(item[0])):
            img = self._window_image(popup)
            if img is None:
                clipped = (max(rect[0], union[0]), max(rect[1], union[1]), min(rect[2], union[2]), min(rect[3], union[3]))
                if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
                    continue
                img, rect = native.grab_screen(*clipped), clipped
            canvas.paste(img, (rect[0] - union[0], rect[1] - union[1]))
        return canvas, union[0], union[1], "window"

    def _desktop_capture(self) -> tuple[Image.Image, int, int, str]:
        vx, vy, vw, vh = native.virtual_screen()
        screen = (vx, vy, vx + vw, vy + vh)
        canvas = native.grab_screen(*screen)
        draw = ImageDraw.Draw(canvas)
        above: list[tuple] = []
        for h in native.enum_windows():
            if not native.IsWindowVisible(h) or native.is_cloaked(h) or native.IsIconic(h):
                continue
            if native.window_exstyle(h) & native.WS_EX_TRANSPARENT:
                continue
            l, t, r, b = native.frame_rect(h)
            rect = (max(l, screen[0]), max(t, screen[1]), min(r, screen[2]), min(b, screen[3]))
            if rect[2] - rect[0] < 2 or rect[3] - rect[1] < 2:
                continue
            if self._denial(h):
                for part in _uncovered(rect, above):
                    box = (part[0] - vx, part[1] - vy, part[2] - vx - 1, part[3] - vy - 1)
                    draw.rectangle(box, fill=(58, 58, 58))
                    if box[2] - box[0] > 170 and box[3] - box[1] > 24:
                        draw.text((box[0] + 8, box[1] + 6), "off-limits window", fill=(170, 170, 170))
            above.append(rect)
        return canvas, vx, vy, "desktop"

    def _encode(self, img: Image.Image) -> tuple[bytes, str]:
        buf = io.BytesIO()
        img.save(buf, "PNG", compress_level=4)
        if buf.tell() <= self.cfg["max_png_bytes"]:
            return buf.getvalue(), "image/png"
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        return buf.getvalue(), "image/jpeg"

    def _remember(self, shot: Shot) -> Shot:
        self._shots[shot.id] = shot
        if not shot.zoom:
            self._latest[shot.hwnd] = shot.id
        mine = [s for s in self._shots.values() if s.hwnd == shot.hwnd]
        for old in mine[:-12]:
            if old.id != self._latest.get(shot.hwnd):
                del self._shots[old.id]
        for hwnd in [h for h in self._latest if h != DESKTOP and not native.IsWindow(h)]:
            self._forget(hwnd)
        return shot

    def _forget(self, hwnd: int) -> None:
        self._latest.pop(hwnd, None)
        self._trees.pop(hwnd, None)
        self._stale.discard(hwnd)
        self._unseen.discard(hwnd)
        self._slow_web.discard(hwnd)
        for key in [k for k, s in self._shots.items() if s.hwnd == hwnd]:
            del self._shots[key]

    def _screenshot(self, hwnd: int, zoom: dict | None) -> tuple[str, bytes, str]:
        canvas, ox, oy, method = self._capture(hwnd)
        if hwnd == DESKTOP:
            native.draw_cursor(canvas, ox, oy)
        frame = self._frame(hwnd)
        off_x, off_y = ox - frame[0], oy - frame[1]
        limit = self.cfg["max_image_edge"]
        if zoom:
            ref = self._shots.get(self._latest.get(hwnd, ""))
            if hwnd == DESKTOP:
                rsx = rsy = self._desktop_size()[2]
                rox = roy = 0.0
            else:
                rsx, rsy, rox, roy = (ref.sx, ref.sy, ref.off_x, ref.off_y) if ref else (1.0, 1.0, 0.0, 0.0)
            x0 = rox + zoom["x"] / rsx - off_x
            y0 = roy + zoom["y"] / rsy - off_y
            x1 = x0 + zoom["width"] / rsx
            y1 = y0 + zoom["height"] / rsy
            box = (max(0, int(x0)), max(0, int(y0)), min(canvas.width, round(x1)), min(canvas.height, round(y1)))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                raise CUError("The zoom region is empty or outside the picture.")
            canvas = canvas.crop(box)
            off_x, off_y = off_x + box[0], off_y + box[1]
            factor = min(limit / max(canvas.size), 3.0)
        else:
            factor = min(1.0, limit / max(canvas.size))
        source = canvas.size
        if factor != 1.0:
            size = (max(1, round(source[0] * factor)), max(1, round(source[1] * factor)))
            canvas = canvas.resize(size, Image.LANCZOS)
        self._seq += 1
        shot = self._remember(Shot(f"s{self._seq}", hwnd, off_x, off_y, canvas.width / source[0],
                                   canvas.height / source[1], canvas.width, canvas.height,
                                   (frame[2] - frame[0], frame[3] - frame[1]), bool(zoom)))
        note = f"screenshot: {shot.width}x{shot.height}"
        if zoom:
            note += f", zoomed x{shot.sx:.2f} for reading only; coordinates still refer to the full screenshot"
        else:
            if factor != 1.0:
                note += f" (scaled x{shot.sx:.3f} from {source[0]}x{source[1]}; give coordinates in pixels of this image)"
            if hwnd != DESKTOP:
                note += f". This is the window's own frame: pass window_id={hwnd} with coordinates taken from it"
            else:
                note += ". The pointer is drawn in; actions without a coordinate happen there"
        if method == "screen":
            note += "; taken from the screen because the window could not be rendered on its own, so anything covering it is included"
        data, mime = self._encode(canvas)
        return note, data, mime

    def _read_tree(self, hwnd: int) -> Snapshot:
        popups = [(p, native.frame_rect(p)) for p in reversed(self._popups(hwnd))]
        pages = [] if hwnd in self._slow_web else native.web_views(hwnd)
        self.acc.wake(pages)
        deadline = time.monotonic() + 3
        while True:
            try:
                snap = self.acc.snapshot(hwnd, popups, self.cfg["max_tree_elements"],
                                         self.cfg["max_tree_tokens"], self.cfg["max_document_chars"])
            except TreeUnavailable:
                raise CUError("The app did not answer the accessibility request; it is busy, or stuck behind a "
                              "dialog it opened itself. Work from a screenshot with coordinates and keys instead.") from None
            if snap.truncated or sum(kind == CT_DOCUMENT for kind, _ in snap.labels) >= len(pages):
                break
            if time.monotonic() >= deadline:
                snap.pages_missing = True
                self._slow_web.add(hwnd)
                break
            native.pause(0.15)
        self._trees[hwnd] = snap
        self._stale.discard(hwnd)
        return snap

    def _foreground(self) -> str:
        fg = native.foreground_window()
        if not fg:
            return "none"
        if self._denial(fg):
            return "an off-limits window"
        if self._is_candidate(fg):
            return _dumps(self._window(fg))
        return repr(native.window_text(fg) or native.window_class(fg))

    def _desktop_state(self, zoom: dict | None) -> Result:
        _, _, width, height = native.virtual_screen()
        lines = [f"desktop: {width}x{height}; keyboard focus: {self._foreground()}"]
        note, data, mime = self._screenshot(DESKTOP, zoom)
        lines.append(note)
        if not zoom:
            showing = [self._window(h) for h in self._windows() if not native.IsIconic(h)]
            if showing:
                lines.append("windows (front to back, rect in screenshot pixels):\n" + "\n".join(map(_dumps, showing)))
        return Result("\n".join(lines), data, mime)

    def _state(self, hwnd: int, include_screenshot: bool, include_text: bool, zoom: dict | None = None) -> Result:
        if native.input_desktop_name() != "Default":
            raise CUError(_LOCKED)
        if hwnd == DESKTOP:
            return self._desktop_state(zoom)
        if native.IsIconic(hwnd):
            raise CUError("The window is minimized. Call activate_window to restore it first.")
        lines = ["window: " + _dumps(self._window(hwnd))]
        if not native.IsWindowEnabled(hwnd):
            lines.append(self._blocked(hwnd))
        data = mime = None
        if include_screenshot or zoom:
            note, data, mime = self._screenshot(hwnd, zoom)
            lines.append(note)
        if include_text:
            snap = self._read_tree(hwnd)
            self._unseen.discard(hwnd)
            if snap.focused:
                lines.append("focused_element: " + snap.focused)
            if snap.selected_text:
                lines.append("selected_text: " + _dumps(snap.selected_text))
            if snap.selected:
                lines.append("selected_elements:\n" + "\n".join(snap.selected))
            if snap.document_text:
                lines.append("document_text: " + _dumps(snap.document_text))
            lines.append("tree:\n" + "\n".join(snap.lines))
            if snap.truncated:
                lines.append(f"(tree cut off after {len(snap.elements)} elements)")
            if snap.pages_missing:
                lines.append("(a web page in this window is not readable yet; read the tree again in a moment, "
                             "or work from a screenshot)")
        return Result("\n".join(lines), data, mime)

    def _has_focus(self, hwnd: int) -> bool:
        fg = native.foreground_window()
        return fg == hwnd or bool(fg and self._is_transient(fg)
                                  and (self._owned_by(fg, hwnd) or self._same_app(fg, hwnd, {})))

    def _blocked(self, hwnd: int) -> str:
        others = [h for h in self._windows() if h != hwnd]
        dialogs = [h for h in others if self._owned_by(h, hwnd)]
        if not dialogs:
            pid, _ = native.window_pid_tid(hwnd)
            dialogs = [h for h in others if native.window_owner(h) and native.window_pid_tid(h)[0] == pid]
        if not dialogs:
            return ("This window is disabled, usually by a dialog of its app that is not showing yet. "
                    "Call list_windows to find it.")
        return "This window is blocked by a modal dialog. Target the dialog instead: " + _dumps(
            [self._window(h) for h in dialogs])

    def _focus(self, hwnd: int) -> None:
        if not native.IsWindowEnabled(hwnd):
            raise CUError(self._blocked(hwnd))
        self._reachable(hwnd)
        if not native.activate(hwnd, lambda _fg: self._has_focus(hwnd)):
            raise CUError("Could not bring the window to the foreground. Call list_windows and retry once.")
        time.sleep(0.06)

    def _desktop_size(self) -> tuple[int, int, float]:
        _, _, width, height = native.virtual_screen()
        scale = min(1.0, self.cfg["max_image_edge"] / max(width, height))
        return max(1, round(width * scale)), max(1, round(height * scale)), scale

    def _locate(self, target: int, coordinate) -> tuple[int, int]:
        if not _is_point(coordinate):
            raise CUError("coordinate must be [x, y] in pixels of the latest screenshot.")
        x, y = coordinate
        if target == DESKTOP:
            width, height, _ = self._desktop_size()
            if not (0 <= x < width and 0 <= y < height):
                raise CUError(f"({x}, {y}) is outside the desktop screenshot, which is {width}x{height}.")
            vx, vy, vw, vh = native.virtual_screen()
            return int(vx + (x + 0.5) * vw / width), int(vy + (y + 0.5) * vh / height)
        frame = native.frame_rect(target)
        shot = self._shots.get(self._latest.get(target, ""))
        if shot is None:
            return frame[0] + int(x), frame[1] + int(y)
        if (frame[2] - frame[0], frame[3] - frame[1]) != shot.frame_size:
            raise CUError("The window changed size since its last screenshot. Take a new screenshot of it.")
        if not (0 <= x < shot.width and 0 <= y < shot.height):
            raise CUError(f"({x}, {y}) is outside the window's screenshot, which is {shot.width}x{shot.height}.")
        return (int(frame[0] + shot.off_x + (x + 0.5) / shot.sx),
                int(frame[1] + shot.off_y + (y + 0.5) / shot.sy))

    def _operable(self, target: int, sx: int, sy: int) -> int:
        vx, vy, vw, vh = native.virtual_screen()
        if not (vx <= sx < vx + vw and vy <= sy < vy + vh):
            raise CUError("That point is off screen.")
        under = native.window_from_point(sx, sy)
        root = native.window_root(under) if under else 0
        if target == DESKTOP:
            if root and self._denial(root):
                raise CUError("That point is on an off-limits window (shown blanked in screenshots). Terminals, "
                              "security and sign-in prompts, password managers and Claude's own windows cannot "
                              "be operated.")
            if root:
                self._reachable(root)
            return root
        if root == target or (root and root in self._popups(target)):
            return target
        if not root:
            other = "nothing"
        elif self._is_candidate(root) and not self._denial(root):
            other = _dumps(self._window(root))
        else:
            other = repr(native.window_text(root) or native.window_class(root))
        raise CUError(f"The point is over a non-target window ({other}). Call activate_window, look again and "
                      "retry once; if that window is a dialog, target it directly.")

    def _aim(self, target: int, coordinate, beyond_click: str | None = None) -> tuple[int, int]:
        point = self._locate(target, coordinate) if coordinate is not None else native.cursor_pos()
        reached = self._operable(target, *point)
        if beyond_click:
            self._full_control(reached, beyond_click)
        return point

    def _keyboard(self, target: int, what: str):
        if target != DESKTOP:
            self._full_control(target, what)
            return lambda: self._has_focus(target)
        fg = native.foreground_window()
        if fg and self._denial(fg):
            raise CUError("Keyboard input would go to an off-limits window. Click the window you want first.")
        if fg:
            self._reachable(fg)
            self._full_control(fg, what)
        return lambda: native.foreground_window() == fg

    def _modifiers(self, text) -> list:
        if not text:
            return []
        chord = self._chord(text)
        if any(vk not in _MODIFIER_KEYS for vk, _ in chord):
            raise CUError("Only shift, ctrl and alt can be held during a click or a scroll.")
        return chord

    def _press(self, chord: list, hold_s: float = 0.0) -> None:
        if any(vk == 0x1B for vk, _ in chord):
            self.presence.own_escape()
        native.press_chord(chord, hold_s)

    def _enter_text(self, text: str, still_focused) -> str:
        body = text.rstrip("\r\n")
        enters = text[len(body):].replace("\r\n", "\n").replace("\r", "\n").count("\n")
        done = []
        if "\n" in body or "\r" in body or len(body) > 400:
            replaced = native.paste_text(body)
            done.append(f"Pasted {len(body)} characters through the clipboard"
                        + (" (what the clipboard held before was not text and is gone)" if replaced else ""))
        elif body:
            native.type_unicode(body, still_focused)
            done.append(f"Typed {len(body)} characters")
        for _ in range(enters):
            if not still_focused():
                raise CUError("Keyboard focus moved to another window, so Enter was not pressed.")
            self._press([(0x0D, None)])
        if enters:
            done.append(("pressed" if done else "Pressed") + " Enter" + (f" {enters} times" if enters > 1 else ""))
        return " and ".join(done)

    @staticmethod
    def _chord(text) -> list:
        try:
            return parse_chord(str(text))
        except ChordError as e:
            raise CUError(str(e)) from e

    @classmethod
    def _chords(cls, text) -> list[list]:
        return [cls._chord(part) for part in re.sub(r"\s*\+\s*", "+", str(text)).split()]

    def _element(self, hwnd: int, index, name: str | None = None) -> tuple[object, int]:
        if name is not None:
            index = self._named(hwnd, name)
        elif index is None:
            raise CUError("Give element_name or element_index.")
        snap = self._trees.get(hwnd)
        if snap is None:
            raise CUError("No accessibility tree for this window yet. Call get_window_state first.")
        if not isinstance(index, int) or not 0 <= index < len(snap.elements):
            raise CUError(f"element_index {index} is not in the latest accessibility tree "
                          f"(0..{len(snap.elements) - 1}). Call get_window_state for the current one.")
        if name is None and hwnd in self._unseen:
            raise CUError("The indexes of this window changed: its tree was read again to look up an element by "
                          "name. Call get_window_state for the current indexes, or give element_name.")
        return snap.elements[index], index

    def _named(self, hwnd: int, name: str, kinds: set | None = None) -> int:
        if hwnd in self._stale or hwnd not in self._trees:
            self._read_tree(hwnd)
            self._unseen.add(hwnd)
        snap = self._trees[hwnd]
        wanted = " ".join(name.split())
        labels = [(i, label) for i, (kind, label) in enumerate(snap.labels) if kinds is None or kind in kinds]
        hits = [i for i, label in labels if label == wanted]
        if not hits:
            hits = [i for i, label in labels if label.casefold() == wanted.casefold()]
        if not hits:
            names = list(dict.fromkeys(label for _, label in labels if label))
            if kinds is not None:
                raise CUError(f'There is no "{wanted}" to choose. Choices: ' + ", ".join(f'"{n}"' for n in names[:40]) + ".")
            close = difflib.get_close_matches(wanted, names, n=5, cutoff=0.5)
            hint = " Similar names: " + ", ".join(f'"{c}"' for c in close) + "." if close else ""
            raise CUError(f'No element is named "{wanted}" in this window.{hint}')
        clickable = [i for i in hits if snap.labels[i][0] in INTERACTIVE]
        if len(clickable) == 1:
            return clickable[0]
        if len(hits) == 1:
            return hits[0]
        spots = {}
        for i in clickable or hits:
            spots.setdefault(self.acc.rect(snap.elements[i]), i)
        if len(spots) == 1:
            return next(iter(spots.values()))
        options = "; ".join(snap.lines[i].strip() for i in (clickable or hits)[:8])
        raise CUError(f'"{wanted}" matches several elements: {options}. Pass element_index for the one you mean.')

    def _element_center(self, element) -> tuple[int, int] | None:
        rect = self.acc.rect(element)
        if rect is None:
            self.acc.scroll_into_view(element)
            time.sleep(0.15)
            rect = self.acc.rect(element)
        if rect is None:
            return None
        return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2

    def _watch(self, target: int, point: tuple[int, int] | None = None):
        if target != DESKTOP:
            return lambda: self._capture(target)[0]
        vx, vy, vw, vh = native.virtual_screen()
        root = native.window_root(native.window_from_point(*point)) if point else native.foreground_window()
        if root and native.window_class(root) not in _SHELL_CLASSES and not native.IsIconic(root):
            l, t, r, b = native.frame_rect(root)
        else:
            l, t, r, b = vx, vy, vx + vw, vy + vh
        rect = (max(l, vx), max(t, vy), min(r, vx + vw), min(b, vy + vh))
        if rect[2] - rect[0] < 2 or rect[3] - rect[1] < 2:
            rect = (vx, vy, vx + vw, vy + vh)
        return lambda: native.grab_screen(*rect)

    def _before(self, target: int, point: tuple[int, int] | None = None) -> _Before:
        watch = self._watch(target, point)
        try:
            mark = None if target != DESKTOP and native.IsIconic(target) else zlib.crc32(watch().tobytes())
        except (CUError, OSError):
            mark = None
        return _Before(set(self._windows()), native.foreground_window(), watch, mark)

    def _settle(self, watch, least_ms: int | None = None, most_ms: int | None = None) -> Image.Image | None:
        least = self.cfg["settle_ms"] if least_ms is None else least_ms
        most = self.cfg["settle_max_ms"] if most_ms is None else most_ms
        native.pause(least / 1000)
        deadline = time.monotonic() + (most - least) / 1000
        previous = None
        while True:
            try:
                picture = watch()
            except (CUError, OSError):
                return None
            mark = picture.resize((64, 36), Image.BOX).convert("L")
            if previous is not None and ImageStat.Stat(ImageChops.difference(previous, mark)).mean[0] < 0.4:
                return picture
            if time.monotonic() >= deadline:
                return picture
            previous = mark
            native.pause(0.08)

    def _ack(self, target: int, summary: str, before: _Before, include_text: bool = False,
             settle: tuple[int, int] | None = None) -> Result:
        self._stale.update(self._trees)
        gone = target != DESKTOP and (not native.IsWindow(target) or not native.IsWindowVisible(target))
        picture = None if gone else self._settle(before.watch, *(settle or (None, None)))
        notes = [summary if summary.endswith(".") else summary + "."]
        gone = target != DESKTOP and (not native.IsWindow(target) or not native.IsWindowVisible(target))
        if gone:
            self._forget(target)
            notes.append("That window is no longer open.")
        elif picture is not None and before.mark is not None:
            notes.append("Nothing visible changed." if zlib.crc32(picture.tobytes()) == before.mark
                         else "The picture changed.")
        fresh = [self._window(h) for h in self._windows() if h not in before.windows]
        if fresh:
            notes.append("new_windows: " + _dumps(fresh))
        if native.foreground_window() != before.focus:
            notes.append("keyboard focus: " + self._foreground())
        if include_text and not gone and target != DESKTOP:
            try:
                notes.append(self._state(target, False, True).text)
            except CUError as e:
                notes.append(f"The tree was not read: {e}")
        return Result("\n".join(notes))

    def _do(self, action: str, a: dict, target: int) -> str:
        if action == "wait":
            seconds = min(max(float(a.get("duration") or 1), 0.0), 30.0)
            native.pause(seconds)
            return f"Waited {seconds:g}s"
        where = a.get("coordinate")
        at = f"at {list(where)}" if where is not None else "at the pointer"
        if action == "left_mouse_up":
            if where is not None:
                try:
                    point = self._aim(target, where)
                except CUError as e:
                    native.release_buttons()
                    raise CUError(f"{e} The button was released where the pointer already was.") from None
                native.mouse_glide(*point)
                native.mouse_button("left", False, point)
            else:
                native.mouse_button("left", False)
            return f"Released the left button {at}"
        if target != DESKTOP:
            self._focus(target)
        if action in _CLICKS:
            button, count, label = _CLICKS[action]
            modifiers = self._modifiers(a.get("text"))
            plain = button == "left" and not modifiers
            point = self._aim(target, where, None if plain else action.replace("_", " "))
            with native.keys_held(modifiers):
                native.mouse_click(*point, button, count)
            return f"{label} {at}" + (f" holding {a['text']}" if modifiers else "")
        if action == "mouse_move":
            if where is None:
                raise CUError("mouse_move needs a coordinate.")
            native.mouse_glide(*self._locate(target, where))
            return f"Moved the pointer to {list(where)}"
        if action == "left_click_drag":
            if where is None or a.get("start_coordinate") is None:
                raise CUError("left_click_drag needs start_coordinate and coordinate.")
            modifiers = self._modifiers(a.get("text"))
            start = self._aim(target, a["start_coordinate"], "dragging")
            end = self._aim(target, where, "dragging")
            with native.keys_held(modifiers):
                native.mouse_drag(*start, *end)
            return f"Dragged from {list(a['start_coordinate'])} to {list(where)}"
        if action == "left_mouse_down":
            point = self._aim(target, where, "holding the mouse button")
            native.mouse_glide(*point)
            native.mouse_button("left", True, point)
            if self.presence.stopped():
                native.release_buttons()
                raise CUError(_STOPPED)
            return f"Pressed the left button {at}"
        if action == "scroll":
            direction = str(a.get("scroll_direction", "")).lower()
            if direction not in _SCROLL:
                raise CUError("scroll_direction must be up, down, left or right.")
            amount = a.get("scroll_amount", 3)
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise CUError("scroll_amount must be a positive number of wheel notches.")
            modifiers = self._modifiers(a.get("text"))
            point = self._aim(target, where, "scrolling with a key held" if modifiers else None)
            dx, dy = _SCROLL[direction]
            with native.keys_held(modifiers):
                native.mouse_scroll(*point, int(dx * amount * 120), int(dy * amount * 120))
            return f"Scrolled {direction} by {amount:g} {at}"
        if action in ("key", "hold_key"):
            if not a.get("text"):
                raise CUError(f"{action} needs text, for example ctrl+s.")
            chords = self._chords(a["text"])
            repeat = a.get("repeat", 1)
            if not isinstance(repeat, int) or not 1 <= repeat <= 100:
                raise CUError("repeat must be a whole number from 1 to 100.")
            hold = min(max(float(a.get("duration") or 1), 0.0), 30.0) if action == "hold_key" else 0.0
            still_focused = self._keyboard(target, "pressing keys")
            gap = 0.08 if len(chords) > 1 else 0.015
            pressed = 0
            for _ in range(repeat):
                for chord in chords:
                    if pressed:
                        native.pause(gap)
                        if not still_focused():
                            raise CUError(f"Keyboard focus moved to another window after {pressed} key presses; "
                                          "the rest were not sent. Look again before continuing.")
                    self._press(chord, hold)
                    pressed += 1
            return f"Pressed {a['text']}" + (f" {repeat} times" if repeat > 1 else "") + (f" for {hold:g}s" if hold else "")
        if action == "type":
            if not a.get("text"):
                raise CUError("type needs text.")
            return self._enter_text(a["text"], self._keyboard(target, "typing"))
        raise CUError(f"Unknown action {action!r}. Actions: " + ", ".join(COMPUTER_ACTIONS) + ".")

    def _point_of(self, action: str, a: dict, target: int) -> tuple[int, int] | None:
        if action not in _POINTER_ACTIONS:
            return None
        where = a.get("start_coordinate") if action == "left_click_drag" else a.get("coordinate")
        try:
            return self._locate(target, where) if where is not None else native.cursor_pos()
        except CUError:
            return None

    def act(self, action: str, window_id=None, **a) -> Result:
        try:
            target = self._target(window_id) if window_id else DESKTOP
        except CUError as e:
            if action != "left_mouse_up":
                raise
            native.release_buttons()
            raise CUError(f"{e} Any button Computer Use was holding has been released.") from None
        if action == "screenshot":
            return self._state(target, True, False)
        if action == "zoom":
            region = a.get("region")
            if not isinstance(region, (list, tuple)) or len(region) != 4 or region[2] <= region[0] or region[3] <= region[1]:
                raise CUError("zoom needs region [x0, y0, x1, y1] in pixels of the latest screenshot.")
            return self._state(target, False, False, zoom={"x": region[0], "y": region[1],
                                                         "width": region[2] - region[0],
                                                         "height": region[3] - region[1]})
        if action == "cursor_position":
            cx, cy = native.cursor_pos()
            if target == DESKTOP:
                vx, vy, vw, vh = native.virtual_screen()
                width, height, _ = self._desktop_size()
                return Result(f"pointer at [{int((cx - vx) * width / vw)}, {int((cy - vy) * height / vh)}]")
            frame = native.frame_rect(target)
            shot = self._shots.get(self._latest.get(target, ""))
            sx, sy, ox, oy = (shot.sx, shot.sy, shot.off_x, shot.off_y) if shot else (1.0, 1.0, 0.0, 0.0)
            return Result(f"pointer at [{int((cx - frame[0] - ox) * sx)}, {int((cy - frame[1] - oy) * sy)}] "
                          "in this window's screenshot")
        before = self._before(target, self._point_of(action, a, target))
        with self._input(guarded=action not in ("wait", "left_mouse_up"), sends=action != "wait"):
            try:
                summary = self._do(action, a, target)
            except (TypeError, ValueError) as e:
                raise CUError(f"Bad arguments for {action}: {e}") from e
        return self._ack(target, summary, before, settle=_SETTLE.get(action))

    def computer_batch(self, actions: list, screenshot_after: bool = True) -> Result:
        if not isinstance(actions, list) or not actions:
            raise CUError("actions must be a non-empty list of action objects.")
        before = self._before(DESKTOP)
        started = time.monotonic()
        notes: list[str] = []
        targets = set()
        with self.lock:
            for number, step in enumerate(actions, 1):
                arguments = dict(step) if isinstance(step, dict) else {}
                name = arguments.pop("action", None)
                try:
                    native.checkpoint()
                    if time.monotonic() - started > _BATCH_BUDGET_S:
                        raise CUError(f"the batch has run for {_BATCH_BUDGET_S}s, which is its limit")
                    if name in INPUT_ACTIONS:
                        target = self._target(arguments.pop("window_id")) if arguments.get("window_id") else DESKTOP
                        targets.add(target)
                        watch = self._watch(target, self._point_of(name, arguments, target))
                        with self._input(guarded=name not in ("wait", "left_mouse_up"), sends=name != "wait"):
                            notes.append(f"{number}. {self._do(name, arguments, target)}.")
                        self._stale.update(self._trees)
                        self._settle(watch, *_SETTLE.get(name, (120, 1200)))
                    elif name in _ELEMENT_TOOLS:
                        if "window_id" not in arguments:
                            raise CUError(f"{name} needs window_id.")
                        targets.add(self._target(arguments["window_id"]))
                        notes.append(f"{number}. " + getattr(self, name)(**arguments).text.split("\n")[0])
                    else:
                        raise CUError(f"{name!r} is not a batch step. Steps are the input actions "
                                      f"({', '.join(INPUT_ACTIONS)}) and {', '.join(_ELEMENT_TOOLS)}; "
                                      "the screenshot comes at the end.")
                except (CUError, ElementGone, COMError, OSError, TypeError, ValueError) as e:
                    native.release_buttons()
                    notes.append(f"{number}. FAILED: {self._explain(e)}")
                    if number < len(actions):
                        notes.append(f"Steps {number + 1}-{len(actions)} were not run.")
                    break
        fresh = [self._window(h) for h in self._windows() if h not in before.windows]
        if fresh:
            notes.append("new_windows: " + _dumps(fresh))
        if native.foreground_window() != before.focus:
            notes.append("keyboard focus: " + self._foreground())
        if not screenshot_after:
            return Result("\n".join(notes))
        only = next(iter(targets)) if len(targets) == 1 else DESKTOP
        if only != DESKTOP and (not native.IsWindow(only) or not native.IsWindowVisible(only) or native.IsIconic(only)):
            notes.append("The window the batch worked in is no longer showing; the desktop is shown instead.")
            only = DESKTOP
        try:
            state = self._state(only, True, False)
        except CUError as e:
            return Result("\n".join(notes) + f"\nNo screenshot: {e}")
        return Result("\n".join(notes) + "\n" + state.text, state.image, state.mime)

    def list_windows(self) -> Result:
        return Result("[\n" + ",\n".join(_dumps(self._window(h)) for h in self._windows()) + "\n]")

    def list_apps(self, query: str | None = None) -> Result:
        windows = [(h, self._window(h), os.path.normcase(self._identity(h)[0])) for h in self._windows()]
        usage = self.catalog.usage()
        running = {os.path.normcase(p) for p in native.running_image_paths()}
        claimed: set[int] = set()
        entries = []
        for app in self.catalog.installed():
            if self._app_denied(app.target, app.id):
                continue
            target = os.path.normcase(app.target) if app.target else ""
            mine = [w for h, w, exe in windows
                    if w["app"].lower() == app.id.lower() or (target and exe == target)]
            claimed.update(w["id"] for w in mine)
            entry = {"id": app.id, "displayName": app.name}
            if mine or (target and target in running):
                entry["isRunning"] = True
            count, when = usage.get(app.id.lower(), (0, ""))
            if when:
                entry["lastUsedDate"] = when
            if count:
                entry["useCount"] = count
            if mine:
                entry["windows"] = mine
            entries.append(entry)
        loose: dict[str, dict] = {}
        for h, w, exe in windows:
            if w["id"] in claimed:
                continue
            entry = loose.setdefault(w["app"], {"id": w["app"], "isRunning": True, "windows": [],
                                                "displayName": os.path.splitext(os.path.basename(w["app"]))[0]})
            entry["windows"].append(w)
        entries += loose.values()
        if query:
            q = query.lower()
            entries = [e for e in entries if q in e["displayName"].lower() or q in e["id"].lower()]
        entries.sort(key=lambda e: (not e.get("windows"), not e.get("isRunning"),
                                    -(e.get("useCount") or 0), e["displayName"].lower()))
        return Result("[\n" + ",\n".join(_dumps(e) for e in entries) + "\n]")

    def _executable(self, app: str) -> str:
        name = os.path.expandvars(app.strip().strip('"'))
        if not name.lower().endswith(".exe"):
            return ""
        if os.path.isfile(name):
            return os.path.abspath(name)
        if os.path.dirname(name):
            return ""
        wanted = name.lower()
        for h in self._windows():
            exe = self._identity(h)[0]
            if os.path.basename(exe).lower() == wanted:
                return exe
        for entry in self.catalog.installed():
            if os.path.basename(entry.target).lower() == wanted and os.path.isfile(entry.target):
                return entry.target
        return find_executable(name)

    def open_application(self, app: str, new_instance: bool = False) -> Result:
        entry = self.catalog.find(app)
        if entry is not None:
            if self._app_denied(entry.target, entry.id):
                raise CUError(_OFF_LIMITS.format(what=entry.name))
            target, label = entry.id, entry.name
        else:
            path = self._executable(app)
            if not path:
                raise CUError("Unknown app. Pass an id returned by list_apps, the full path of an .exe, or the "
                              "name of one such as mspaint.exe.")
            if self._app_denied(path, path):
                raise CUError(_OFF_LIMITS.format(what=os.path.basename(path)))
            target, label = path, os.path.basename(path)
        before = set(self._windows())
        exe = os.path.normcase(entry.target if entry is not None else target)
        already = []
        for h in self._windows():
            path, aumid = self._identity(h)
            if (exe and os.path.normcase(path) == exe) or aumid.lower() == target.lower():
                already.append(h)
        with self._input():
            if already and not new_instance:
                self._focus(already[0])
                return Result(f"{label} was already open; brought it to the front.\nwindows: "
                              + _dumps([self._window(h) for h in already]))
            try:
                shell_launch(target)
            except OSError as e:
                raise CUError(f"Could not start {label}: {e}") from e
            deadline = time.monotonic() + (2.5 if already else self.cfg["launch_wait_s"])
            fresh: list[int] = []
            while not fresh and time.monotonic() < deadline:
                native.pause(0.4)
                fresh = [h for h in self._windows() if h not in before]
        if fresh:
            native.pause(0.6)
            fresh = [h for h in self._windows() if h not in before]
            return Result(f"Started {label}.\nnew_windows: " + _dumps([self._window(h) for h in fresh]))
        still_open = [self._window(h) for h in already if native.IsWindow(h)]
        if still_open:
            return Result(f"{label} was already running and opened no new window.\nwindows: " + _dumps(still_open))
        return Result(f"Started {label}; no window has appeared yet. Call list_windows to look again.")

    def activate_window(self, window_id) -> Result:
        hwnd = self._target(window_id)
        before = self._before(hwnd)
        with self._input():
            self._focus(hwnd)
        return self._ack(hwnd, "Brought the window to the front", before)

    def get_window_state(self, window_id, include_text: bool = True, include_screenshot: bool = False) -> Result:
        return self._state(self._target(window_id), include_screenshot, include_text)

    def click_element(self, window_id, element_name: str | None = None, element_index: int | None = None,
                      click_count: int = 1, mouse_button: str = "left", text: str | None = None,
                      include_text: bool = False) -> Result:
        hwnd = self._target(window_id)
        button = _BUTTONS.get(str(mouse_button).lower())
        if button is None:
            raise CUError("mouse_button must be left, right or middle.")
        if click_count not in (1, 2, 3):
            raise CUError("click_count must be 1, 2 or 3.")
        modifiers = self._modifiers(text)
        if button != "left" or modifiers:
            self._full_control(hwnd, "anything but a plain left click")
        before = self._before(hwnd)
        with self._input():
            self._focus(hwnd)
            element, index = self._element(hwnd, element_index, element_name)
            what = f"element {index} ({self.acc.describe(element)})"
            center = self._element_center(element)
            if center is None:
                if button != "left" or click_count != 1 or not self.acc.perform(element, "invoke"):
                    raise CUError(f"Element {index} has no on-screen area. Scroll it into view and read the tree again.")
                summary = f"{what[0].upper()}{what[1:]} has no on-screen area; invoked it instead"
            else:
                self._operable(hwnd, *center)
                with native.keys_held(modifiers):
                    native.mouse_click(*center, button, click_count)
                times = {1: "", 2: " twice", 3: " three times"}[click_count]
                summary = f"Clicked {what}" + (f" with the {button} button" if button != "left" else "") + times
        return self._ack(hwnd, summary, before, include_text)

    def _choose(self, hwnd: int, box, box_index: int, value: str) -> str:
        if self.acc.perform(box, "expand") is False:
            center = self._element_center(box)
            if center is None:
                raise CUError(f"Element {box_index} is a list that cannot be opened: it has no on-screen area.")
            self._operable(hwnd, *center)
            native.mouse_click(*center)
        time.sleep(0.3)
        self._stale.add(hwnd)
        try:
            item_index = self._named(hwnd, value, {CT_LISTITEM})
        except CUError:
            self._press([(0x1B, None)])
            raise
        center = self._element_center(self._trees[hwnd].elements[item_index])
        if center is None:
            self._press([(0x1B, None)])
            raise CUError(f'"{value}" is in the list but not showing; scroll the list and click it.')
        self._operable(hwnd, *center)
        native.mouse_click(*center)
        return f'Chose "{value}" in'

    def set_value(self, window_id, value: str, element_name: str | None = None, element_index: int | None = None,
                  include_text: bool = False) -> Result:
        hwnd = self._target(window_id)
        self._full_control(hwnd, "setting values")
        element, index = self._element(hwnd, element_index, element_name)
        label = self.acc.describe(element)
        kind = self._trees[hwnd].labels[index][0]
        before = self._before(hwnd)
        with self._input():
            center = self._element_center(element)
            if kind == CT_COMBOBOX and not self.acc.editable(element):
                self._focus(hwnd)
                how = self._choose(hwnd, element, index, value)
            elif center is not None and self.acc.takes_text(element):
                self._focus(hwnd)
                self._operable(hwnd, *center)
                native.mouse_click(*center)
                time.sleep(0.1)
                native.press_chord(parse_chord("ctrl+a"))
                if value:
                    self._enter_text(value.rstrip("\r\n"), lambda: self._has_focus(hwnd))
                else:
                    native.press_chord(parse_chord("Delete"))
                how = "Typed the value of"
            elif self.acc.set_value(element, value):
                how = "Set the value of"
            else:
                raise CUError(f"Element {index} cannot take a value: {label}.")
        return self._ack(hwnd, f"{how} element {index} ({label})", before, include_text)

    def perform_secondary_action(self, window_id, action: str, element_name: str | None = None,
                                 element_index: int | None = None, include_text: bool = False) -> Result:
        hwnd = self._target(window_id)
        self._full_control(hwnd, "accessibility actions")
        element, index = self._element(hwnd, element_index, element_name)
        label = self.acc.describe(element)
        before = self._before(hwnd)
        with self._input():
            if action.strip().lower() == "raise" and index == 0:
                self._focus(hwnd)
                outcome = True
            else:
                outcome = self.acc.perform(element, action)
            if outcome is False:
                raise CUError(f"Element {index} does not support {action!r}: {label}. "
                              "Known actions: Expand, Collapse, Scroll Up/Down/Left/Right, Scroll Into View, "
                              "Invoke, Toggle, Select, Focus, Raise, Show Menu.")
        summary = f"Performed {action} on element {index} ({label})"
        if outcome == "pending":
            summary += (". The app has not come back from it, usually because it opened a dialog and is "
                        "waiting there; until that dialog is closed its accessibility tree cannot be read, "
                        "so handle the dialog from a screenshot with coordinates or keys")
        return self._ack(hwnd, summary, before, include_text)

    def read_clipboard(self) -> Result:
        owner = native.window_root(native.clipboard_owner())
        if owner and self._denial(owner):
            raise CUError("The clipboard was filled by an off-limits app, so it is not read.")
        text = native.clipboard_text()
        if not text:
            return Result("The clipboard holds no text.")
        return Result(text if len(text) <= 20000 else text[:20000] + f"\n… ({len(text) - 20000} more characters)")

    def write_clipboard(self, text: str) -> Result:
        native.set_clipboard_text(text)
        return Result(f"Put {len(text)} characters on the clipboard.")

    TOOLS = (*COMPUTER_ACTIONS, "computer_batch", "list_apps", "list_windows", "open_application",
             "activate_window", "get_window_state", "click_element", "set_value", "perform_secondary_action",
             "read_clipboard", "write_clipboard")

    @staticmethod
    def _explain(error: Exception) -> str:
        if isinstance(error, (CUError, TimeoutError)):
            return str(error)
        if isinstance(error, ElementGone):
            return "That element no longer exists. Read the tree again and pick a current element."
        if isinstance(error, COMError):
            return (f"The application rejected the accessibility request ({error.hresult & 0xFFFFFFFF:#010x}). "
                    "Read the tree again and retry once, or use coordinates instead.")
        if isinstance(error, OSError):
            return f"Windows refused the operation: {error}"
        return f"{type(error).__name__}: {error}"

    def call(self, name: str, arguments: dict, cancel: threading.Event | None = None) -> Result:
        if name not in self.TOOLS:
            raise CUError(f"Unknown tool {name}.")
        if name in COMPUTER_ACTIONS:
            tool, arguments = self.act, {"action": name, **arguments}
        else:
            tool = getattr(self, name)
        try:
            inspect.signature(tool).bind(**arguments)
        except TypeError as e:
            raise CUError(f"Bad arguments for {name}: {e}") from e
        self._cancel = cancel
        try:
            return tool(**arguments)
        except CUError:
            raise
        except Cancelled:
            native.release_buttons()
            raise
        except (ElementGone, COMError, OSError) as e:
            raise CUError(self._explain(e)) from e
        finally:
            self._cancel = None
