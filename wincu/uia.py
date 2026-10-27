from __future__ import annotations

from dataclasses import dataclass, field

import comtypes
import comtypes.client
from comtypes import COMError

from . import native

with native.NamedMutex("Local\\ClaudeWinCU.ComtypesGen", 30000, "another session is still starting up"):
    comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as U

UIA_E_ELEMENTNOTAVAILABLE = -2147220991
UIA_E_TIMEOUT = -2146233083

CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox", 50004: "Edit",
    50005: "Hyperlink", 50006: "Image", 50007: "ListItem", 50008: "List", 50009: "Menu",
    50010: "MenuBar", 50011: "MenuItem", 50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab", 50019: "TabItem",
    50020: "Text", 50021: "ToolBar", 50022: "ToolTip", 50023: "Tree", 50024: "TreeItem",
    50025: "Custom", 50026: "Group", 50027: "Thumb", 50028: "DataGrid", 50029: "DataItem",
    50030: "Document", 50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator", 50039: "SemanticZoom",
    50040: "AppBar",
}
CT_SCROLLBAR, CT_WINDOW, CT_DOCUMENT, CT_EDIT, CT_COMBOBOX, CT_MENUITEM = 50014, 50032, 50030, 50004, 50003, 50011
CT_LISTITEM, CT_SPINNER = 50007, 50016
_PRUNABLE = {50033, 50026, 50025, 50006, 50038, 50027, 50037}
INTERACTIVE = {50000, 50002, 50003, 50004, 50005, 50007, 50011, 50013, 50015, 50016, 50019, 50024, 50031}

_CACHED_PROPS = [
    U.UIA_NamePropertyId, U.UIA_ControlTypePropertyId, U.UIA_IsEnabledPropertyId,
    U.UIA_HasKeyboardFocusPropertyId, U.UIA_IsPasswordPropertyId,
    U.UIA_IsValuePatternAvailablePropertyId, U.UIA_ValueValuePropertyId,
    U.UIA_IsRangeValuePatternAvailablePropertyId, U.UIA_RangeValueValuePropertyId,
    U.UIA_IsTogglePatternAvailablePropertyId, U.UIA_ToggleToggleStatePropertyId,
    U.UIA_IsExpandCollapsePatternAvailablePropertyId, U.UIA_ExpandCollapseExpandCollapseStatePropertyId,
    U.UIA_IsSelectionItemPatternAvailablePropertyId, U.UIA_SelectionItemIsSelectedPropertyId,
    U.UIA_IsScrollPatternAvailablePropertyId, U.UIA_ScrollVerticallyScrollablePropertyId,
    U.UIA_ScrollHorizontallyScrollablePropertyId, U.UIA_IsInvokePatternAvailablePropertyId,
    U.UIA_IsTextPatternAvailablePropertyId, U.UIA_IsKeyboardFocusablePropertyId,
    U.UIA_BoundingRectanglePropertyId,
]


class ElementGone(Exception):
    pass


class TreeUnavailable(Exception):
    pass


@dataclass
class Snapshot:
    lines: list[str] = field(default_factory=list)
    elements: list = field(default_factory=list)
    labels: list[tuple[int, str]] = field(default_factory=list)
    focused: str | None = None
    selected: list[str] = field(default_factory=list)
    document_text: str | None = None
    selected_text: str | None = None
    truncated: bool = False
    pages_missing: bool = False


