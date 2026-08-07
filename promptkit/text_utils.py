from __future__ import annotations

import re

try:
    from wcwidth import wcswidth, wcwidth as _wcwidth  # type: ignore[assignment]
except Exception:
    def _wcwidth(ch: str) -> int:
        return 1

    def wcswidth(s: str) -> int:
        return len(s)


__all__ = [
    "ANSI_ESCAPE_RE",
    "strip_ansi",
    "visible_width",
    "truncate_ansi",
    "hex_to_rgb",
]

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def visible_width(text: str) -> int:
    clean = ANSI_ESCAPE_RE.sub("", text)
    width = wcswidth(clean)
    if width >= 0:
        return width

    total = 0
    for ch in clean:
        w = _wcwidth(ch)
        total += w if w >= 0 else 1
    return total


def truncate_ansi(text: str, max_width: int, suffix: str = "...", reset: bool = True) -> str:
    if max_width <= 0:
        return ""

    if visible_width(text) <= max_width:
        return text

    suffix_w = wcswidth(suffix) if wcswidth(suffix) >= 0 else len(suffix)
    target = max(0, max_width - suffix_w)

    out: list[str] = []
    width = 0
    i = 0
    n = len(text)
    while i < n and width < target:
        if text[i] == "\x1b" and i + 1 < n and text[i + 1] == "[":
            end = text.find("m", i)
            if end != -1:
                out.append(text[i:end + 1])
                i = end + 1
                continue
        ch = text[i]
        w = _wcwidth(ch)
        if w < 0:
            w = 1
        if width + w > target:
            break
        out.append(ch)
        width += w
        i += 1

    if reset:
        out.append("\x1b[0m")
    out.append(suffix)
    return "".join(out)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except ValueError:
        return None
