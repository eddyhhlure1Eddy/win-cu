from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import random
import threading
import time

from PIL import Image, ImageChops

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)


def _set_dpi_awareness() -> None:
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


_set_dpi_awareness()

HWND = wt.HWND
HDC = wt.HDC
HANDLE = wt.HANDLE
BOOL = wt.BOOL
UINT = wt.UINT
DWORD = wt.DWORD
LONG = wt.LONG
ULONG_PTR = ctypes.c_size_t
c_int = ctypes.c_int

WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, wt.LPARAM)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", DWORD), ("u", _INPUTUNION)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", DWORD), ("cntUsage", DWORD), ("th32ProcessID", DWORD),
                ("th32DefaultHeapID", ULONG_PTR), ("th32ModuleID", DWORD), ("cntThreads", DWORD),
                ("th32ParentProcessID", DWORD), ("pcPriClassBase", LONG), ("dwFlags", DWORD),
                ("szExeFile", wt.WCHAR * 260)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("flags", DWORD), ("hCursor", HANDLE), ("ptScreenPos", wt.POINT)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", BOOL), ("xHotspot", DWORD), ("yHotspot", DWORD), ("hbmMask", wt.HBITMAP),
                ("hbmColor", wt.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", DWORD), ("biWidth", LONG), ("biHeight", LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", DWORD), ("biSizeImage", DWORD),
                ("biXPelsPerMeter", LONG), ("biYPelsPerMeter", LONG), ("biClrUsed", DWORD),
                ("biClrImportant", DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


EnumWindows = _fn(user32, "EnumWindows", BOOL, WNDENUMPROC, wt.LPARAM)
EnumChildWindows = _fn(user32, "EnumChildWindows", BOOL, HWND, WNDENUMPROC, wt.LPARAM)
IsWindow = _fn(user32, "IsWindow", BOOL, HWND)
IsWindowVisible = _fn(user32, "IsWindowVisible", BOOL, HWND)
IsWindowEnabled = _fn(user32, "IsWindowEnabled", BOOL, HWND)
IsIconic = _fn(user32, "IsIconic", BOOL, HWND)
IsHungAppWindow = _fn(user32, "IsHungAppWindow", BOOL, HWND)
GetWindowTextLengthW = _fn(user32, "GetWindowTextLengthW", c_int, HWND)
GetWindowTextW = _fn(user32, "GetWindowTextW", c_int, HWND, wt.LPWSTR, c_int)
GetClassNameW = _fn(user32, "GetClassNameW", c_int, HWND, wt.LPWSTR, c_int)
GetWindowThreadProcessId = _fn(user32, "GetWindowThreadProcessId", DWORD, HWND, ctypes.POINTER(DWORD))
GetWindowLongPtrW = _fn(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, HWND, c_int)
GetWindow = _fn(user32, "GetWindow", HWND, HWND, UINT)
GetAncestor = _fn(user32, "GetAncestor", HWND, HWND, UINT)
GetWindowRect = _fn(user32, "GetWindowRect", BOOL, HWND, ctypes.POINTER(wt.RECT))
GetForegroundWindow = _fn(user32, "GetForegroundWindow", HWND)
SetForegroundWindow = _fn(user32, "SetForegroundWindow", BOOL, HWND)
BringWindowToTop = _fn(user32, "BringWindowToTop", BOOL, HWND)
ShowWindow = _fn(user32, "ShowWindow", BOOL, HWND, c_int)
AttachThreadInput = _fn(user32, "AttachThreadInput", BOOL, DWORD, DWORD, BOOL)
WindowFromPoint = _fn(user32, "WindowFromPoint", HWND, wt.POINT)
MonitorFromPoint = _fn(user32, "MonitorFromPoint", HANDLE, wt.POINT, DWORD)
GetCursorPos = _fn(user32, "GetCursorPos", BOOL, ctypes.POINTER(wt.POINT))
SetCursorPos = _fn(user32, "SetCursorPos", BOOL, c_int, c_int)
GetSystemMetrics = _fn(user32, "GetSystemMetrics", c_int, c_int)
GetDoubleClickTime = _fn(user32, "GetDoubleClickTime", UINT)
SendInput = _fn(user32, "SendInput", UINT, UINT, ctypes.POINTER(INPUT), c_int)
MapVirtualKeyW = _fn(user32, "MapVirtualKeyW", UINT, UINT, UINT)
VkKeyScanW = _fn(user32, "VkKeyScanW", ctypes.c_short, wt.WCHAR)
PrintWindow = _fn(user32, "PrintWindow", BOOL, HWND, HDC, UINT)
GetDC = _fn(user32, "GetDC", HDC, HWND)
ReleaseDC = _fn(user32, "ReleaseDC", c_int, HWND, HDC)
OpenInputDesktop = _fn(user32, "OpenInputDesktop", HANDLE, DWORD, BOOL, DWORD)
CloseDesktop = _fn(user32, "CloseDesktop", BOOL, HANDLE)
GetUserObjectInformationW = _fn(user32, "GetUserObjectInformationW", BOOL, HANDLE, c_int, ctypes.c_void_p,
                                DWORD, ctypes.POINTER(DWORD))

CreateCompatibleDC = _fn(gdi32, "CreateCompatibleDC", HDC, HDC)
CreateDIBSection = _fn(gdi32, "CreateDIBSection", wt.HBITMAP, HDC, ctypes.POINTER(BITMAPINFO), UINT,
                       ctypes.POINTER(ctypes.c_void_p), HANDLE, DWORD)
SelectObject = _fn(gdi32, "SelectObject", wt.HGDIOBJ, HDC, wt.HGDIOBJ)
DeleteObject = _fn(gdi32, "DeleteObject", BOOL, wt.HGDIOBJ)
DeleteDC = _fn(gdi32, "DeleteDC", BOOL, HDC)
BitBlt = _fn(gdi32, "BitBlt", BOOL, HDC, c_int, c_int, c_int, c_int, HDC, c_int, c_int, DWORD)
GdiFlush = _fn(gdi32, "GdiFlush", BOOL)

DwmGetWindowAttribute = _fn(dwmapi, "DwmGetWindowAttribute", ctypes.c_long, HWND, DWORD, ctypes.c_void_p, DWORD)

GetCurrentThreadId = _fn(kernel32, "GetCurrentThreadId", DWORD)
OpenProcess = _fn(kernel32, "OpenProcess", HANDLE, DWORD, BOOL, DWORD)
CloseHandle = _fn(kernel32, "CloseHandle", BOOL, HANDLE)
QueryFullProcessImageNameW = _fn(kernel32, "QueryFullProcessImageNameW", BOOL, HANDLE, DWORD, wt.LPWSTR,
                                 ctypes.POINTER(DWORD))
GetApplicationUserModelId = _fn(kernel32, "GetApplicationUserModelId", LONG, HANDLE,
                                ctypes.POINTER(ctypes.c_uint32), wt.LPWSTR)
CreateMutexW = _fn(kernel32, "CreateMutexW", HANDLE, ctypes.c_void_p, BOOL, wt.LPCWSTR)
WaitForSingleObject = _fn(kernel32, "WaitForSingleObject", DWORD, HANDLE, DWORD)
ReleaseMutex = _fn(kernel32, "ReleaseMutex", BOOL, HANDLE)

ShellExecuteW = _fn(shell32, "ShellExecuteW", ctypes.c_void_p, HWND, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR,
                    wt.LPCWSTR, c_int)
EnumProcesses = _fn(kernel32, "K32EnumProcesses", BOOL, ctypes.POINTER(DWORD), DWORD, ctypes.POINTER(DWORD))
GetAsyncKeyState = _fn(user32, "GetAsyncKeyState", ctypes.c_short, c_int)
OpenProcessToken = _fn(advapi32, "OpenProcessToken", BOOL, HANDLE, DWORD, ctypes.POINTER(HANDLE))
GetTokenInformation = _fn(advapi32, "GetTokenInformation", BOOL, HANDLE, c_int, ctypes.c_void_p, DWORD,
                          ctypes.POINTER(DWORD))
GetSidSubAuthorityCount = _fn(advapi32, "GetSidSubAuthorityCount", ctypes.POINTER(ctypes.c_ubyte), ctypes.c_void_p)
GetSidSubAuthority = _fn(advapi32, "GetSidSubAuthority", ctypes.POINTER(DWORD), ctypes.c_void_p, DWORD)
GetCurrentProcessId = _fn(kernel32, "GetCurrentProcessId", DWORD)
GetCursorInfo = _fn(user32, "GetCursorInfo", BOOL, ctypes.POINTER(CURSORINFO))
GetIconInfo = _fn(user32, "GetIconInfo", BOOL, HANDLE, ctypes.POINTER(ICONINFO))
DrawIconEx = _fn(user32, "DrawIconEx", BOOL, HDC, c_int, c_int, HANDLE, c_int, c_int, UINT, HANDLE, UINT)
PatBlt = _fn(gdi32, "PatBlt", BOOL, HDC, c_int, c_int, c_int, c_int, DWORD)
GetClipboardOwner = _fn(user32, "GetClipboardOwner", HWND)
OpenClipboard = _fn(user32, "OpenClipboard", BOOL, HWND)
CloseClipboard = _fn(user32, "CloseClipboard", BOOL)
EmptyClipboard = _fn(user32, "EmptyClipboard", BOOL)
GetClipboardData = _fn(user32, "GetClipboardData", HANDLE, UINT)
SetClipboardData = _fn(user32, "SetClipboardData", HANDLE, UINT, HANDLE)
GlobalAlloc = _fn(kernel32, "GlobalAlloc", HANDLE, UINT, ctypes.c_size_t)
GlobalLock = _fn(kernel32, "GlobalLock", ctypes.c_void_p, HANDLE)
GlobalUnlock = _fn(kernel32, "GlobalUnlock", BOOL, HANDLE)
GlobalFree = _fn(kernel32, "GlobalFree", HANDLE, HANDLE)
CreateToolhelp32Snapshot = _fn(kernel32, "CreateToolhelp32Snapshot", HANDLE, DWORD, DWORD)
Process32FirstW = _fn(kernel32, "Process32FirstW", BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))
Process32NextW = _fn(kernel32, "Process32NextW", BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))

