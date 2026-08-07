from __future__ import annotations

import os
import sys
import signal
import select
import asyncio
import time
import tty
import termios
from types import FrameType
from typing import Union, Literal, TYPE_CHECKING
from .completion import CompletionItem, Completer, WordCompleter
from .input import InputHandler
from .renderer import Renderer
from .highlighter import Highlighter, CompletionHighlighter
from .styling import StyleParser
from .terminal import get_capabilities
from .history import History
from .formatted_prompt import resolve_prompt

if TYPE_CHECKING:
    from .formatted_prompt import PromptSpec, FormattedPrompt

_HandleAction = Literal["continue", "submit", "interrupt"]


class Prompt:

    def __init__(
        self,
        completer: Union[Completer, WordCompleter],
        prompt: PromptSpec = ">>> ",
        box_style: str = "rounded",
        highlighter: Highlighter | None = None,
        history: History | list[str] | None = None,
        autosuggest: bool = True,
        completion_style: dict[str, str] | None = None,
        suggestion_style: str | None = None,
        prompt_style: str | None = None,
        cursor_style: str | None = None,
    ) -> None:
        self.completer: Union[Completer, WordCompleter] = completer
        self.input_handler: InputHandler = InputHandler()
        self.highlighter: Highlighter | None = highlighter

        self._caps = get_capabilities()

        self.completion_highlighter: CompletionHighlighter | None = (
            CompletionHighlighter(highlighter) if highlighter else None
        )

        if isinstance(prompt, str):
            if prompt_style and '[' not in prompt:
                styled_prompt_raw = f"[{prompt_style}]{prompt}[/]"
                self.styled_prompt: str = StyleParser.parse(styled_prompt_raw)
            else:
                self.styled_prompt: str = StyleParser.parse(prompt)
            self.prompt_visible_length: int = StyleParser.get_visible_length(self.styled_prompt)
            renderer_prompt: PromptSpec = self.styled_prompt
        else:
            self.styled_prompt = ""
            self.prompt_visible_length = 0
            renderer_prompt = prompt

        self.renderer: Renderer = Renderer(
            renderer_prompt,
            box_style=box_style,
            completion_highlighter=self.completion_highlighter,
            prompt_visible_length=self.prompt_visible_length if isinstance(prompt, str) else None,
            completion_style=completion_style,
            suggestion_style=suggestion_style,
            cursor_style=cursor_style,
        )

        self.prompt: PromptSpec = prompt
        self.input_buffer: str = ""
        self.cursor_pos: int = 0
        self.selected_idx: int = 0
        self.show_box: bool = False
        self.scroll_offset: int = 0
        self._tab_triggered: bool = False

        self.resize_pending: bool = False

        if isinstance(history, History):
            self.history: History = history
        elif isinstance(history, list):
            self.history = History(strings=history)
        else:
            self.history = History()

        self.autosuggest: bool = autosuggest
        self._autosuggestion: str | None = None

        self._prev_selected_idx: int = 0
        self._prev_scroll_offset: int = 0

        self._setup_resize_handler()

    def _run_fallback(self) -> str:
        clean_prompt = self._caps.strip_ansi(self.styled_prompt)

        while True:
            try:
                result = input(clean_prompt)
                return result
            except EOFError as exc:
                raise KeyboardInterrupt from exc

    def _setup_resize_handler(self) -> None:
        def handle_resize(_signum: int, _frame: FrameType | None) -> None:
            self.renderer.on_sigwinch()

        try:
            signal.signal(signal.SIGWINCH, handle_resize)
        except Exception:
            pass

    def _update_autosuggestion(self) -> None:
        if not self.autosuggest or self.history.is_navigating:
            self._autosuggestion = None
            return

        self._autosuggestion = self.history.get_suggestion(self.input_buffer)

    def apply_completion(self, match: CompletionItem) -> None:
        words = self.input_buffer.split()
        if words:
            words[-1] = match.text
            self.input_buffer = ' '.join(words) + " "
        else:
            self.input_buffer = match.text + " "

        self.cursor_pos = len(self.input_buffer)
        self.show_box = False

    def _handle_char(
        self, ch: str, matches: list[CompletionItem]
    ) -> tuple[_HandleAction, list[CompletionItem]]:
        if self.resize_pending:
            self.resize_pending = False
            return "continue", []

        if self.input_handler.is_paste_start(ch):
            paste_text = self.input_handler.read_paste_content()
            if paste_text:
                self.input_buffer = (
                    self.input_buffer[:self.cursor_pos] + paste_text +
                    self.input_buffer[self.cursor_pos:]
                )
                self.cursor_pos += len(paste_text)
                if self.history.is_navigating:
                    self.history.reset()
                self._update_autosuggestion()
            ch = ''

        if self.input_handler.is_enter(ch):
            query = self.completer.get_last_word(self.input_buffer)
            matches = self.completer.get_matches(query, limit=None)

            if self.show_box and matches:
                self.apply_completion(matches[self.selected_idx])
                self._tab_triggered = False
                self._update_autosuggestion()
                query_for_match = self.input_buffer.rstrip()
                query = self.completer.get_last_word(query_for_match)
                matches = self.completer.get_matches(query, limit=None)
            else:
                self.history.append(self.input_buffer)
                self.history.reset()
                self._autosuggestion = None
                self.renderer.draw_screen(
                    self.input_buffer, self.cursor_pos, matches,
                    False, self.selected_idx, self.scroll_offset,
                    suggestion=None,
                )
                return "submit", matches

        elif self.input_handler.is_tab(ch):
            if self._autosuggestion:
                self.input_buffer += self._autosuggestion
                self.cursor_pos = len(self.input_buffer)
                self._autosuggestion = None
                self.show_box = False
                self._tab_triggered = False
            else:
                query_for_match = self.input_buffer.rstrip()
                query = self.completer.get_last_word(query_for_match)
                matches = self.completer.get_matches(query, limit=None)

                if matches:
                    if not self.show_box:
                        self.show_box = True
                        self.selected_idx = 0
                        self._tab_triggered = not self.input_buffer.strip()
                    else:
                        prev_idx = self.selected_idx
                        self.selected_idx = (self.selected_idx + 1) % len(matches)

                        if prev_idx == len(matches) - 1 and self.selected_idx == 0:
                            self.scroll_offset = 0
                        else:
                            viewport_size = 10
                            if self.selected_idx >= self.scroll_offset + viewport_size:
                                self.scroll_offset = self.selected_idx - viewport_size + 1

        elif self.input_handler.is_backspace(ch):
            if self.cursor_pos > 0:
                self.input_buffer = (
                    self.input_buffer[:self.cursor_pos - 1] +
                    self.input_buffer[self.cursor_pos:]
                )
                self.cursor_pos -= 1
                self.show_box = len(self.input_buffer) > 0
                if not self.show_box:
                    self._tab_triggered = False
                if self.history.is_navigating:
                    self.history.reset()
                self._update_autosuggestion()

        elif self.input_handler.is_ctrl_c(ch):
            sys.stdout.write("\n\033[J")
            print("^C")
            return "interrupt", matches

        elif self.input_handler.is_arrow_up(ch):
            if self.show_box and matches:
                prev_idx = self.selected_idx
                self.selected_idx = (self.selected_idx - 1) % len(matches)

                old_scroll = self.scroll_offset
                viewport_size = (len(self.renderer._box_state["visible_matches"])
                                 if self.renderer._box_state else 10)
                if prev_idx == 0 and self.selected_idx == len(matches) - 1:
                    self.scroll_offset = max(0, len(matches) - viewport_size)
                elif self.selected_idx < self.scroll_offset:
                    self.scroll_offset = self.selected_idx

                if self.scroll_offset == old_scroll and self.renderer._box_state is not None:
                    old_rel = prev_idx - old_scroll
                    new_rel = self.selected_idx - self.scroll_offset
                    if 0 <= old_rel < viewport_size and 0 <= new_rel < viewport_size:
                        self.renderer.draw_selection_update(old_rel, new_rel, self.cursor_pos)
                        self._prev_selected_idx = new_rel
                        self._prev_scroll_offset = self.scroll_offset
                        return "continue", matches
            else:
                lines = self.input_buffer.split('\n')
                if len(lines) > 1:
                    line_idx, col = self._get_line_col()
                    if line_idx > 0:
                        prev_line_len = len(lines[line_idx - 1])
                        new_col = min(col, prev_line_len)
                        self.cursor_pos = self._line_col_to_pos(line_idx - 1, new_col)
                    else:
                        new_input = self.history.up(self.input_buffer)
                        self.input_buffer = new_input
                        self.cursor_pos = len(self.input_buffer)
                        self._autosuggestion = None
                else:
                    new_input = self.history.up(self.input_buffer)
                    self.input_buffer = new_input
                    self.cursor_pos = len(self.input_buffer)
                    self._autosuggestion = None

        elif self.input_handler.is_arrow_down(ch):
            if self.show_box and matches:
                prev_idx = self.selected_idx
                self.selected_idx = (self.selected_idx + 1) % len(matches)

                old_scroll = self.scroll_offset
                viewport_size = (len(self.renderer._box_state["visible_matches"])
                                 if self.renderer._box_state else 10)
                if prev_idx == len(matches) - 1 and self.selected_idx == 0:
                    self.scroll_offset = 0
                else:
                    if self.selected_idx >= self.scroll_offset + viewport_size:
                        self.scroll_offset = self.selected_idx - viewport_size + 1

                if self.scroll_offset == old_scroll and self.renderer._box_state is not None:
                    old_rel = prev_idx - old_scroll
                    new_rel = self.selected_idx - self.scroll_offset
                    if 0 <= old_rel < viewport_size and 0 <= new_rel < viewport_size:
                        self.renderer.draw_selection_update(old_rel, new_rel, self.cursor_pos)
                        self._prev_selected_idx = new_rel
                        self._prev_scroll_offset = self.scroll_offset
                        return "continue", matches
            else:
                lines = self.input_buffer.split('\n')
                if len(lines) > 1:
                    line_idx, col = self._get_line_col()
                    if line_idx < len(lines) - 1:
                        next_line_len = len(lines[line_idx + 1])
                        new_col = min(col, next_line_len)
                        self.cursor_pos = self._line_col_to_pos(line_idx + 1, new_col)
                    else:
                        new_input = self.history.down()
                        self.input_buffer = new_input
                        self.cursor_pos = len(self.input_buffer)
                        self._autosuggestion = None
                else:
                    new_input = self.history.down()
                    self.input_buffer = new_input
                    self.cursor_pos = len(self.input_buffer)
                    self._autosuggestion = None

        elif self.input_handler.is_ctrl_arrow_right(ch):
            if self._autosuggestion:
                word_end = 0
                while (word_end < len(self._autosuggestion)
                       and self._autosuggestion[word_end] == ' '):
                    word_end += 1
                while (word_end < len(self._autosuggestion)
                       and self._autosuggestion[word_end] != ' '):
                    word_end += 1

                if word_end > 0:
                    accepted = self._autosuggestion[:word_end]
                    self.input_buffer += accepted
                    self.cursor_pos = len(self.input_buffer)
                    self._update_autosuggestion()
                self.show_box = False
                self._tab_triggered = False

        elif self.input_handler.is_arrow_right(ch):
            if self._autosuggestion:
                self.input_buffer += self._autosuggestion
                self.cursor_pos = len(self.input_buffer)
                self._autosuggestion = None
                self.show_box = False
                self._tab_triggered = False
            elif self.cursor_pos < len(self.input_buffer):
                self.cursor_pos += 1
                self.show_box = False
                self._tab_triggered = False

        elif self.input_handler.is_arrow_left(ch):
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            self.show_box = False
            self._tab_triggered = False

        elif self.input_handler.is_space(ch):
            self.input_buffer = (
                self.input_buffer[:self.cursor_pos] + ' ' +
                self.input_buffer[self.cursor_pos:]
            )
            self.cursor_pos += 1
            self.show_box = False
            self._tab_triggered = False
            if self.history.is_navigating:
                self.history.reset()
            self._update_autosuggestion()

        elif self.input_handler.is_escape(ch):
            if self.show_box:
                self.show_box = False
                self._tab_triggered = False

        elif self.input_handler.is_printable(ch):
            self.input_buffer = (
                self.input_buffer[:self.cursor_pos] + ch +
                self.input_buffer[self.cursor_pos:]
            )
            self.cursor_pos += 1
            self.show_box = True
            self.selected_idx = 0
            self._tab_triggered = False
            if self.history.is_navigating:
                self.history.reset()
            self._update_autosuggestion()

        if ch not in ('\r', '\n', '\t'):
            query_for_match = self.input_buffer.rstrip()
            query = self.completer.get_last_word(query_for_match)
            matches = self.completer.get_matches(query, limit=None)

        if not matches:
            self.show_box = False
            self._tab_triggered = False
        elif not self.input_buffer.strip() and not self._tab_triggered:
            self.show_box = False

        if matches and self.show_box:
            self.selected_idx = min(self.selected_idx, len(matches) - 1)
            self.selected_idx = max(0, self.selected_idx)
            viewport_size = (len(self.renderer._box_state["visible_matches"])
                             if self.renderer._box_state else 10)
            if self.scroll_offset > len(matches) - viewport_size:
                self.scroll_offset = max(0, len(matches) - viewport_size)
            if self.selected_idx < self.scroll_offset:
                self.scroll_offset = self.selected_idx
            elif self.selected_idx >= self.scroll_offset + viewport_size:
                self.scroll_offset = self.selected_idx - viewport_size + 1
        else:
            self.selected_idx = 0
            self.scroll_offset = 0

        self.renderer.draw_screen(
            self.input_buffer, self.cursor_pos, matches,
            self.show_box, self.selected_idx, self.scroll_offset,
            suggestion=self._autosuggestion,
        )

        return "continue", matches

    def run(self) -> str:
        if not self._caps.is_tty_in or not self._caps.supports_cursor_movement:
            return self._run_fallback()

        self.renderer.reset()
        self.renderer.draw_screen(
            self.input_buffer, self.cursor_pos, [], False, 0, 0,
            suggestion=None,
        )
        self.renderer.show_cursor()
        matches: list[CompletionItem] = []

        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()

        _pipe_r: int = -1
        _pipe_w: int = -1
        _prev_sigwinch = None

        _stdin_fd = self.input_handler.fd if self.input_handler.fd >= 0 else sys.stdin.fileno()
        _old_termios = termios.tcgetattr(_stdin_fd)
        _raw = termios.tcgetattr(_stdin_fd)
        tty.setraw(_stdin_fd)
        _raw = termios.tcgetattr(_stdin_fd)
        _raw[1] |= termios.OPOST
        if hasattr(termios, 'ONLCR'):
            _raw[1] |= termios.ONLCR
        termios.tcsetattr(_stdin_fd, termios.TCSADRAIN, _raw)

        try:
            while True:
                _watch = [_stdin_fd]
                if _pipe_r >= 0:
                    _watch.append(_pipe_r)

                try:
                    _ready, _, _ = select.select(_watch, [], [], 0.025)
                except (ValueError, OSError):
                    _ready = [_stdin_fd]

                if self.renderer.check_resize_event():
                    self.renderer.handle_resize()
                    self.renderer.draw_screen(
                        self.input_buffer, self.cursor_pos, matches,
                        self.show_box, self.selected_idx, self.scroll_offset,
                        suggestion=self._autosuggestion,
                    )
                    self.renderer.mark_resize_redrawn()

                if _stdin_fd in _ready:
                    ch = self.input_handler.read_char(already_raw=True)
                    action, matches = self._handle_char(ch, matches)
                    if action == "submit":
                        return self.input_buffer
                    if action == "interrupt":
                        raise KeyboardInterrupt
        finally:
            try:
                termios.tcsetattr(_stdin_fd, termios.TCSADRAIN, _old_termios)
            except Exception:
                pass
            if _prev_sigwinch is not None:
                try:
                    signal.signal(signal.SIGWINCH, _prev_sigwinch)
                except Exception:
                    pass
            for _fd in (_pipe_r, _pipe_w):
                if _fd >= 0:
                    try:
                        os.close(_fd)
                    except OSError:
                        pass
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()
            self.renderer.position_cursor_below_rendered()
            self.renderer.reset_cursor()

    async def run_async(self) -> str:
        if not self._caps.is_tty_in or not self._caps.supports_cursor_movement:
            return self._run_fallback()

        self.renderer.reset()
        self.renderer.draw_screen(
            self.input_buffer, self.cursor_pos, [], False, 0, 0,
            suggestion=None,
        )
        self.renderer.show_cursor()
        matches: list[CompletionItem] = []

        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()

        try:
            while True:
                ch = await asyncio.to_thread(self.input_handler.read_char)
                action, matches = self._handle_char(ch, matches)
                if action == "submit":
                    return self.input_buffer
                if action == "interrupt":
                    raise KeyboardInterrupt
                self.renderer.check_resize()
                if self.renderer.should_redraw_on_resize():
                    self.renderer.handle_resize()
                    self.renderer.draw_screen(
                        self.input_buffer, self.cursor_pos, matches,
                        self.show_box, self.selected_idx, self.scroll_offset,
                        suggestion=self._autosuggestion,
                    )
                    self.renderer.mark_resize_redrawn()
        except asyncio.CancelledError:
            sys.stdout.write("\x1b[?2004l")
            self.renderer.show_cursor()
            sys.stdout.write("\n\033[J")
            sys.stdout.flush()
            raise
        finally:
            try:
                sys.stdout.write("\x1b[?2004l")
                sys.stdout.flush()
            except Exception:
                pass
            self.renderer.position_cursor_below_rendered()
            self.renderer.reset_cursor()

    def _get_line_col(self) -> tuple[int, int]:
        lines = self.input_buffer.split('\n')
        pos = 0
        for i, line in enumerate(lines):
            if pos + len(line) >= self.cursor_pos:
                return i, self.cursor_pos - pos
            pos += len(line) + 1
        return len(lines) - 1, len(lines[-1])

    def _line_col_to_pos(self, line_idx: int, col: int) -> int:
        lines = self.input_buffer.split('\n')
        pos = 0
        for i in range(line_idx):
            pos += len(lines[i]) + 1
        return pos + min(col, len(lines[line_idx]))
