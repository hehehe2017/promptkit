from __future__ import annotations

import sys
import shutil
import re
from wcwidth import wcswidth, wcwidth as _wcwidth
from .completion import CompletionItem
from .box_chars import BoxChars
from .highlighter import CompletionHighlighter
from .terminal import get_capabilities, set_cursor_style, reset_cursor_style, resolve_box_style
from .border_renderer import _OutputBuffer, get_visible_length
from .text_utils import truncate_ansi, hex_to_rgb
from .formatted_prompt import FormattedPrompt, PromptSpec, resolve_prompt
from .styling import StyleParser


class Renderer:

    def __init__(
        self,
        prompt: PromptSpec = ">>> ",
        box_style: str = "rounded",
        completion_highlighter: CompletionHighlighter | None = None,
        prompt_visible_length: int | None = None,
        completion_style: dict[str, str] | None = None,
        suggestion_style: str | None = None,
        cursor_style: str | None = None,
    ) -> None:
        self._prompt_spec: PromptSpec = prompt
        fp = resolve_prompt(prompt)

        self.prompt: str = fp.styled_prompt_prefix
        self.prompt_visible_length: int = (
            prompt_visible_length if prompt_visible_length is not None
            else fp.prompt_prefix_visible_length
        )

        self._has_info_line: bool = bool(fp.info_line)
        self._styled_info_line: str = fp.styled_info_line
        self._info_line_visible_length: int = fp.info_line_visible_length

        self._has_rprompt: bool = bool(fp.rprompt)
        self._styled_rprompt: str = fp.styled_rprompt
        self._rprompt_visible_length: int = fp.rprompt_visible_length

        self._caps = get_capabilities()
        effective_box_style = resolve_box_style(box_style, self._caps)

        self.box_chars: BoxChars = BoxChars.for_style(effective_box_style)
        self.completion_highlighter: CompletionHighlighter | None = completion_highlighter

        self._completion_style: dict[str, str] = completion_style or {}
        self._selected_bg: str = self._resolve_color(
            self._completion_style.get("selected_bg", ""), "bg"
        ) or "\033[48;5;238m"
        self._border_color: str = self._resolve_color(
            self._completion_style.get("border_color", ""), "fg"
        )

        self._suggestion_style: str = self._resolve_suggestion_style(suggestion_style)

        self._box_state: dict | None = None

        self._prev_cursor_line: int = 0
        self._prev_input_lines: int = 1

        self._resize_during_render: bool = False

        self._cursor_style_escape: str = (
            set_cursor_style(cursor_style) if cursor_style else ""
        )

        term_cols, term_rows = self.get_terminal_size()
        self._prev_term_cols: int = term_cols
        self._prev_term_rows: int = term_rows
        self._term_cols_before_resize: int = term_cols
        self._term_rows_before_resize: int = term_rows
        self._resize_cooldown: float = -1.0

        self._resize_signal_pending: bool = False
        self._resize_stable_wait: float = 0.0
        self._term_cols_before_signal: int = term_cols
        self._term_rows_before_signal: int = term_rows

    def check_resize(self) -> bool:
        cols, rows = self.get_terminal_size()
        if cols != self._prev_term_cols or rows != self._prev_term_rows:
            self._term_cols_before_resize = self._prev_term_cols
            self._term_rows_before_resize = self._prev_term_rows
            self._prev_term_cols = cols
            self._prev_term_rows = rows
            if self._resize_cooldown < 0:
                self._resize_cooldown = 0.2
            return False
        if self._resize_cooldown > 0:
            self._resize_cooldown -= 0.02
            return False
        return False

    def should_redraw_on_resize(self) -> bool:
        return self._resize_cooldown > 0 and self._resize_cooldown <= 0.02

    def mark_resize_redrawn(self) -> None:
        self._resize_cooldown = -1
        self._resize_signal_pending = False

    def on_sigwinch(self) -> None:
        cols, rows = self.get_terminal_size()
        self._term_cols_before_signal = cols
        self._term_rows_before_signal = rows
        self._resize_signal_pending = True
        self._resize_stable_wait = 0.15

    def check_resize_event(self) -> bool:
        if not self._resize_signal_pending:
            return False
        if self._resize_stable_wait > 0:
            self._resize_stable_wait -= 0.025
            return False
        return True

    def get_resize_diff(self) -> tuple[int, int, int, int]:
        cols, rows = self.get_terminal_size()
        return (
            self._term_cols_before_signal,
            self._term_rows_before_signal,
            cols,
            rows
        )

    def clear_screen_area(self) -> None:
        sys.stdout.write("\r\033[J")
        sys.stdout.flush()

    def _resolve_color(self, color_spec: str, mode: str = "fg") -> str:
        if not color_spec:
            return ""

        if color_spec.replace(";", "").replace(" ", "").isdigit():
            return f"\033[{color_spec.strip()}m"

        if color_spec.startswith("#") and len(color_spec) == 7:
            from .styling import StyleParser
            if mode == "bg":
                return f"\033[{StyleParser._hex_to_bg_ansi(color_spec.lstrip('#'))}m"
            else:
                return f"\033[{StyleParser._hex_to_fg_ansi(color_spec.lstrip('#'))}m"

        from .styling import StyleParser
        if mode == "bg":
            tag = f"on_{color_spec}"
        else:
            tag = color_spec

        codes = StyleParser._parse_styles(tag)
        if codes:
            return f"\033[{';'.join(codes)}m"

        return ""

    def _resolve_suggestion_style(self, style_spec: str | None) -> str:
        if style_spec is None:
            return ""

        if style_spec == "dim":
            return "\033[2m"

        if style_spec.replace(";", "").replace(" ", "").isdigit():
            return f"\033[{style_spec.strip()}m"

        if style_spec.startswith("#") and len(style_spec) == 7:
            from .styling import StyleParser
            return f"\033[{StyleParser._hex_to_fg_ansi(style_spec.lstrip('#'))}m"

        from .styling import StyleParser
        codes = StyleParser._parse_styles(style_spec)
        if codes:
            return f"\033[{';'.join(codes)}m"

        return "\033[2m"

    def _styled_border(self, char: str) -> str:
        if self._border_color:
            return f"{self._border_color}{char}\033[0m"
        return char

    def _resolve_prompt_for_render(self) -> None:
        if callable(self._prompt_spec) and not isinstance(self._prompt_spec, str):
            fp = resolve_prompt(self._prompt_spec)
            self.prompt = fp.styled_prompt_prefix
            self.prompt_visible_length = fp.prompt_prefix_visible_length
            self._has_info_line = bool(fp.info_line)
            self._styled_info_line = fp.styled_info_line
            self._info_line_visible_length = fp.info_line_visible_length
            self._has_rprompt = bool(fp.rprompt)
            self._styled_rprompt = fp.styled_rprompt
            self._rprompt_visible_length = fp.rprompt_visible_length

    def reset(self) -> None:
        self._prev_cursor_line = 0
        self._prev_input_lines = 1
        self._box_state = None
        self._resize_during_render = False

    def handle_resize(self) -> None:
        prev_cols, prev_rows, term_cols, term_rows = self.get_resize_diff()

        rows_grew = term_rows > prev_rows
        rows_shrunk = term_rows < prev_rows
        cols_changed = term_cols != prev_cols

        if rows_grew or rows_shrunk:
            scroll_count = min(term_rows, 5)
            if scroll_count > 0:
                sys.stdout.write("\n" * scroll_count)
                sys.stdout.write(f"\033[{scroll_count}A")
                sys.stdout.write("\r")
                sys.stdout.write("\033[J")
                sys.stdout.flush()
        elif cols_changed:
            sys.stdout.write("\033[2J")
            sys.stdout.write(f"\033[{term_rows};1H")
            sys.stdout.flush()

        self._prev_cursor_line = 0
        self._prev_input_lines = 1
        self._box_state = None
        self._resize_during_render = True

    def show_cursor(self) -> None:
        if self._cursor_style_escape:
            sys.stdout.write(self._cursor_style_escape)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    def hide_cursor(self) -> None:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    def reset_cursor(self) -> None:
        sys.stdout.write(reset_cursor_style())
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    def position_cursor_below_rendered(self) -> None:
        prev_box_height = self._box_state["box_height"] if self._box_state else 0
        total_lines = self._prev_input_lines + prev_box_height

        lines_below_cursor = total_lines - 1 - self._prev_cursor_line
        if lines_below_cursor > 0:
            sys.stdout.write(f"\033[{lines_below_cursor}B")

        sys.stdout.write("\r\n")
        sys.stdout.flush()
        self._resize_during_render = False

    def get_terminal_size(self) -> tuple[int, int]:
        try:
            size = shutil.get_terminal_size()
            return (size.columns, size.lines)
        except Exception:
            return (80, 24)

    def truncate_text(self, text: str, max_length: int, suffix: str = "...") -> str:
        return truncate_ansi(text, max_length, suffix=suffix, reset=False)

    def _wrap_text_to_lines(
        self,
        text: str,
        first_width: int,
        rest_width: int,
    ) -> list[str]:
        if not text:
            return []

        lines: list[str] = []
        current_line: list[str] = []
        current_width = 0
        max_width = first_width

        for char in text:
            if char == '\n':
                lines.append("".join(current_line))
                current_line = []
                current_width = 0
                max_width = rest_width
                continue

            w = _wcwidth(char)
            if w < 0:
                w = 1

            if current_width + w > max_width:
                lines.append("".join(current_line))
                current_line = [char]
                current_width = w
                max_width = rest_width
            else:
                current_line.append(char)
                current_width += w

        if current_line:
            lines.append("".join(current_line))

        return lines

    def _calc_input_visible_width(self, text: str, term_cols: int) -> int:
        from wcwidth import wcswidth, wcwidth as _wcwidth

        if not text:
            return 0

        lines = text.split('\n')
        last_line = lines[-1]

        width = wcswidth(last_line)
        if width < 0:
            width = sum(1 for c in last_line if _wcwidth(c) >= 0)
        return width

    def _calc_wrapped_cursor(
        self,
        input_buffer: str,
        cursor_pos: int,
        term_cols: int,
    ) -> tuple[list[str], int, int, int]:
        first_width = max(1, term_cols - self.prompt_visible_length)
        rest_width = term_cols

        lines = self._wrap_text_to_lines(input_buffer, first_width, rest_width)
        total_lines = len(lines) if lines else 1

        cursor_line = 0
        cursor_col = self.prompt_visible_length + 1

        if not input_buffer or cursor_pos == 0:
            return lines, total_lines, cursor_line, cursor_col

        char_idx = 0
        accumulated_width = 0
        line_idx = 0
        line_width_limit = first_width

        for char in input_buffer:
            if char == '\n':
                char_idx += 1
                line_idx += 1
                accumulated_width = 0
                line_width_limit = rest_width

                if char_idx == cursor_pos:
                    cursor_line = line_idx
                    cursor_col = 1
                continue

            w = _wcwidth(char)
            if w < 0:
                w = 1

            if accumulated_width + w > line_width_limit:
                line_idx += 1
                accumulated_width = 0
                line_width_limit = rest_width

            char_idx += 1
            accumulated_width += w

            if char_idx == cursor_pos:
                cursor_line = line_idx
                if line_idx == 0:
                    cursor_col = self.prompt_visible_length + accumulated_width + 1
                else:
                    cursor_col = accumulated_width + 1
                break

        if cursor_pos == len(input_buffer):
            cursor_line = line_idx
            if line_idx == 0:
                cursor_col = self.prompt_visible_length + accumulated_width + 1
            else:
                cursor_col = accumulated_width + 1

        if cursor_col > term_cols:
            cursor_line += 1
            cursor_col = 1

        return lines, total_lines, cursor_line, cursor_col

    def draw_screen(
        self,
        input_buffer: str,
        cursor_pos: int,
        matches: list[CompletionItem],
        show_box: bool,
        selected_idx: int,
        scroll_offset: int = 0,
        suggestion: str | None = None,
    ) -> None:
        self._resolve_prompt_for_render()

        if not self._caps.supports_cursor_movement:
            self._draw_screen_plain(input_buffer, matches, show_box, selected_idx, scroll_offset)
            return

        buf = _OutputBuffer()

        term_cols, term_rows = self.get_terminal_size()

        info_line_rows = 1 if self._has_info_line else 0

        lines, input_lines, cursor_line, cursor_col = self._calc_wrapped_cursor(
            input_buffer, cursor_pos, term_cols
        )

        is_post_resize = self._resize_during_render

        available_for_input = max(1, term_rows - 1 - info_line_rows)

        if input_lines > available_for_input:
            viewport_scroll = max(0, cursor_line - available_for_input + 1)
            max_scroll = max(0, input_lines - available_for_input)
            viewport_scroll = min(viewport_scroll, max_scroll)

            visible_lines = lines[viewport_scroll:viewport_scroll + available_for_input]
            visible_input_lines = len(visible_lines)
            visible_cursor_line = cursor_line - viewport_scroll
        else:
            viewport_scroll = 0
            visible_lines = lines
            visible_input_lines = input_lines
            visible_cursor_line = cursor_line

        total_rendered_rows = info_line_rows + visible_input_lines

        if is_post_resize:
            move_up = min(total_rendered_rows - 1, term_rows - 1)
            if move_up > 0:
                buf.write(f"\r\033[{move_up}A")
            else:
                buf.write("\r")
            for i in range(total_rendered_rows):
                buf.write("\033[2K")
                if i < total_rendered_rows - 1:
                    buf.write("\033[1B")
            if total_rendered_rows > 1:
                buf.write(f"\r\033[{total_rendered_rows - 1}A")
            else:
                buf.write("\r")
            self._resize_during_render = False
        else:
            if self._prev_cursor_line > 0:
                buf.write(f"\r\033[{self._prev_cursor_line}A")
            else:
                buf.write("\r")

            prev_box_height = self._box_state["box_height"] if self._box_state else 0
            lines_to_clear = max(self._prev_input_lines + prev_box_height, 1)
            lines_to_clear = min(lines_to_clear, term_rows)
            for i in range(lines_to_clear):
                buf.write("\033[2K")
                if i < lines_to_clear - 1:
                    buf.write("\033[1B")
            if lines_to_clear > 1:
                buf.write(f"\r\033[{lines_to_clear - 1}A")
            else:
                buf.write("\r")

        if self._has_info_line:
            info = StyleParser.truncate(self._styled_info_line, term_cols)
            buf.write("\033[2K")
            buf.write(info)
            buf.write("\n")

        prompt_prefix = StyleParser.truncate(self.prompt, term_cols)
        for i, line in enumerate(visible_lines):
            if i == 0 and viewport_scroll == 0:
                buf.write(prompt_prefix + line)
            else:
                buf.write(line)
            if i < len(visible_lines) - 1:
                buf.write("\n")

        if not visible_lines:
            buf.write(prompt_prefix)

        if suggestion and cursor_pos == len(input_buffer):
            self._render_suggestion_buf(
                buf, input_buffer, cursor_pos, suggestion,
                visible_cursor_line, cursor_col, term_cols,
            )

        if self._has_rprompt and cursor_pos == len(input_buffer):
            rprompt_pos = term_cols - self._rprompt_visible_length

            if rprompt_pos >= 1:
                input_width = self.prompt_visible_length + self._calc_input_visible_width(input_buffer, term_cols)

                if rprompt_pos > input_width:
                    spaces_to_move = rprompt_pos - cursor_col + 1
                    if spaces_to_move > 0:
                        buf.write(f"\033[{spaces_to_move}C")
                        buf.write(self._styled_rprompt)
                        buf.write(f"\033[{spaces_to_move}D")

        should_show = show_box and len(matches) > 0
        visible_matches: list[CompletionItem] = []

        if should_show:
            MIN_TERMINAL_LINES = 4
            available_rows = term_rows - total_rendered_rows
            max_popup_items = max(available_rows - 2, 0)

            if term_rows < MIN_TERMINAL_LINES or max_popup_items <= 0:
                should_show = False
                visible_matches = []
            else:
                max_items = min(10, max_popup_items)
                visible_matches = matches[scroll_offset:scroll_offset + max_items]

            if not visible_matches:
                self._box_state = None
                cursor_line_from_top = info_line_rows + visible_cursor_line
                if cursor_line_from_top > 0:
                    buf.write(f"\033[{cursor_line_from_top}A")
                buf.write("\r")
                buf.write(f"\033[{cursor_col}G")
                self._prev_cursor_line = cursor_line_from_top
                self._prev_input_lines = total_rendered_rows
                buf.flush()
                return

            available_width = term_cols - 2

            max_text = max(len(m.display_text) for m in visible_matches)
            has_desc = any(m.description for m in visible_matches)
            max_desc = (
                max(len(m.description) for m in visible_matches) if has_desc else 0
            )

            if has_desc:
                box_width = min(
                    max(max_text + max_desc + 7, available_width // 2),
                    available_width
                )
            else:
                box_width = min(max_text + 4, available_width)

            box_width = max(box_width, 20)

            content_width = box_width - 2
            prefix_width = 2
            separator_width = 3 if has_desc else 0
            remaining = content_width - prefix_width - separator_width

            if has_desc:
                if remaining >= max_text + max_desc:
                    desc_width = max_desc
                    text_width = max_text
                else:
                    half_remaining = remaining // 2
                    desc_width = min(max_desc, remaining - max_text)
                    text_width = remaining - desc_width
                if desc_width < 0:
                    desc_width = 0
                    text_width = remaining
            else:
                text_width = remaining
                desc_width = 0

            box_height = len(visible_matches) + 2

            relative_selected_idx = selected_idx - scroll_offset
            relative_selected_idx = max(0, min(relative_selected_idx, len(visible_matches) - 1))
            self._box_state = {
                "visible_matches": visible_matches,
                "box_width": box_width,
                "box_height": box_height,
                "text_width": text_width,
                "desc_width": desc_width,
                "selected_idx": relative_selected_idx,
                "scroll_offset": scroll_offset,
                "input_buffer": input_buffer,
                "term_cols": term_cols,
            }
        else:
            box_width = 0
            box_height = 0
            text_width = 0
            desc_width = 0
            self._box_state = None

        if is_post_resize:
            buf.write("\033[J")
        else:
            buf.write("\n\033[J")
            buf.write("\033[A")

        if should_show:
            relative_selected_idx = selected_idx - scroll_offset
            self._draw_completion_box_buf(
                buf,
                visible_matches,
                box_width,
                box_height,
                text_width,
                desc_width,
                relative_selected_idx,
            )

        end_line = total_rendered_rows - 1
        end_col = 1
        if visible_lines:
            last_line_width = wcswidth(visible_lines[-1])
            if len(visible_lines) == 1 and viewport_scroll == 0:
                end_col = self.prompt_visible_length + last_line_width + 1
            else:
                end_col = last_line_width + 1
        else:
            end_col = self.prompt_visible_length + 1

        cursor_line_from_top = info_line_rows + visible_cursor_line

        if end_line > cursor_line_from_top:
            buf.write(f"\r\033[{end_line - cursor_line_from_top}A")
        elif end_line < cursor_line_from_top:
            buf.write(f"\r\033[{cursor_line_from_top - end_line}B")
        else:
            buf.write("\r")

        buf.write(f"\033[{cursor_col}G")

        self._prev_cursor_line = cursor_line_from_top
        self._prev_input_lines = total_rendered_rows

        buf.flush()

    def _draw_completion_box_buf(
        self,
        buf: _OutputBuffer,
        matches: list[CompletionItem],
        box_width: int,
        box_height: int,
        text_width: int,
        desc_width: int,
        selected_idx: int,
    ) -> None:
        inner_width = box_width - 2

        buf.write("\n" * box_height)

        buf.write(f"\033[{box_height}A")

        buf.write("\r\033[1B")
        buf.write(
            self._styled_border(self.box_chars.top_left) +
            self._styled_border(self.box_chars.horizontal) * inner_width +
            self._styled_border(self.box_chars.top_right)
        )

        for idx, match in enumerate(matches):
            buf.write("\r\033[1B")

            line = self._build_item_line(
                match, idx, selected_idx, inner_width, text_width, desc_width,
            )
            buf.write(line)

        buf.write("\r\033[1B")
        buf.write(
            self._styled_border(self.box_chars.bottom_left) +
            self._styled_border(self.box_chars.horizontal) * inner_width +
            self._styled_border(self.box_chars.bottom_right)
        )

        buf.write(f"\033[{box_height}A")

    def _build_item_line(
        self,
        match: CompletionItem,
        idx: int,
        selected_idx: int,
        inner_width: int,
        text_width: int,
        desc_width: int,
    ) -> str:
        if idx == selected_idx:
            prefix = self.box_chars.arrow_right + " "
            style = self._selected_bg
            reset = "\033[0m"
        else:
            prefix = "  "
            style = ""
            reset = ""

        txt = self.truncate_text(match.display_text, text_width)
        desc = (
            self.truncate_text(match.description, desc_width)
            if match.description
            else ""
        )

        if self.completion_highlighter:
            completion_type = match.type if match.type else "text"
            txt = self.completion_highlighter.highlight_completion(txt, completion_type)

            if desc:
                desc = self.completion_highlighter.highlight_description(desc)

        if match.match_indices:
            txt = self._highlight_match_indices(txt, match.match_indices)

        txt_visible_len = get_visible_length(txt)
        txt_padding = max(0, text_width - txt_visible_len)
        txt_padded = txt + (' ' * txt_padding)

        if desc_width > 0 and match.description:
            desc_visible_len = get_visible_length(desc)
            desc_padding = max(0, desc_width - desc_visible_len)
            desc_padded = desc + (' ' * desc_padding)
            content = f"{prefix}{txt_padded} {self.box_chars.vertical} {desc_padded}"
        else:
            content = f"{prefix}{txt_padded}"

        visible_len = get_visible_length(content)
        padding_needed = inner_width - visible_len

        if padding_needed > 0:
            content = content + (' ' * padding_needed)
        elif padding_needed < 0:
            content = self._truncate_ansi_content(content, inner_width)

        styled_content = f"{style}{content}{reset}"

        return (
            f"{self._styled_border(self.box_chars.vertical)}"
            f"{styled_content}"
            f"{self._styled_border(self.box_chars.vertical)}"
        )

    def _render_suggestion_buf(
        self,
        buf: _OutputBuffer,
        input_buffer: str,
        cursor_pos: int,
        suggestion: str,
        cursor_line: int = 0,
        cursor_col: int = 0,
        term_cols: int = 80,
    ) -> None:
        if not suggestion:
            return

        if "\n" in suggestion or "\r" in suggestion:
            suggestion = suggestion.replace("\r", "").replace("\n", " ")
        if not suggestion:
            return

        remaining_cols = max(0, term_cols - cursor_col + 1)

        if remaining_cols <= 0:
            return

        truncated = self._truncate_plain(suggestion, remaining_cols)

        if self._suggestion_style:
            styled = f"{self._suggestion_style}{truncated}\033[0m"
        elif self._caps.supports_dim:
            styled = f"\033[2m{truncated}\033[0m"
        elif self._caps.color_level >= 1:
            if self._caps.color_level >= 2:
                styled = f"\033[38;5;245m{truncated}\033[0m"
            else:
                styled = f"\033[37m{truncated}\033[0m"
        else:
            return

        buf.write(styled)

    def draw_selection_update(
        self,
        old_selected_idx: int,
        new_selected_idx: int,
        cursor_pos: int,
    ) -> None:
        if self._box_state is None:
            return

        bs = self._box_state
        matches = bs["visible_matches"]
        box_width = bs["box_width"]
        _box_height = bs["box_height"]
        text_width = bs["text_width"]
        desc_width = bs["desc_width"]
        inner_width = box_width - 2

        if old_selected_idx >= len(matches) or new_selected_idx >= len(matches):
            return

        buf = _OutputBuffer()

        old_line_offset = 1 + 1 + old_selected_idx
        buf.write(f"\r\033[{old_line_offset}B")
        old_line = self._build_item_line(
            matches[old_selected_idx], old_selected_idx, new_selected_idx,
            inner_width, text_width, desc_width,
        )
        buf.write("\r\033[2K")
        buf.write(old_line)

        delta = new_selected_idx - old_selected_idx
        if delta > 0:
            buf.write(f"\r\033[{delta}B")
        elif delta < 0:
            buf.write(f"\r\033[{abs(delta)}A")

        new_line = self._build_item_line(
            matches[new_selected_idx], new_selected_idx, new_selected_idx,
            inner_width, text_width, desc_width,
        )
        buf.write("\r\033[2K")
        buf.write(new_line)

        go_up = 1 + 1 + new_selected_idx
        buf.write(f"\r\033[{go_up}A")

        stored_input = bs.get("input_buffer", "")
        stored_cols = bs.get("term_cols", 80)
        _lines, _total_lines, cursor_line, cursor_col = self._calc_wrapped_cursor(
            stored_input, cursor_pos, stored_cols
        )

        end_line = _total_lines - 1
        if end_line > cursor_line:
            buf.write(f"\r\033[{end_line - cursor_line}A")
        elif end_line < cursor_line:
            buf.write(f"\r\033[{cursor_line - end_line}B")
        else:
            buf.write("\r")

        buf.write(f"\033[{cursor_col}G")

        bs["selected_idx"] = new_selected_idx

        buf.flush()

    def _truncate_plain(self, text: str, max_width: int) -> str:
        if max_width <= 0:
            return ""

        result: list[str] = []
        current_width = 0

        for char in text:
            char_width = _wcwidth(char)
            if char_width < 0:
                char_width = 1
            if current_width + char_width > max_width:
                break
            result.append(char)
            current_width += char_width

        if len(result) < len(text) and current_width + 1 <= max_width:
            result.append("…")

        return ''.join(result)

    def _highlight_match_indices(self, text: str, indices: list[int]) -> str:
        if not indices:
            return text

        segments: list[tuple[str, str]] = []
        visible_idx = 0
        i = 0
        pending_ansi = ""

        while i < len(text):
            if text[i] == '\x1b' and i + 1 < len(text) and text[i + 1] == '[':
                end = text.find('m', i)
                if end != -1:
                    pending_ansi += text[i:end + 1]
                    i = end + 1
                    continue

            segments.append((pending_ansi, text[i]))
            pending_ansi = ""
            visible_idx += 1
            i += 1

        indices_set = set(indices)
        result: list[str] = []
        in_highlight = False

        for seg_idx, (ansi_prefix, char) in enumerate(segments):
            should_highlight = seg_idx in indices_set

            if should_highlight and not in_highlight:
                if ansi_prefix:
                    result.append(ansi_prefix)
                result.append("\033[1;4m")
                result.append(char)
                in_highlight = True
            elif should_highlight and in_highlight:
                if ansi_prefix:
                    result.append("\033[0m")
                    result.append(ansi_prefix)
                    result.append("\033[1;4m")
                result.append(char)
            elif not should_highlight and in_highlight:
                result.append("\033[0m")
                if ansi_prefix:
                    result.append(ansi_prefix)
                result.append(char)
                in_highlight = False
            else:
                if ansi_prefix:
                    result.append(ansi_prefix)
                result.append(char)

        if in_highlight:
            result.append("\033[0m")

        if pending_ansi:
            result.append(pending_ansi)

        return ''.join(result)

    def _truncate_ansi_content(self, text: str, target_width: int) -> str:
        result: list[str] = []
        current_width = 0
        i = 0
        while i < len(text):
            if text[i] == '\x1b' and i + 1 < len(text) and text[i + 1] == '[':
                end = text.find('m', i)
                if end != -1:
                    result.append(text[i:end + 1])
                    i = end + 1
                    continue
            char_width = _wcwidth(text[i])
            if char_width < 0:
                char_width = 1
            if current_width + char_width > target_width:
                break
            result.append(text[i])
            current_width += char_width
            i += 1
        return ''.join(result)

    def _draw_screen_plain(
        self,
        input_buffer: str,
        matches: list[CompletionItem],
        show_box: bool,
        selected_idx: int,
        scroll_offset: int = 0,
        _suggestion: str | None = None,
    ) -> None:
        clean_prompt = self._caps.strip_ansi(self.prompt)

        if self._has_info_line:
            clean_info = self._caps.strip_ansi(self._styled_info_line)
            sys.stdout.write(f"\r{clean_info}\n")

        term_cols, _ = self.get_terminal_size()
        first_width = max(1, term_cols - len(clean_prompt))
        lines = self._wrap_text_to_lines(input_buffer, first_width, term_cols)

        if lines:
            sys.stdout.write(f"\r{clean_prompt}{lines[0]}")
            for line in lines[1:]:
                sys.stdout.write(f"\n{line}")
        else:
            sys.stdout.write(f"\r{clean_prompt}")

        if show_box and matches:
            max_items = 10
            visible_matches = matches[scroll_offset:scroll_offset + max_items]
            sys.stdout.write("\n")
            for idx, match in enumerate(visible_matches):
                actual_idx = scroll_offset + idx
                marker = ">" if actual_idx == selected_idx else " "
                desc = f" - {match.description}" if match.description else ""
                sys.stdout.write(f"  {marker} {match.display_text}{desc}\n")
            sys.stdout.flush()

    def _calc_input_lines(self, input_buffer: str, cursor_pos: int = 0) -> tuple[int, int, int]:
        term_cols, _ = self.get_terminal_size()
        if term_cols <= 0:
            term_cols = 80

        _lines, total_lines, cursor_line, cursor_col = self._calc_wrapped_cursor(
            input_buffer, cursor_pos, term_cols
        )

        return total_lines, cursor_line, cursor_col

    def clear_below(self) -> None:
        if not self._caps.supports_cursor_movement:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return
        sys.stdout.write("\n\033[J")
        sys.stdout.write("\033[A\r")