GWL_STYLE, GWL_EXSTYLE = -16, -20
GW_OWNER = 4
GA_ROOT = 2
WS_CAPTION = 0x00C00000
WS_DISABLED = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
SW_RESTORE = 9
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
_BUTTON_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120


_stop = threading.local()


def set_checkpoint(check) -> None:
    _stop.check = check


def checkpoint() -> None:
    check = getattr(_stop, "check", None)
    if check is not None:
        check()


def pause(seconds: float) -> None:
    end = time.monotonic() + seconds
    while True:
        checkpoint()
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(left, 0.05))


def enum_windows() -> list[int]:
    out: list[int] = []

    @WNDENUMPROC
    def cb(hwnd, _):
        out.append(hwnd or 0)
        return True

    EnumWindows(cb, 0)
    return out


def enum_child_windows(hwnd: int) -> list[int]:
    out: list[int] = []

    @WNDENUMPROC
    def cb(h, _):
        out.append(h or 0)
        return True

    EnumChildWindows(hwnd, cb, 0)
    return out


def web_views(hwnd: int) -> list[int]:
    return [h for h in enum_child_windows(hwnd)
            if window_class(h) == "Chrome_RenderWidgetHostHWND" and IsWindowVisible(h)]


def window_text(hwnd: int) -> str:
    n = GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_style(hwnd: int) -> int:
    return GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF


