from __future__ import annotations

import os
import re
import sys
import shutil


def _detect_win_vt() -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
            return True
        return False
    except Exception:
        return False


def resolve_box_style(box_style: str, caps: "TerminalCapabilities") -> str:
    if not caps.supports_cursor_movement or not caps.supports_ansi:
        return "ascii"
    return box_style


class _ResizeMixin:

    def _init_resize_state(self, term_cols: int, term_rows: int) -> None:
        self._term_cols_before_signal: int = term_cols
        self._term_rows_before_signal: int = term_rows
        self._resize_stable_wait: float = 0.0
        self._resize_during_render: bool = False

    def on_sigwinch(self) -> None:
        cols, rows = self.get_terminal_size()  # type: ignore[attr-defined]
        self._term_cols_before_signal = cols
        self._term_rows_before_signal = rows
        self._resize_during_render = True
        self._resize_stable_wait = 0.15

    def check_resize_event(self) -> bool:
        if self._resize_stable_wait <= 0:
            return True
        self._resize_stable_wait -= 0.025
        if self._resize_stable_wait <= 0:
            return True
        return False

    def get_resize_diff(self) -> tuple[int, int, int, int]:
        cols, rows = self.get_terminal_size()  # type: ignore[attr-defined]
        return (
            self._term_cols_before_signal,
            self._term_rows_before_signal,
            cols,
            rows,
        )


class TerminalCapabilities:

    def __init__(self) -> None:
        self.is_tty: bool = sys.stdout.isatty()
        self.is_tty_in: bool = sys.stdin.isatty()

        self.term_name: str = os.environ.get("TERM", "").lower()

        try:
            size = shutil.get_terminal_size()
            self.term_cols: int = size.columns
            self.term_rows: int = size.lines
        except Exception:
            self.term_cols = 80
            self.term_rows = 24

        self.color_level: int = self._detect_color_level()
        self.supports_ansi: bool = self._detect_ansi_support()
        self.supports_cursor_movement: bool = self._detect_cursor_movement_support()
        self.supports_dim: bool = self._detect_dim_support()

    def _detect_color_level(self) -> int:
        if not self.is_tty:
            return 0

        if self.term_name in ("dumb", ""):
            if os.environ.get("NO_COLOR") is not None:
                return 0
            if self.term_name == "dumb":
                return 0

        if os.environ.get("NO_COLOR") is not None:
            return 0

        colorterm = os.environ.get("COLORTERM", "").lower()
        if colorterm in ("truecolor", "24bit"):
            return 3

        if "truecolor" in self.term_name:
            return 3
        if "256color" in self.term_name:
            return 2

        term_program = os.environ.get("TERM_PROGRAM", "").lower()
        if term_program in ("iterm.app", "wezterm", "ghostty", "kitty"):
            return 3

        if os.environ.get("WT_SESSION") is not None:
            return 3

        win_vt = _detect_win_vt()
        if win_vt is not None:
            return 3 if win_vt else 1

        if self.term_name and self.term_name != "dumb":
            return 2

        return 1

    def _detect_ansi_support(self) -> bool:
        if not self.is_tty:
            return False

        if self.term_name == "dumb":
            return False

        win_vt = _detect_win_vt()
        if win_vt is not None:
            return bool(win_vt)

        return True

    def _detect_cursor_movement_support(self) -> bool:
        if not self.supports_ansi:
            return False

        if self.term_name == "dumb":
            return False

        return True

    def _detect_dim_support(self) -> bool:
        if not self.supports_ansi:
            return False
        if self.term_name == "dumb":
            return False
        win_vt = _detect_win_vt()
        if win_vt is not None:
            return bool(win_vt)
        return True

    @staticmethod
    def strip_ansi(text: str) -> str:
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?(?:\x07|\x1b\\)")
        return ansi_pattern.sub("", text)

    @staticmethod
    def strip_rich_tags(text: str) -> str:
        tag_pattern = re.compile(r"\[(?:/[^\]]*|[^\]]*)\]")
        return tag_pattern.sub("", text)

    def can_display_box(self) -> bool:
        if not self.supports_cursor_movement:
            return False
        return True

    def get_recommended_box_style(self) -> str:
        if not self.supports_cursor_movement:
            return "ascii"
        if self.term_name == "dumb":
            return "ascii"
        return "rounded"

    def __repr__(self) -> str:
        return (
            f"TerminalCapabilities("
            f"is_tty={self.is_tty}, "
            f"color_level={self.color_level}, "
            f"supports_ansi={self.supports_ansi}, "
            f"supports_cursor_movement={self.supports_cursor_movement}, "
            f"term={self.term_name!r})"
        )


_capabilities: TerminalCapabilities | None = None


def set_cursor_style(style: str) -> str:
    codes: dict[str, str] = {
        "block": "\033[2 q",
        "underline": "\033[4 q",
        "beam": "\033[6 q",
        "line": "\033[6 q",
    }
    return codes.get(style, "")


def reset_cursor_style() -> str:
    return "\033[0 q"


def get_capabilities() -> TerminalCapabilities:
    global _capabilities
    if _capabilities is None:
        _capabilities = TerminalCapabilities()
    return _capabilities


def reset_capabilities() -> None:
    global _capabilities
    _capabilities = None
