from __future__ import annotations

from . import native

VK_SHIFT, VK_CONTROL, VK_ALT = 0x10, 0x11, 0x12

_BLOCKED = {"meta", "meta_l", "meta_r", "windows", "win", "lwin", "rwin", "cmd", "command",
            "super", "super_l", "super_r", "os", "hyper_l", "hyper_r"}

_NAMED: dict[str, int | tuple[int, bool]] = {
    "backspace": 0x08, "tab": 0x09, "return": 0x0D, "enter": 0x0D,
    "shift": VK_SHIFT, "shift_l": VK_SHIFT, "shift_r": 0xA1,
    "control": VK_CONTROL, "ctrl": VK_CONTROL, "control_l": VK_CONTROL, "control_r": 0xA3,
    "alt": VK_ALT, "alt_l": VK_ALT, "alt_r": 0xA5,
    "pause": 0x13, "caps_lock": 0x14, "capslock": 0x14, "escape": 0x1B, "esc": 0x1B, "space": 0x20,
    "page_up": 0x21, "pageup": 0x21, "prior": 0x21, "pgup": 0x21,
    "page_down": 0x22, "pagedown": 0x22, "next": 0x22, "pgdn": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "print": 0x2C, "printscreen": 0x2C, "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "menu": 0x5D, "apps": 0x5D, "num_lock": 0x90, "numlock": 0x90, "scroll_lock": 0x91,
    "kp_multiply": 0x6A, "kp_add": 0x6B, "kp_separator": 0x6C, "kp_subtract": 0x6D,
    "kp_decimal": 0x6E, "kp_divide": 0x6F, "kp_enter": (0x0D, True),
    "semicolon": 0xBA, "equal": 0xBB, "comma": 0xBC, "minus": 0xBD, "period": 0xBE, "slash": 0xBF,
    "grave": 0xC0, "bracketleft": 0xDB, "backslash": 0xDC, "bracketright": 0xDD, "apostrophe": 0xDE,
}
_NAMED.update({f"f{i}": 0x6F + i for i in range(1, 25)})
_NAMED.update({f"kp_{i}": 0x60 + i for i in range(10)})
_NAMED.update({str(i): 0x30 + i for i in range(10)})
_NAMED.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})

_SHIFTED = {
    "colon": 0xBA, "plus": 0xBB, "less": 0xBC, "underscore": 0xBD, "greater": 0xBE, "question": 0xBF,
    "asciitilde": 0xC0, "braceleft": 0xDB, "bar": 0xDC, "braceright": 0xDD, "quotedbl": 0xDE,
    "exclam": 0x31, "at": 0x32, "numbersign": 0x33, "dollar": 0x34, "percent": 0x35,
    "asciicircum": 0x36, "ampersand": 0x37, "asterisk": 0x38, "parenleft": 0x39, "parenright": 0x30,
}


class ChordError(ValueError):
    pass


def parse_chord(chord: str) -> list[tuple[int, bool | None]]:
    tokens = [t.strip() for t in chord.split("+")]
    if not chord.strip() or any(not t for t in tokens):
        raise ChordError(f"invalid key chord {chord!r}; join key names with '+', and write the plus key as 'plus'")
    keys: list[tuple[int, bool | None]] = []
    need_shift = False
    for token in tokens:
        name = token.lower().replace("numpad_", "kp_")
        if name in _BLOCKED:
            raise ChordError("the Windows key and its shortcuts are not allowed")
        if name in _NAMED and (len(token) != 1 or not token.isupper()):
            entry = _NAMED[name]
            keys.append(entry if isinstance(entry, tuple) else (entry, None))
        elif name in _SHIFTED:
            need_shift = True
            keys.append((_SHIFTED[name], None))
        elif len(token) == 1:
            found = native.vk_for_char(token)
            if found is None or found[1] & ~1:
                raise ChordError(f"no key for {token!r} on this keyboard layout; use type_text for text")
            if found[1] & 1 and (len(tokens) == 1 or not token.isalpha()):
                need_shift = True
            keys.append((found[0], None))
        else:
            raise ChordError(f"unknown key name {token!r}")
    if need_shift and not any(vk in (VK_SHIFT, 0xA1) for vk, _ in keys):
        keys.insert(0, (VK_SHIFT, None))
    return keys