def window_exstyle(hwnd: int) -> int:
    return GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF


def window_owner(hwnd: int) -> int:
    return GetWindow(hwnd, GW_OWNER) or 0


def window_root(hwnd: int) -> int:
    return GetAncestor(hwnd, GA_ROOT) or 0


def window_pid_tid(hwnd: int) -> tuple[int, int]:
    pid = DWORD(0)
    tid = GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value, tid


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wt.RECT()
    GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def frame_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wt.RECT()
    hr = DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r))
    if hr == 0 and r.right > r.left and r.bottom > r.top:
        return r.left, r.top, r.right, r.bottom
    return window_rect(hwnd)


def is_cloaked(hwnd: int) -> bool:
    v = DWORD(0)
    hr = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
    return hr == 0 and v.value != 0


def foreground_window() -> int:
    return GetForegroundWindow() or 0


def window_from_point(x: int, y: int) -> int:
    return WindowFromPoint(wt.POINT(x, y)) or 0


def virtual_screen() -> tuple[int, int, int, int]:
    return GetSystemMetrics(76), GetSystemMetrics(77), GetSystemMetrics(78), GetSystemMetrics(79)


def input_desktop_name() -> str | None:
    h = OpenInputDesktop(0, False, 0x0001)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(256)
        needed = DWORD(0)
        if GetUserObjectInformationW(h, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
            return buf.value
        return None
    finally:
        CloseDesktop(h)


def process_image_path(pid: int) -> str:
    h = OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        size = DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        CloseHandle(h)


def running_image_paths() -> set[str]:
    pids = (DWORD * 4096)()
    used = DWORD(0)
    if not EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(used)):
        return set()
    count = used.value // ctypes.sizeof(DWORD)
    return {p for p in (process_image_path(pids[i]) for i in range(count) if pids[i]) if p}