def _clip(s: str, limit: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _quote(s: str, limit: int = 160) -> str:
    return '"' + _clip(s, limit).replace('"', '\\"') + '"'


def estimate_tokens(s: str) -> int:
    ascii_chars = sum(1 for c in s if ord(c) < 128)
    return int(ascii_chars / 3.5 + (len(s) - ascii_chars) * 1.2) + 1


class _TreeWriter:
    def __init__(self, focus, max_elements: int, max_tokens: int) -> None:
        self.snap = Snapshot()
        self.focus = focus
        self.text_target = None
        self.document = None
        self._max_elements = max_elements
        self._tokens_left = max_tokens

    def add(self, el, info: dict, body: str, depth: int) -> bool:
        snap = self.snap
        if len(snap.elements) >= self._max_elements or self._tokens_left <= 0:
            snap.truncated = True
            return False
        flat = f"[{len(snap.elements)}] {body}"
        line = "\t" * depth + flat
        self._tokens_left -= estimate_tokens(line)
        snap.elements.append(el)
        snap.lines.append(line)
        snap.labels.append((info["type"], " ".join(info["name"].split())))
        if info["focused"] and snap.focused is None:
            snap.focused = flat
            if info["text"]:
                self.text_target = el
        if info["selected"] and len(snap.selected) < 20:
            snap.selected.append(flat)
        if self.document is None and info["text"] and info["type"] in (CT_DOCUMENT, CT_EDIT):
            self.document = el
        return True


class Accessibility:
    def __init__(self) -> None:
        try:
            self.uia = comtypes.CoCreateInstance(U.CUIAutomation8._reg_clsid_, interface=U.IUIAutomation2,
                                                 clsctx=comtypes.CLSCTX_INPROC_SERVER)
            self.uia.ConnectionTimeout = 5000
            self.uia.TransactionTimeout = 10000
        except (COMError, AttributeError, OSError):
            self.uia = comtypes.CoCreateInstance(U.CUIAutomation._reg_clsid_, interface=U.IUIAutomation,
                                                 clsctx=comtypes.CLSCTX_INPROC_SERVER)
        self._subtree = self._request(U.TreeScope_Subtree)
        self._single = self._request(U.TreeScope_Element)

    def _request(self, scope: int):
        cr = self.uia.CreateCacheRequest()
        for pid in _CACHED_PROPS:
            cr.AddProperty(pid)
        cr.TreeScope = scope
        if scope != U.TreeScope_Element:
            onscreen = self.uia.CreatePropertyCondition(U.UIA_IsOffscreenPropertyId, False)
            cr.TreeFilter = self.uia.CreateAndCondition(self.uia.ControlViewCondition, onscreen)
        return cr

    @staticmethod
    def _read(el) -> dict | None:
        try:
            g = el.GetCachedPropertyValue
            info = {
                "type": el.CachedControlType,
                "name": el.CachedName or "",
                "enabled": bool(el.CachedIsEnabled),
                "focused": bool(el.CachedHasKeyboardFocus),
                "password": bool(g(U.UIA_IsPasswordPropertyId)),
                "focusable": bool(g(U.UIA_IsKeyboardFocusablePropertyId)),
                "invoke": bool(g(U.UIA_IsInvokePatternAvailablePropertyId)),
                "text": bool(g(U.UIA_IsTextPatternAvailablePropertyId)),
                "value": None, "toggle": None, "expand": None, "selected": None,
                "vscroll": False, "hscroll": False,
            }
            if g(U.UIA_IsValuePatternAvailablePropertyId):
                info["value"] = g(U.UIA_ValueValuePropertyId) or ""
            elif g(U.UIA_IsRangeValuePatternAvailablePropertyId):
                info["value"] = format(g(U.UIA_RangeValueValuePropertyId), "g")
            if g(U.UIA_IsTogglePatternAvailablePropertyId):
                info["toggle"] = g(U.UIA_ToggleToggleStatePropertyId)
            if g(U.UIA_IsExpandCollapsePatternAvailablePropertyId):
                info["expand"] = g(U.UIA_ExpandCollapseExpandCollapseStatePropertyId)
            if g(U.UIA_IsSelectionItemPatternAvailablePropertyId):
                info["selected"] = bool(g(U.UIA_SelectionItemIsSelectedPropertyId))
            if g(U.UIA_IsScrollPatternAvailablePropertyId):
                info["vscroll"] = bool(g(U.UIA_ScrollVerticallyScrollablePropertyId))
                info["hscroll"] = bool(g(U.UIA_ScrollHorizontallyScrollablePropertyId))
            return info
        except (COMError, ValueError, TypeError):
            return None

    @staticmethod
    def _secondary_actions(info: dict) -> list[str]:
        out = []
        if info["expand"] in (0, 2):
            out.append("Expand")
        if info["expand"] in (1, 2):
            out.append("Collapse")
        if info["vscroll"]:
            out += ["Scroll Up", "Scroll Down"]
        if info["hscroll"]:
            out += ["Scroll Left", "Scroll Right"]
        if info["type"] == CT_WINDOW:
            out.append("Raise")
        return out

    @classmethod
    def _format(cls, info: dict) -> str:
        parts = [CONTROL_TYPES.get(info["type"], f"Type{info['type']}")]
        if info["name"]:
            parts.append(_quote(info["name"]))
        if info["value"] is not None and not info["password"] and info["value"] != info["name"]:
            if info["value"] or info["type"] in (CT_EDIT, CT_COMBOBOX):
                parts.append("value=" + _quote(info["value"], 240))
        states = []
        if info["password"]:
            states.append("password")
        if not info["enabled"]:
            states.append("disabled")
        if info["focused"]:
            states.append("focused")
        if info["selected"]:
            states.append("selected")
        if info["toggle"] is not None:
            states.append({0: "unchecked", 1: "checked"}.get(info["toggle"], "mixed"))
        if info["expand"] in (0, 1, 2):
            states.append({0: "collapsed", 1: "expanded", 2: "partially expanded"}[info["expand"]])
        if states:
            parts.append("(" + ", ".join(states) + ")")
        actions = cls._secondary_actions(info)
        if actions:
            parts.append("actions: " + ", ".join(actions))
        return " ".join(parts)

    @staticmethod
    def _printable(info: dict) -> bool:
        if info["type"] not in _PRUNABLE:
            return True
        return bool(info["name"] or info["value"] or info["focused"] or info["invoke"]
                    or info["toggle"] is not None or info["expand"] is not None
                    or info["selected"] is not None or info["vscroll"] or info["hscroll"])

    @staticmethod
    def _children(el) -> list:
        try:
            arr = el.GetCachedChildren()
        except (COMError, ValueError):
            return []
        if not arr:
            return []
        try:
            return [arr.GetElement(i) for i in range(arr.Length)]
        except (COMError, ValueError):
            return []

    def snapshot(self, hwnd: int, popups: list[tuple[int, tuple]], max_elements: int, max_tokens: int,
                 max_text_chars: int) -> Snapshot:
        try:
            focus = self.uia.GetFocusedElement()
        except (COMError, OSError):
            focus = None
        out = _TreeWriter(focus, max_elements, max_tokens)
        main = self._root(hwnd)
        if main is None:
            raise TreeUnavailable()
        self._walk(main, out)
        stray = None
        for popup, rect in popups:
            if out.snap.truncated:
                break
            root = self._root(popup)
            if root is not None:
                self._walk(root, out)
            if stray is None:
                stray = self._offscreen_menu_items(main)
            for el, info, (x, y) in stray:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    out.add(el, info, self._format(info), 1)
        snap = out.snap
        if snap.focused is None:
            snap.focused = self._focused_outside_tree([hwnd] + [p for p, _ in popups])
        self._read_text(out.text_target or out.document, snap, max_text_chars)
        return snap

    def _root(self, hwnd: int):
        try:
            return self.uia.ElementFromHandleBuildCache(hwnd, self._subtree) or None
        except (COMError, OSError):
            return None

    def wake(self, hwnds: list[int]) -> None:
        for hwnd in hwnds:
            try:
                self.uia.ElementFromHandle(hwnd)
            except (COMError, OSError):
                pass

    def _walk(self, root, out: "_TreeWriter") -> None:
        stack = [(root, 0)]
        while stack:
            el, depth = stack.pop()
            info = self._read(el)
            if info is None or info["type"] == CT_SCROLLBAR:
                continue
            if info["focused"]:
                info["focused"] = self._same(out.focus, el)
            if self._printable(info):
                if not out.add(el, info, self._format(info), depth):
                    return
                depth += 1
            for kid in reversed(self._children(el)):
                stack.append((kid, depth))

    def _offscreen_menu_items(self, main) -> list[tuple]:
        try:
            condition = self.uia.CreateAndCondition(
                self.uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, CT_MENUITEM),
                self.uia.CreatePropertyCondition(U.UIA_IsOffscreenPropertyId, True))
            found = main.FindAllBuildCache(U.TreeScope_Descendants, condition, self._single)
            items = []
            for i in range(found.Length if found else 0):
                el = found.GetElement(i)
                r = el.CachedBoundingRectangle
                info = self._read(el)
                if info is not None and r.right > r.left and r.bottom > r.top:
                    info["focused"] = False
                    items.append((el, info, ((r.left + r.right) // 2, (r.top + r.bottom) // 2)))
            return items
        except (COMError, ValueError, OSError):
            return []

    def _same(self, a, b) -> bool:
        if not a or not b:
            return False
        try:
            return bool(self.uia.CompareElements(a, b))
        except (COMError, OSError):
            return False

    def _focused_outside_tree(self, hwnds: list[int]) -> str | None:
        try:
            el = self.uia.GetFocusedElementBuildCache(self._single)
            if not el:
                return None
            walker = self.uia.ControlViewWalker
            cur = el
            for _ in range(64):
                handle = cur.CurrentNativeWindowHandle
                if handle and int(handle) in hwnds:
                    info = self._read(el)
                    return "(not indexed) " + self._format(info) if info else None
                cur = walker.GetParentElement(cur)
                if not cur:
                    break
        except (COMError, ValueError, OSError):
            pass
        return None

    def _read_text(self, el, snap: Snapshot, max_chars: int) -> None:
        if el is None:
            return
        tp = self._pattern(el, U.UIA_TextPatternId, U.IUIAutomationTextPattern)
        if tp is None:
            return
        try:
            text = tp.DocumentRange.GetText(max_chars + 1)
            if text:
                snap.document_text = text if len(text) <= max_chars else text[:max_chars] + "…"
            ranges = tp.GetSelection()
            if ranges and ranges.Length:
                chunks = [ranges.GetElement(i).GetText(2000) for i in range(min(ranges.Length, 5))]
                selected = "\n".join(c for c in chunks if c)
                if selected:
                    snap.selected_text = selected
        except (COMError, ValueError):
            pass

    @staticmethod
    def _pattern(el, pattern_id: int, interface):
        try:
            p = el.GetCurrentPattern(pattern_id)
        except COMError as e:
            if e.hresult == UIA_E_ELEMENTNOTAVAILABLE:
                raise ElementGone() from e
            return None
        if not p:
            return None
        try:
            return p.QueryInterface(interface)
        except COMError:
            return None

    @staticmethod
    def rect(el) -> tuple[int, int, int, int] | None:
        try:
            r = el.CurrentBoundingRectangle
        except COMError as e:
            raise ElementGone() from e
        if r.right - r.left <= 0 or r.bottom - r.top <= 0:
            return None
        return r.left, r.top, r.right, r.bottom

    def describe(self, el) -> str:
        try:
            fresh = el.BuildUpdatedCache(self._single)
        except COMError as e:
            raise ElementGone() from e
        info = self._read(fresh)
        return self._format(info) if info else "element"

    def editable(self, combo) -> bool:
        try:
            field = combo.FindFirst(U.TreeScope_Children,
                                    self.uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, CT_EDIT))
            return bool(field)
        except COMError as e:
            raise ElementGone() from e

    def takes_text(self, el) -> bool:
        try:
            kind = el.CurrentControlType
        except COMError as e:
            raise ElementGone() from e
        return kind in (CT_EDIT, CT_DOCUMENT, CT_SPINNER) or (kind == CT_COMBOBOX and self.editable(el))

    def set_value(self, el, value: str) -> bool:
        vp = self._pattern(el, U.UIA_ValuePatternId, U.IUIAutomationValuePattern)
        if vp is not None:
            try:
                if not vp.CurrentIsReadOnly:
                    self._run_action(lambda: vp.SetValue(value))
                    return True
            except COMError:
                pass
        rp = self._pattern(el, U.UIA_RangeValuePatternId, U.IUIAutomationRangeValuePattern)
        if rp is not None:
            try:
                rp.SetValue(float(value))
                return True
            except (COMError, ValueError):
                pass
        return False

    def _run_action(self, call) -> bool | str:
        try:
            usual = self.uia.TransactionTimeout
            self.uia.TransactionTimeout = 3000
        except (AttributeError, COMError):
            usual = None
        try:
            call()
            return True
        except COMError as e:
            if e.hresult != UIA_E_TIMEOUT:
                raise
            return "pending"
        finally:
            if usual is not None:
                self.uia.TransactionTimeout = usual

    def perform(self, el, action: str) -> bool | str:
        key = " ".join(action.lower().replace("_", " ").split())
        none, back, fwd = U.ScrollAmount_NoAmount, U.ScrollAmount_LargeDecrement, U.ScrollAmount_LargeIncrement
        expand = (U.UIA_ExpandCollapsePatternId, U.IUIAutomationExpandCollapsePattern)
        scroll = (U.UIA_ScrollPatternId, U.IUIAutomationScrollPattern)
        invoke = (U.UIA_InvokePatternId, U.IUIAutomationInvokePattern, lambda p: p.Invoke())
        by_pattern = {
            "expand": (*expand, lambda p: p.Expand()),
            "collapse": (*expand, lambda p: p.Collapse()),
            "scroll up": (*scroll, lambda p: p.Scroll(none, back)),
            "scroll down": (*scroll, lambda p: p.Scroll(none, fwd)),
            "scroll left": (*scroll, lambda p: p.Scroll(back, none)),
            "scroll right": (*scroll, lambda p: p.Scroll(fwd, none)),
            "invoke": invoke, "press": invoke, "click": invoke,
            "toggle": (U.UIA_TogglePatternId, U.IUIAutomationTogglePattern, lambda p: p.Toggle()),
            "select": (U.UIA_SelectionItemPatternId, U.IUIAutomationSelectionItemPattern, lambda p: p.Select()),
            "scroll into view": (U.UIA_ScrollItemPatternId, U.IUIAutomationScrollItemPattern,
                                 lambda p: p.ScrollIntoView()),
        }
        try:
            if key in by_pattern:
                pattern_id, interface, run = by_pattern[key]
                pattern = self._pattern(el, pattern_id, interface)
                if pattern is None:
                    return False
                return self._run_action(lambda: run(pattern))
            if key in ("focus", "raise"):
                return self._run_action(el.SetFocus)
            if key in ("show menu", "show context menu"):
                return self._run_action(el.QueryInterface(U.IUIAutomationElement3).ShowContextMenu)
        except COMError as e:
            if e.hresult == UIA_E_ELEMENTNOTAVAILABLE:
                raise ElementGone() from e
            raise
        return False

    def scroll_into_view(self, el) -> None:
        try:
            self.perform(el, "scroll into view")
        except COMError:
            pass
