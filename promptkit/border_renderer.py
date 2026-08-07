from __future__ import annotations
import sys
import shutil
from .box_chars import BoxChars
from .terminal import get_capabilities, resolve_box_style, _ResizeMixin
from .text_utils import visible_width, truncate_ansi, hex_to_rgb

class _OutputBuffer:
    __slots__ = ("_parts",)

    def __init__(self) -> None:
        self._parts: list[str] = []

    def write(self, text: str) -> None:
        self._parts.append(text)

    def flush(self) -> None:
        if self._parts:
            sys.stdout.write("".join(self._parts))
            sys.stdout.flush()
            self._parts.clear()

    def clear(self) -> None:
        self._parts.clear()

def get_visible_length(text: str) -> int:
    return visible_width(text)

def truncate_ansi_content(text: str, target_width: int) -> str:
    return truncate_ansi(text, target_width, suffix="", reset=False)

class BorderRenderer(_ResizeMixin):
    def __init__(
        self,
        box_style: str = "rounded",
        border_color: str = "",
        selected_bg: str = "",
        position_offset: int = 0,
    ) -> None:
        self._caps = get_capabilities()
        effective_style = resolve_box_style(box_style, self._caps)

        self.box_chars: BoxChars = BoxChars.for_style(effective_style)
        self._border_color: str = border_color
        self._selected_bg: str = selected_bg
        self._position_offset: int = position_offset

        self._prev_total_lines: int = 0
        self._prev_header_lines: int = 0
        self._prev_term_cols: int = 0
        self._box_state: dict | None = None
        self._resize_during_render: bool = False
        self._init_resize_state(0, 0)

    def _styled_border(self, char: str) -> str:
        if self._border_color:
            ansi = self._hex_to_ansi(self._border_color)
            return f"{ansi}{char}\033[0m"
        return char

    @staticmethod
    def _hex_to_ansi(hex_color: str) -> str:
        rgb = hex_to_rgb(hex_color)
        if rgb is None:
            return hex_color.lstrip('#')
        r, g, b = rgb
        return f"\033[38;2;{r};{g};{b}m"

    def _estimate_start_row(self, term_rows: int, dialog_lines: int) -> int:
        return max(1, term_rows - dialog_lines + 1)

    def get_terminal_size(self) -> tuple[int, int]:
        try:
            size = shutil.get_terminal_size()
            return (size.columns, size.lines)
        except Exception:
            return (80, 24)

    def _calc_max_items(self, term_rows: int, header_lines: int, content_count: int) -> int:
        MIN_BOX_LINES = 4
        if header_lines > 0:
            min_required = header_lines + 3
        else:
            min_required = 3

        if term_rows < min_required:
            return 0

        available_rows = term_rows - header_lines
        max_items = max(available_rows - 2, 0)
        return min(max_items, content_count)

    def _calc_physical_lines(self, header_lines: list[str], box_height: int, term_cols: int) -> int:
        physical = 0

        for line in header_lines:
            visible_len = get_visible_length(line)
            if visible_len > 0:
                physical += max(1, (visible_len + term_cols - 1) // term_cols)
            else:
                physical += 1

        physical += box_height

        return physical

    def draw_box(
        self,
        content_lines: list[str],
        selected_idx: int = 0,
        scroll_offset: int = 0,
        max_visible: int = 10,
        header_lines: list[str] | None = None,
        box_width: int | None = None,
    ) -> None:
        if not self._caps.supports_cursor_movement:
            if header_lines:
                for line in header_lines:
                    print(line)
            for i, line in enumerate(content_lines):
                prefix = "► " if i == selected_idx else "  "
                print(f"{prefix}{line}")
            return

        term_cols, term_rows = self.get_terminal_size()
        headers = header_lines or []
        header_count = len(headers)

        max_items = self._calc_max_items(term_rows, header_count, len(content_lines))
        if max_items <= 0:
            self._hide_box(headers, term_rows)
            return

        max_items = min(max_items, max_visible)

        visible = content_lines[scroll_offset:scroll_offset + max_items]
        if not visible:
            self._hide_box(headers, term_rows)
            return

        if box_width is None:
            max_content_width = max(get_visible_length(line) for line in visible)
            box_width = max_content_width + 4
            box_width = max(box_width, 20)

        box_width = min(box_width, term_cols - 2 - self._position_offset)
        inner_width = box_width - 2

        rel_selected = selected_idx - scroll_offset
        rel_selected = max(0, min(rel_selected, len(visible) - 1))

        box_height = len(visible) + 2
        total_lines = header_count + box_height

        buf = _OutputBuffer()

        is_post_resize = self._resize_during_render

        if is_post_resize:
            buf.write("\r\033[2K")
            self._resize_during_render = False
        elif self._prev_total_lines > 0:
            lines_to_clear = max(self._prev_total_lines, total_lines)

            buf.write("\r")
            buf.write("\033[2K")
            buf.write("\033[J")

            buf.write("\r")
            for i in range(lines_to_clear):
                buf.write("\033[2K")
                buf.write("\033[J")
                if i < lines_to_clear - 1:
                    buf.write("\033[1B")

            buf.write("\r")
            buf.write(f"\033[{lines_to_clear - 1}A")
        else:
            buf.write("\r\033[2K")

        for line in headers:
            buf.write("\r")
            if self._position_offset > 0:
                buf.write(" " * self._position_offset)
            buf.write(f"{line}\n")

        if self._position_offset > 0:
            buf.write(" " * self._position_offset)
        buf.write(
            self._styled_border(self.box_chars.top_left) +
            self._styled_border(self.box_chars.horizontal) * inner_width +
            self._styled_border(self.box_chars.top_right) +
            "\n"
        )

        for idx, line in enumerate(visible):
            if self._position_offset > 0:
                buf.write(" " * self._position_offset)

            if idx == rel_selected and self._selected_bg:
                styled_line = f"{self._selected_bg}{line}\033[0m"
            else:
                styled_line = line

            visible_len = get_visible_length(styled_line)
            if visible_len < inner_width:
                styled_line += ' ' * (inner_width - visible_len)
            elif visible_len > inner_width:
                styled_line = truncate_ansi_content(styled_line, inner_width)

            buf.write(
                self._styled_border(self.box_chars.vertical) +
                styled_line +
                self._styled_border(self.box_chars.vertical) +
                "\n"
            )

        if self._position_offset > 0:
            buf.write(" " * self._position_offset)
        buf.write(
            self._styled_border(self.box_chars.bottom_left) +
            self._styled_border(self.box_chars.horizontal) * inner_width +
            self._styled_border(self.box_chars.bottom_right)
        )

        move_up = len(visible) + 1 + header_count
        buf.write(f"\033[{move_up}A")

        self._box_state = {
            "visible_lines": visible,
            "box_width": box_width,
            "box_height": box_height,
            "inner_width": inner_width,
            "selected_idx": rel_selected,
            "scroll_offset": scroll_offset,
            "header_count": header_count,
        }
        self._prev_total_lines = total_lines
        self._prev_header_lines = header_count
        self._prev_term_cols = term_cols

        buf.flush()

    def draw_selection_update(
        self,
        old_selected_idx: int,
        new_selected_idx: int,
    ) -> None:
        if self._box_state is None:
            return

        bs = self._box_state
        visible = bs["visible_lines"]
        inner_width = bs["inner_width"]
        header_count = bs["header_count"]

        if old_selected_idx >= len(visible) or new_selected_idx >= len(visible):
            return

        buf = _OutputBuffer()

        old_line_offset = header_count + 1 + 1 + old_selected_idx
        buf.write(f"\r\033[{old_line_offset}B")

        old_line = visible[old_selected_idx]
        visible_len = get_visible_length(old_line)
        if visible_len < inner_width:
            old_line += ' ' * (inner_width - visible_len)
        elif visible_len > inner_width:
            old_line = truncate_ansi_content(old_line, inner_width)

        buf.write("\r\033[2K")
        buf.write(
            self._styled_border(self.box_chars.vertical) +
            old_line +
            self._styled_border(self.box_chars.vertical)
        )

        delta = new_selected_idx - old_selected_idx
        if delta > 0:
            buf.write(f"\r\033[{delta}B")
        elif delta < 0:
            buf.write(f"\r\033[{abs(delta)}A")

        new_line = visible[new_selected_idx]
        if new_selected_idx == new_selected_idx and self._selected_bg:
            new_line_styled = f"{self._selected_bg}{new_line}\033[0m"
        else:
            new_line_styled = new_line

        visible_len = get_visible_length(new_line_styled)
        if visible_len < inner_width:
            new_line_styled += ' ' * (inner_width - visible_len)
        elif visible_len > inner_width:
            new_line_styled = truncate_ansi_content(new_line_styled, inner_width)

        buf.write("\r\033[2K")
        buf.write(
            self._styled_border(self.box_chars.vertical) +
            new_line_styled +
            self._styled_border(self.box_chars.vertical)
        )

        go_up = header_count + 1 + 1 + new_selected_idx
        buf.write(f"\r\033[{go_up}A")

        bs["selected_idx"] = new_selected_idx

        buf.flush()

    def _hide_box(self, headers: list[str], term_rows: int) -> None:
        buf = _OutputBuffer()

        if self._prev_total_lines > 0:
            buf.write("\r")
            for i in range(self._prev_total_lines):
                buf.write("\033[2K")
                if i < self._prev_total_lines - 1:
                    buf.write("\033[1B")
            buf.write(f"\r\033[{self._prev_total_lines - 1}A")
        else:
            buf.write("\r\033[2K")

        if headers and term_rows >= 1:
            if self._position_offset > 0:
                buf.write(" " * self._position_offset)
            buf.write(headers[0])

        self._box_state = None
        self._prev_total_lines = min(len(headers), 1) if headers and term_rows >= 1 else 0
        self._prev_header_lines = self._prev_total_lines

        buf.flush()

    def handle_resize(self) -> None:
        if self._prev_total_lines == 0 and self._box_state is None:
            return

        prev_cols, prev_rows, term_cols, term_rows = self.get_resize_diff()
        cols_changed = term_cols != prev_cols

        prev_lines = self._prev_total_lines if self._prev_total_lines > 0 else 12

        buf = _OutputBuffer()

        if cols_changed:
            if prev_lines > 0:
                buf.write("\r")
                for i in range(prev_lines):
                    buf.write("\033[2K")
                    if i < prev_lines - 1:
                        buf.write("\033[1B")
                buf.write(f"\r\033[{prev_lines - 1}A")
            buf.write("\033[J")
        else:
            buf.write("\r\033[J")

        buf.flush()

        self._prev_total_lines = 0
        self._prev_header_lines = 0
        self._prev_term_cols = 0
        self._box_state = None
        self._resize_during_render = True

    def position_cursor_below_rendered(self) -> None:
        prev_box_height = self._box_state["box_height"] if self._box_state else 0
        total_lines = self._prev_total_lines

        if total_lines <= 0:
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            return

        lines_to_move = total_lines - 1
        if lines_to_move > 0:
            sys.stdout.write(f"\033[{lines_to_move}B")

        sys.stdout.write("\r\n")
        sys.stdout.flush()

    def clear_rendered(self) -> None:
        if self._prev_total_lines <= 0:
            return

        buf = _OutputBuffer()
        buf.write("\r")
        for i in range(self._prev_total_lines):
            buf.write("\033[2K")
            if i < self._prev_total_lines - 1:
                buf.write("\n")
        if self._prev_total_lines > 1:
            buf.write(f"\r\033[{self._prev_total_lines - 1}A")
        buf.flush()

        self._prev_total_lines = 0
        self._prev_header_lines = 0
        self._box_state = None

    def get_viewport_size(self) -> int:
        if self._box_state is None:
            return 0
        return len(self._box_state["visible_lines"])
