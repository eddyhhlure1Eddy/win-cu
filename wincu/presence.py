from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time

from . import native

user32 = native.user32
gdi32 = native.gdi32
kernel32 = native.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HANDLE)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_byte * 32)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT), ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD), ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wt.USHORT), ("Flags", wt.USHORT), ("Reserved", wt.USHORT), ("VKey", wt.USHORT),
                ("Message", wt.UINT), ("ExtraInformation", wt.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


RegisterClassExW = _fn(user32, "RegisterClassExW", wt.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _fn(user32, "CreateWindowExW", wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HANDLE, wt.HINSTANCE, ctypes.c_void_p)
DefWindowProcW = _fn(user32, "DefWindowProcW", LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
GetMessageW = _fn(user32, "GetMessageW", wt.BOOL, ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
DispatchMessageW = _fn(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(wt.MSG))
PostMessageW = _fn(user32, "PostMessageW", wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
SetTimer = _fn(user32, "SetTimer", ctypes.c_size_t, wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p)
SetLayeredWindowAttributes = _fn(user32, "SetLayeredWindowAttributes", wt.BOOL, wt.HWND, wt.COLORREF, wt.BYTE, wt.DWORD)
SetWindowDisplayAffinity = _fn(user32, "SetWindowDisplayAffinity", wt.BOOL, wt.HWND, wt.DWORD)
SetWindowPos = _fn(user32, "SetWindowPos", wt.BOOL, wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                   ctypes.c_int, wt.UINT)
SetWindowRgn = _fn(user32, "SetWindowRgn", ctypes.c_int, wt.HWND, wt.HANDLE, wt.BOOL)
InvalidateRect = _fn(user32, "InvalidateRect", wt.BOOL, wt.HWND, ctypes.c_void_p, wt.BOOL)
BeginPaint = _fn(user32, "BeginPaint", wt.HDC, wt.HWND, ctypes.POINTER(PAINTSTRUCT))
EndPaint = _fn(user32, "EndPaint", wt.BOOL, wt.HWND, ctypes.POINTER(PAINTSTRUCT))
GetClientRect = _fn(user32, "GetClientRect", wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
FillRect = _fn(user32, "FillRect", ctypes.c_int, wt.HDC, ctypes.POINTER(wt.RECT), wt.HANDLE)
DrawTextW = _fn(user32, "DrawTextW", ctypes.c_int, wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT)
RegisterRawInputDevices = _fn(user32, "RegisterRawInputDevices", wt.BOOL, ctypes.POINTER(RAWINPUTDEVICE), wt.UINT, wt.UINT)
GetRawInputData = _fn(user32, "GetRawInputData", wt.UINT, wt.HANDLE, wt.UINT, ctypes.c_void_p,
                      ctypes.POINTER(wt.UINT), wt.UINT)
GetLastInputInfo = _fn(user32, "GetLastInputInfo", wt.BOOL, ctypes.POINTER(LASTINPUTINFO))
GetTickCount = _fn(kernel32, "GetTickCount", wt.DWORD)
GetModuleHandleW = _fn(kernel32, "GetModuleHandleW", wt.HMODULE, wt.LPCWSTR)
CreateSolidBrush = _fn(gdi32, "CreateSolidBrush", wt.HANDLE, wt.COLORREF)
CreateRoundRectRgn = _fn(gdi32, "CreateRoundRectRgn", wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int)
CreateFontW = _fn(gdi32, "CreateFontW", wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                  ctypes.c_int, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
                  wt.LPCWSTR)
SetBkMode = _fn(gdi32, "SetBkMode", ctypes.c_int, wt.HDC, ctypes.c_int)
SetTextColor = _fn(gdi32, "SetTextColor", wt.COLORREF, wt.HDC, wt.COLORREF)

WM_PAINT, WM_TIMER, WM_INPUT, WM_APP = 0x000F, 0x0113, 0x00FF, 0x8000
WM_REFRESH = WM_APP + 1
WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TOPMOST = 0x00080000, 0x00000008
WDA_EXCLUDEFROMCAPTURE = 0x11
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RI_KEY_BREAK = 0x01
VK_ESCAPE = 0x1B
OVERLAY_CLASS = "ClaudeWinCUBanner"

BANNER_SIZE = (430, 34)
ACTIVE_TEXT = "Claude is using this PC · Press Esc to stop"
STOPPED_TEXT = "Stopped by Esc · Claude no longer sends input"


class Presence:
    def __init__(self, show_banner: bool = True, linger_s: float = 3.0, stop_hold_s: float = 12.0,
                 yield_quiet_s: float = 0.8, yield_wait_s: float = 4.0) -> None:
        self.show_banner = show_banner
        self.linger_s = linger_s
        self.stop_hold_s = stop_hold_s
        self.yield_quiet_s = yield_quiet_s
        self.yield_wait_s = yield_wait_s
        self._hwnd = 0
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_until = 0.0
        self._stopped_until = 0.0
        self._own_tick = 0
        self._own_escape_until = 0.0
        self.on_stop = None
        self._wndproc = WNDPROC(self._on_message)

    def begin_action(self) -> str | None:
        self._start()
        now = time.monotonic()
        if now < self._stopped_until:
            return ("The user pressed Esc to stop computer use, so nothing was sent. "
                    "Do not send more input until the user asks you to continue.")
        deadline = now + self.yield_wait_s
        while self._user_active():
            if time.monotonic() >= deadline:
                return ("The user is using the mouse or keyboard right now, so nothing was sent. "
                        "Wait until they finish, or ask them how to proceed.")
            native.pause(0.1)
        self._active_until = time.monotonic() + 150
        self._refresh()
        return None

    def end_action(self, sent_input: bool = True) -> None:
        if sent_input:
            self._own_tick = GetTickCount()
        if not self.stopped():
            self._active_until = time.monotonic() + self.linger_s

    def own_escape(self) -> None:
        self._own_escape_until = time.monotonic() + 0.6

    def stopped(self) -> bool:
        return time.monotonic() < self._stopped_until

    def _user_active(self) -> bool:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not GetLastInputInfo(ctypes.byref(info)):
            return False
        now = GetTickCount()
        age = (now - info.dwTime) & 0xFFFFFFFF
        after_ours = (info.dwTime - self._own_tick) & 0xFFFFFFFF
        ours = self._own_tick and (after_ours <= 48 or after_ours > 0x7FFFFFFF)
        return age < self.yield_quiet_s * 1000 and not ours

    def _start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="wincu-presence", daemon=True)
            self._thread.start()
            self._ready.wait(3)

    def _refresh(self) -> None:
        if self._hwnd:
            PostMessageW(self._hwnd, WM_REFRESH, 0, 0)

    def _run(self) -> None:
        instance = GetModuleHandleW(None)
        cls = WNDCLASSEXW()
        cls.cbSize = ctypes.sizeof(cls)
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = instance
        cls.lpszClassName = OVERLAY_CLASS
        RegisterClassExW(ctypes.byref(cls))
        vx, vy, vw, _ = native.virtual_screen()
        w, h = BANNER_SIZE
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | native.WS_EX_TRANSPARENT | native.WS_EX_TOOLWINDOW | native.WS_EX_NOACTIVATE
        hwnd = CreateWindowExW(ex, OVERLAY_CLASS, "Claude is using this computer", WS_POPUP,
                               vx + (vw - w) // 2, vy + 10, w, h, None, None, instance, None)
        if hwnd:
            SetLayeredWindowAttributes(hwnd, 0, 235, 0x2)
            SetWindowRgn(hwnd, CreateRoundRectRgn(0, 0, w + 1, h + 1, 16, 16), False)
            SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            keyboard = RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, hwnd)
            RegisterRawInputDevices(ctypes.byref(keyboard), 1, ctypes.sizeof(keyboard))
            SetTimer(hwnd, 1, 250, None)
            self._font = CreateFontW(-15, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Microsoft YaHei UI")
            self._brush_active = CreateSolidBrush(0x00302A26)
            self._brush_stopped = CreateSolidBrush(0x002B2BB0)
            self._hwnd = hwnd
        self._ready.set()
        msg = wt.MSG()
        while hwnd and GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            DispatchMessageW(ctypes.byref(msg))

    def _on_message(self, hwnd, message, wparam, lparam):
        if message == WM_INPUT:
            self._on_raw_input(lparam)
        elif message in (WM_TIMER, WM_REFRESH):
            self._update_banner(hwnd)
            return 0
        elif message == WM_PAINT:
            self._paint(hwnd)
            return 0
        return DefWindowProcW(hwnd, message, wparam, lparam)

    def _on_raw_input(self, lparam) -> None:
        raw = RAWINPUT()
        size = wt.UINT(ctypes.sizeof(raw))
        got = GetRawInputData(lparam, RID_INPUT, ctypes.byref(raw), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if got == 0xFFFFFFFF or raw.header.dwType != 1:
            return
        now = time.monotonic()
        pressed = not raw.keyboard.Flags & RI_KEY_BREAK
        if pressed and raw.keyboard.VKey == VK_ESCAPE and self._own_escape_until < now < self._active_until:
            self._stopped_until = now + self.stop_hold_s
            self._active_until = 0.0
            if self.on_stop:
                self.on_stop()

    def _update_banner(self, hwnd) -> None:
        now = time.monotonic()
        visible = self.show_banner and (now < self._active_until or now < self._stopped_until)
        state = (visible, now < self._stopped_until)
        if state != getattr(self, "_shown", None):
            self._shown = state
            if visible:
                SetWindowPos(hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
                InvalidateRect(hwnd, None, True)
            else:
                native.ShowWindow(hwnd, 0)

    def _paint(self, hwnd) -> None:
        ps = PAINTSTRUCT()
        hdc = BeginPaint(hwnd, ctypes.byref(ps))
        rect = wt.RECT()
        GetClientRect(hwnd, ctypes.byref(rect))
        stopped = time.monotonic() < self._stopped_until
        FillRect(hdc, ctypes.byref(rect), self._brush_stopped if stopped else self._brush_active)
        old = native.SelectObject(hdc, self._font)
        SetBkMode(hdc, 1)
        SetTextColor(hdc, 0x00FFFFFF)
        DrawTextW(hdc, STOPPED_TEXT if stopped else ACTIVE_TEXT, -1, ctypes.byref(rect), 0x1 | 0x4 | 0x20)
        native.SelectObject(hdc, old)
        EndPaint(hwnd, ctypes.byref(ps))