def parent_pids() -> dict[int, int]:
    snapshot = CreateToolhelp32Snapshot(0x2, 0)
    if not snapshot or snapshot == HANDLE(-1).value:
        return {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        out = {}
        more = Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            out[entry.th32ProcessID] = entry.th32ParentProcessID
            more = Process32NextW(snapshot, ctypes.byref(entry))
        return out
    finally:
        CloseHandle(snapshot)


def process_integrity(pid: int) -> int | None:
    process = OpenProcess(0x1000, False, pid)
    if not process:
        return None
    token = HANDLE()
    try:
        if not OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            return None
        try:
            size = DWORD(0)
            GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            if not GetTokenInformation(token, 25, buf, size, ctypes.byref(size)):
                return None
            sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            return GetSidSubAuthority(sid, GetSidSubAuthorityCount(sid)[0] - 1)[0]
        finally:
            CloseHandle(token)
    finally:
        CloseHandle(process)


def process_aumid(pid: int) -> str:
    h = OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        n = ctypes.c_uint32(0)
        rc = GetApplicationUserModelId(h, ctypes.byref(n), None)
        if rc != 122 or n.value == 0:
            return ""
        buf = ctypes.create_unicode_buffer(n.value)
        if GetApplicationUserModelId(h, ctypes.byref(n), buf) == 0:
            return buf.value
        return ""
    finally:
        CloseHandle(h)


def _make_dib(w: int, h: int):
    hdc_screen = GetDC(None)
    hdc_mem = CreateCompatibleDC(hdc_screen)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    bits = ctypes.c_void_p()
    hbmp = CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbmp or not bits:
        DeleteDC(hdc_mem)
        ReleaseDC(None, hdc_screen)
        raise OSError("CreateDIBSection failed")
    old = SelectObject(hdc_mem, hbmp)
    return hdc_screen, hdc_mem, hbmp, old, bits


def _free_dib(hdc_screen, hdc_mem, hbmp, old) -> None:
    SelectObject(hdc_mem, old)
    DeleteObject(hbmp)
    DeleteDC(hdc_mem)
    ReleaseDC(None, hdc_screen)


def _to_image(bits, w: int, h: int) -> Image.Image:
    data = ctypes.string_at(bits, w * h * 4)
    return Image.frombuffer("RGB", (w, h), data, "raw", "BGRX", 0, 1)


def print_window(hwnd: int) -> Image.Image | None:
    l, t, r, b = window_rect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hdc_screen, hdc_mem, hbmp, old, bits = _make_dib(w, h)
    try:
        ok = PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        GdiFlush()
        if not ok:
            return None
        return _to_image(bits, w, h)
    finally:
        _free_dib(hdc_screen, hdc_mem, hbmp, old)


def grab_screen(l: int, t: int, r: int, b: int) -> Image.Image:
    w, h = r - l, b - t
    hdc_screen, hdc_mem, hbmp, old, bits = _make_dib(w, h)
    try:
        BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, l, t, SRCCOPY | CAPTUREBLT)
        GdiFlush()
        return _to_image(bits, w, h)
    finally:
        _free_dib(hdc_screen, hdc_mem, hbmp, old)


def is_blank(img: Image.Image) -> bool:
    return all(hi == 0 for _, hi in img.getextrema())


def draw_cursor(canvas: Image.Image, origin_x: int, origin_y: int) -> None:
    info = CURSORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not GetCursorInfo(ctypes.byref(info)) or not info.flags & 1 or not info.hCursor:
        return
    icon = ICONINFO()
    if not GetIconInfo(info.hCursor, ctypes.byref(icon)):
        return
    for bitmap in (icon.hbmMask, icon.hbmColor):
        if bitmap:
            DeleteObject(bitmap)
    x = info.ptScreenPos.x - icon.xHotspot - origin_x
    y = info.ptScreenPos.y - icon.yHotspot - origin_y
    size = 96
    if x >= canvas.width or y >= canvas.height or x + size <= 0 or y + size <= 0:
        return
    renders = []
    for fill in (0x00000042, 0x00FF0062):
        hdc_screen, hdc_mem, hbmp, old, bits = _make_dib(size, size)
        try:
            PatBlt(hdc_mem, 0, 0, size, size, fill)
            DrawIconEx(hdc_mem, 0, 0, info.hCursor, 0, 0, 0, None, 0x0003)
            GdiFlush()
            renders.append(_to_image(bits, size, size).convert("L"))
            if fill == 0x00000042:
                colour = _to_image(bits, size, size)
        finally:
            _free_dib(hdc_screen, hdc_mem, hbmp, old)
    on_black, on_white = renders
    clear = ImageChops.subtract(on_white, on_black)
    inverting = ImageChops.subtract(on_black, on_white).point(lambda v: 255 if v > 32 else 0)
    opaque = ImageChops.subtract(ImageChops.invert(clear), inverting)
    if inverting.getbbox():
        under = canvas.crop((x, y, x + size, y + size))
        canvas.paste(ImageChops.invert(under), (x, y), inverting)
    canvas.paste(colour, (x, y), opaque)


def clipboard_owner() -> int:
    return GetClipboardOwner() or 0


def clipboard_text() -> str:
    for _ in range(10):
        if OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        raise OSError("the clipboard is in use by another program")
    try:
        handle = GetClipboardData(13)
        if not handle:
            return ""
        pointer = GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            GlobalUnlock(handle)
    finally:
        CloseClipboard()


def set_clipboard_text(text: str) -> None:
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    for _ in range(10):
        if OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        raise OSError("the clipboard is in use by another program")
    try:
        EmptyClipboard()
        handle = GlobalAlloc(0x0002, size)
        pointer = GlobalLock(handle) if handle else None
        if not pointer:
            raise OSError("could not allocate clipboard memory")
        ctypes.memmove(pointer, data, size)
        GlobalUnlock(handle)
        if not SetClipboardData(13, handle):
            GlobalFree(handle)
            raise OSError("the clipboard rejected the text")
    finally:
        CloseClipboard()


def _send(inputs: list[INPUT]) -> None:
    n = len(inputs)
    if not n:
        return
    arr = (INPUT * n)(*inputs)
    sent = SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise OSError(f"SendInput delivered {sent}/{n} events (input is blocked, error {ctypes.get_last_error()})")


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    i = INPUT()
    i.type = INPUT_MOUSE
    i.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return i


def _key(vk: int, scan: int, flags: int) -> INPUT:
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def cursor_pos() -> tuple[int, int]:
    p = wt.POINT()
    GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _move_to(x: int, y: int) -> INPUT:
    vx, vy, vw, vh = virtual_screen()
    return _mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                  int(((x - vx) + 0.5) * 65536 / vw), int(((y - vy) + 0.5) * 65536 / vh))


def mouse_move(x: int, y: int) -> None:
    _send([_move_to(x, y)])
    if cursor_pos() != (x, y):
        SetCursorPos(x, y)


def _button_flags(button: str) -> tuple[int, int]:
    if GetSystemMetrics(23) and button in ("left", "right"):
        button = "right" if button == "left" else "left"
    return _BUTTON_FLAGS[button]


GLIDE_MAX_S = 0.5
GLIDE_BOW = (0.08, 0.15)
GLIDE_BOW_MAX_PX = 120


def on_screen(x: int, y: int) -> bool:
    return bool(MonitorFromPoint(wt.POINT(x, y), 0))


def glide_path(start: tuple[int, int], end: tuple[int, int], steps: int, bow: float) -> list[tuple[int, int]]:
    (sx, sy), (x, y) = start, end
    length = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 or 1
    nx, ny = (sy - y) / length, (x - sx) / length
    points = []
    for i in range(1, steps):
        eased = 1 - (1 - i / steps) ** 3
        side = 4 * bow * eased * (1 - eased)
        points.append((round(sx + (x - sx) * eased + nx * side), round(sy + (y - sy) * eased + ny * side)))
    return points + [(x, y)]


def mouse_glide(x: int, y: int) -> None:
    sx, sy = cursor_pos()
    distance = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
    duration = min(distance / 2000, GLIDE_MAX_S)
    if duration < 0.03:
        mouse_move(x, y)
        return
    steps = int(duration * 60)
    path = glide_path((sx, sy), (x, y), steps, 0)
    if not _buttons_down:
        bow = min(distance * random.uniform(*GLIDE_BOW), GLIDE_BOW_MAX_PX) * random.choice((1, -1))
        for side in (bow, -bow):
            arc = glide_path((sx, sy), (x, y), steps, side)
            if all(on_screen(*p) for p in arc):
                path = arc
                break
    for px, py in path[:-1]:
        mouse_move(px, py)
        pause(1 / 60)
    mouse_move(x, y)


def mouse_button(button: str, down: bool, at: tuple[int, int] | None = None) -> None:
    flags = _button_flags(button)
    event = _mouse(flags[0] if down else flags[1])
    _send([_move_to(*at), event] if at else [event])
    (_buttons_down.add if down else _buttons_down.discard)(button)


_buttons_down: set[str] = set()


def release_buttons() -> None:
    for button in list(_buttons_down):
        try:
            mouse_button(button, False)
        except OSError:
            _buttons_down.discard(button)


_last_click = (0.0, 0, 0, "")


def mouse_click(x: int, y: int, button: str = "left", count: int = 1) -> None:
    global _last_click
    when, lx, ly, last_button = _last_click
    wait = GetDoubleClickTime() / 1000 + 0.05 - (time.monotonic() - when)
    if (wait > 0 and last_button == button
            and abs(x - lx) <= GetSystemMetrics(36) and abs(y - ly) <= GetSystemMetrics(37)):
        pause(wait)
    mouse_glide(x, y)
    pause(0.04)
    for i in range(count):
        mouse_button(button, True, (x, y))
        time.sleep(0.03)
        mouse_button(button, False, (x, y))
        if i < count - 1:
            time.sleep(0.07)
    _last_click = (time.monotonic(), x, y, button)


def mouse_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration: float = 0.5) -> None:
    mouse_glide(x1, y1)
    pause(0.08)
    mouse_button(button, True, (x1, y1))
    released = False
    try:
        pause(0.12)
        dist = max(abs(x2 - x1), abs(y2 - y1))
        steps = max(8, min(60, dist // 8))
        for i in range(1, steps + 1):
            mouse_move(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
            pause(duration / steps)
        pause(0.12)
        mouse_button(button, False, (x2, y2))
        released = True
    finally:
        if not released:
            try:
                mouse_button(button, False)
            except OSError:
                pass


def mouse_scroll(x: int, y: int, dx: int, dy: int) -> None:
    mouse_glide(x, y)
    pause(0.05)
    for flag, amount in ((MOUSEEVENTF_WHEEL, -dy), (MOUSEEVENTF_HWHEEL, dx)):
        sign = 1 if amount >= 0 else -1
        remaining = abs(amount)
        while remaining > 0:
            step = min(WHEEL_DELTA, remaining)
            _send([_move_to(x, y), _mouse(flag, data=sign * step)])
            remaining -= step
            pause(0.015)


_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5D, 0x6F, 0x90, 0xA3, 0xA5}


def key_events(vk: int, up: bool, extended: bool | None = None) -> INPUT:
    if extended is None:
        extended = vk in _EXTENDED_VKS
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    return _key(vk, MapVirtualKeyW(vk, 0), flags)


@contextlib.contextmanager
def keys_held(keys: list[tuple[int, bool | None]]):
    pressed: list[tuple[int, bool | None]] = []
    try:
        for vk, ext in keys:
            _send([key_events(vk, False, ext)])
            pressed.append((vk, ext))
            time.sleep(0.02)
        yield
    finally:
        for vk, ext in reversed(pressed):
            try:
                _send([key_events(vk, True, ext)])
            except OSError:
                pass
            time.sleep(0.02)


def press_chord(keys: list[tuple[int, bool | None]], hold_s: float = 0.0) -> None:
    with keys_held(keys):
        if hold_s > 0.03:
            pause(hold_s)
        else:
            time.sleep(0.03)


def type_unicode(text: str, still_focused=None) -> None:
    events: list[INPUT] = []
    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        if ch == "\n":
            events += [key_events(0x0D, False), key_events(0x0D, True)]
        elif ch == "\t":
            events += [key_events(0x09, False), key_events(0x09, True)]
        else:
            raw = ch.encode("utf-16-le", "surrogatepass")
            for i in range(0, len(raw), 2):
                unit = raw[i] | (raw[i + 1] << 8)
                events += [_key(0, unit, KEYEVENTF_UNICODE), _key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    for i in range(0, len(events), 12):
        checkpoint()
        if still_focused is not None and not still_focused():
            raise OSError("another window took the keyboard focus while typing; the text was only partly entered")
        _send(events[i:i + 12])
        time.sleep(0.018)


def paste_text(text: str) -> bool:
    try:
        previous = clipboard_text()
    except OSError:
        previous = ""
    lost = not previous and user32.CountClipboardFormats() > 0
    wanted = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    set_clipboard_text(wanted)
    if clipboard_text() != wanted:
        raise OSError("the clipboard did not take the text, so nothing was pasted")
    time.sleep(0.05)
    press_chord([(0x11, None), (0x56, None)])
    time.sleep(0.3)
    if previous:
        try:
            set_clipboard_text(previous)
        except OSError:
            pass
    return lost


def held_modifiers() -> list[str]:
    names = (("Ctrl", 0x11), ("Shift", 0x10), ("Alt", 0x12), ("Win", 0x5B), ("Win", 0x5C))
    return list(dict.fromkeys(name for name, vk in names if GetAsyncKeyState(vk) & 0x8000))


def vk_for_char(ch: str) -> tuple[int, int] | None:
    r = VkKeyScanW(ch)
    if r == -1:
        return None
    return r & 0xFF, (r >> 8) & 0xFF


def _wait_foreground(accept, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while True:
        if accept(foreground_window()):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.02)


def activate(hwnd: int, accept=None) -> bool:
    if accept is None:
        accept = lambda fg: fg == hwnd
    if IsIconic(hwnd):
        ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.15)
    if accept(foreground_window()):
        return True

    try:
        _send([_mouse(MOUSEEVENTF_MOVE, 0, 0)])
    except OSError:
        pass
    SetForegroundWindow(hwnd)
    if _wait_foreground(accept, 0.3):
        return True

    fg = foreground_window()
    me = GetCurrentThreadId()
    _, fg_tid = window_pid_tid(fg) if fg else (0, 0)
    if fg_tid and fg_tid != me:
        attached = AttachThreadInput(me, fg_tid, True)
        try:
            BringWindowToTop(hwnd)
            SetForegroundWindow(hwnd)
        finally:
            if attached:
                AttachThreadInput(me, fg_tid, False)
        if _wait_foreground(accept, 0.3):
            return True

    try:
        _send([key_events(0x12, False)])
        SetForegroundWindow(hwnd)
        _send([key_events(0xE8, False), key_events(0xE8, True)])
    finally:
        try:
            _send([key_events(0x12, True)])
        except OSError:
            pass
    return _wait_foreground(accept, 0.4)


class NamedMutex:
    def __init__(self, name: str, wait_ms: int, busy: str) -> None:
        self._h = CreateMutexW(None, False, name)
        self._wait_ms = wait_ms
        self._busy = busy

    def __enter__(self):
        if self._h:
            deadline = time.monotonic() + self._wait_ms / 1000
            while (rc := WaitForSingleObject(self._h, 50)) == 0x102 and time.monotonic() < deadline:
                checkpoint()
            if rc not in (0, 0x80):
                raise TimeoutError(self._busy)
        return self

    def __exit__(self, *exc):
        if self._h:
            ReleaseMutex(self._h)
        return False
