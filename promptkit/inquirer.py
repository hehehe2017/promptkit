import sys
import asyncio
import signal
from typing import Optional, Callable, Any, List
from .input import InputHandler
from .border_renderer import BorderRenderer, _OutputBuffer, get_visible_length, truncate_ansi_content
from .box_chars import BoxChars
from .styling import StyleParser
from .terminal import get_capabilities


class Confirm:

    def __init__(
        self,
        message: str,
        default: bool = True,
        confirm_letter: str = "y",
        reject_letter: str = "n",
        transformer: Optional[Callable[[bool], Any]] = None,
        border: bool = True,
        box_style: str = "rounded",
        border_color: str = "",
        show_cursor: bool = True,
        qmark_style: str = "bold",
        confirm_style: str = "bold green",
        reject_style: str = "bold red"
    ):
        self.message = message
        self.default = default
        self.confirm_letter = confirm_letter.lower()
        self.reject_letter = reject_letter.lower()
        self.transformer = transformer
        self.border = border
        self.box_style = box_style
        self.border_color = border_color
        self.show_cursor = show_cursor
        self.qmark_style = qmark_style
        self.confirm_style = confirm_style
        self.reject_style = reject_style

        self.input_handler = InputHandler()
        self.box_chars = BoxChars.for_style(box_style)
        self._border_renderer = BorderRenderer(box_style=box_style, border_color=border_color)
        self._resize_pending = False

    def _draw_dialog(self, current_value: Optional[bool] = None) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25l")

        if current_value is None:
            display_value = self.default
        else:
            display_value = current_value

        styled_qmark = StyleParser.parse(f"[{self.qmark_style}]?[/]")
        confirm_char = self.confirm_letter.upper() if display_value else self.confirm_letter.lower()
        reject_char = self.reject_letter.lower() if display_value else self.reject_letter.upper()
        styled_confirm = StyleParser.parse(f"[{self.confirm_style}]{confirm_char}[/]")
        styled_reject = StyleParser.parse(f"[{self.reject_style}]{reject_char}[/]")
        prompt_line = f"{styled_qmark} {self.message} ({styled_confirm}/{styled_reject})"

        if self.border:
            self._border_renderer.draw_box(
                content_lines=[prompt_line],
                selected_idx=0,
                scroll_offset=0,
                max_visible=1
            )
        else:
            sys.stdout.write("\r\033[2K")
            sys.stdout.write(prompt_line)
            sys.stdout.flush()

    def _clear_border(self) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25h")
        if self.border:
            self._border_renderer.clear_rendered()

    def run(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        prev_handler = signal.getsignal(signal.SIGWINCH)

        def _on_resize(sig, frame):
            self._resize_pending = True
            self._border_renderer.on_sigwinch()

        signal.signal(signal.SIGWINCH, _on_resize)

        try:
            self._draw_dialog()
            result = self.default

            while True:
                ch = self.input_handler.read_char()

                if self._resize_pending or self._border_renderer._resize_during_render:
                    self._resize_pending = False
                    self._border_renderer.handle_resize()
                    self._draw_dialog(result if result != self.default else None)
                    continue

                if ch == '\r' or ch == '\n':
                    self._clear_border()
                    if self.transformer:
                        return self.transformer(result)
                    return result

                elif ch.lower() == self.confirm_letter:
                    result = True
                    self._draw_dialog(result)

                elif ch.lower() == self.reject_letter:
                    result = False
                    self._draw_dialog(result)

                elif ch == '\x03':
                    self._clear_border()
                    print("^C")
                    raise KeyboardInterrupt
        finally:
            signal.signal(signal.SIGWINCH, prev_handler)

    async def run_async(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        prev_handler = signal.getsignal(signal.SIGWINCH)

        def _on_resize(sig, frame):
            self._resize_pending = True
            self._border_renderer.on_sigwinch()

        signal.signal(signal.SIGWINCH, _on_resize)

        try:
            self._draw_dialog()
            result = self.default

            while True:
                ch = await asyncio.to_thread(self.input_handler.read_char)

                if self._resize_pending:
                    self._resize_pending = False
                    self._border_renderer.handle_resize()
                    self._draw_dialog(result if result != self.default else None)
                    continue

                if ch == '\r' or ch == '\n':
                    self._clear_border()
                    if self.transformer:
                        return self.transformer(result)
                    return result

                elif ch.lower() == self.confirm_letter:
                    result = True
                    self._draw_dialog(result)

                elif ch.lower() == self.reject_letter:
                    result = False
                    self._draw_dialog(result)

                elif ch == '\x03':
                    self._clear_border()
                    print("^C")
                    raise KeyboardInterrupt

        except asyncio.CancelledError:
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\n\033[J")
            sys.stdout.flush()
            raise
        finally:
            signal.signal(signal.SIGWINCH, prev_handler)

    def _run_fallback(self) -> Any:
        confirm_char = self.confirm_letter.upper() if self.default else self.confirm_letter.lower()
        reject_char = self.reject_letter.lower() if self.default else self.reject_letter.upper()
        prompt_text = f"{self.message} ({confirm_char}/{reject_char}) "
        while True:
            try:
                response = input(prompt_text).strip().lower()
                if response == self.confirm_letter:
                    result = True
                elif response == self.reject_letter:
                    result = False
                elif response == "":
                    result = self.default
                else:
                    continue

                if self.transformer:
                    return self.transformer(result)
                return result
            except EOFError as exc:
                raise KeyboardInterrupt from exc


def confirm(
    message: str,
    default: bool = True,
    confirm_letter: str = "y",
    reject_letter: str = "n",
    transformer: Optional[Callable[[bool], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    show_cursor: bool = True,
    qmark_style: str = "bold",
    confirm_style: str = "bold green",
    reject_style: str = "bold red"
) -> Confirm:
    """Create a Yes/No confirmation dialog.

    Args:
        message: The question/message to display.
        default: Default value (``True`` for Yes, ``False`` for No). Default: ``True``.
        confirm_letter: Letter for Yes confirmation (default: ``'y'``).
        reject_letter: Letter for No confirmation (default: ``'n'``).
        transformer: Function to transform the ``bool`` result before returning.
        border: Whether to draw a border around the dialog (default: ``True``).
        box_style: Box style if ``border`` is ``True`` — ``'rounded'`` (default),
            ``'square'``, ``'ascii'``, ``'double'``, or ``'heavy'``.
        show_cursor: Show terminal cursor (default: ``True``).
        qmark_style: Style for the question mark (default: ``'bold'``).
        confirm_style: Style for the confirm letter (default: ``'bold green'``).
        reject_style: Style for the reject letter (default: ``'bold red'``).

    Returns:
        :class:`Confirm` dialog instance. Call ``.run()`` (sync) or
        ``.run_async()`` (async) to execute and get the result.

    Examples:
        >>> if confirm("Continue?", default=True).run():
        ...     print("Yes!")
        >>> result = confirm("Proceed?", border=False).run()
        >>> result = confirm("Continue?", transformer=lambda x: "Yes" if x else "No").run()
        >>> result = confirm("Proceed?", show_cursor=False).run()
        >>> result = confirm("Continue?", confirm_style="bold red").run()
    """
    return Confirm(
        message=message,
        default=default,
        confirm_letter=confirm_letter,
        reject_letter=reject_letter,
        transformer=transformer,
        border=border,
        box_style=box_style,
        show_cursor=show_cursor,
        qmark_style=qmark_style,
        confirm_style=confirm_style,
        reject_style=reject_style
    )


class Select:

    def __init__(
        self,
        message: str,
        choices: List[str],
        default: Optional[str] = None,
        cursor: str = "►",
        transformer: Optional[Callable[[Any], Any]] = None,
        border: bool = True,
        box_style: str = "rounded",
        border_color: str = "",
        max_visible: int = 10,
        multiselect: bool = False,
        show_cursor: bool = True,
        pointer: str = "►",
        qmark: str = "?",
        amark: str = "x",
        hidden_select: bool = False,
        position_render: str = "left",
        pointer_style: str = "bold green",
        amark_style: str = "bold green",
        qmark_style: str = "bold",
        selected_style: str = "bold"
    ):
        self.message = message
        self.choices = choices
        self.default = default
        self.cursor = cursor
        self.pointer = pointer
        self.transformer = transformer
        self.border = border
        self.box_style = box_style
        self.border_color = border_color
        self.max_visible = max_visible
        self.multiselect = multiselect
        self.show_cursor = show_cursor
        self.qmark = qmark
        self.amark = amark
        self.hidden_select = hidden_select
        self.position_render = position_render
        self.pointer_style = pointer_style
        self.amark_style = amark_style
        self.qmark_style = qmark_style
        self.selected_style = selected_style

        self.input_handler = InputHandler()
        self.box_chars = BoxChars.for_style(box_style)

        self._border_renderer = BorderRenderer(
            box_style=box_style,
            border_color=border_color,
            position_offset=0,
        )

        if default and default in choices:
            self.selected_idx = choices.index(default)
        else:
            self.selected_idx = 0

        self.scroll_offset = 0

        self._resize_pending = False

        self.selected_indices: set[int] = set()
        if multiselect and default and default in choices:
            self.selected_indices.add(choices.index(default))

    def _draw_dialog(self) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25l")

        if self.border:
            self._draw_with_border()
        else:
            self._draw_without_border()

    def _get_position_offset(self, content_width: int, term_width: int, box_border_width: int = 0) -> int:
        total_width = content_width + box_border_width

        if self.position_render == "left":
            return 0
        elif self.position_render == "center":
            return max(0, (term_width - total_width) // 2)
        elif self.position_render == "right":
            return max(0, term_width - total_width)
        else:
            return 0

    def _draw_with_border(self) -> None:
        import shutil
        term_cols, _ = shutil.get_terminal_size()

        styled_qmark = StyleParser.parse(f"[{self.qmark_style}]{self.qmark}[/]")
        styled_message = f"{styled_qmark} {self.message}"

        pointer_visible_len = get_visible_length(self.pointer)
        amark_visible_len = get_visible_length(self.amark) if self.multiselect else 0

        content_lines = []
        for idx, choice in enumerate(self.choices):
            if self.multiselect:
                if idx in self.selected_indices:
                    if idx == self.selected_idx:
                        styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                        styled_amark = StyleParser.parse(f"[{self.amark_style}]{self.amark}[/]")
                        prefix = styled_pointer + " " + styled_amark + " "
                    else:
                        cursor_spaces = " " * pointer_visible_len
                        styled_amark = StyleParser.parse(f"[{self.amark_style}]{self.amark}[/]")
                        prefix = cursor_spaces + " " + styled_amark + " "
                else:
                    if idx == self.selected_idx:
                        mark_spaces = " " * amark_visible_len
                        styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                        prefix = styled_pointer + " " + mark_spaces + " "
                    else:
                        cursor_spaces = " " * pointer_visible_len
                        mark_spaces = " " * amark_visible_len
                        prefix = cursor_spaces + " " + mark_spaces + " "
            else:
                if idx == self.selected_idx:
                    styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                    prefix = styled_pointer + " "
                else:
                    prefix = " " * (pointer_visible_len + 1)

            if idx == self.selected_idx and self.selected_style:
                styled_choice = StyleParser.parse(f"[{self.selected_style}]{choice}[/]")
            else:
                styled_choice = choice

            content_lines.append(" " + prefix + styled_choice)

        actual_max_width = max(get_visible_length(line) for line in content_lines) if content_lines else 0
        raw_box_width = actual_max_width + 4
        raw_box_width = max(raw_box_width, 20)

        if self.position_render == "left":
            position_offset = 0
        elif self.position_render == "center":
            position_offset = max(0, (term_cols - raw_box_width) // 2)
        elif self.position_render == "right":
            position_offset = max(0, term_cols - raw_box_width)
        else:
            position_offset = 0

        # Truncate the header so it can't ghost past the right edge when scrolling.
        message_max_width = term_cols - position_offset if term_cols > position_offset else term_cols
        if get_visible_length(styled_message) > message_max_width:
            available = max(0, message_max_width - 4)
            if available > 0:
                truncated = truncate_ansi_content(styled_message, available)
                styled_message = truncated + " .."

        available_for_box = term_cols - position_offset
        box_total_width = min(raw_box_width, available_for_box)

        max_content_width = max(0, box_total_width - 4)

        for i in range(len(content_lines)):
            if get_visible_length(content_lines[i]) > max_content_width:
                content_lines[i] = truncate_ansi_content(content_lines[i], max_content_width)

        self._border_renderer._position_offset = position_offset

        self._border_renderer.draw_box(
            content_lines=content_lines,
            selected_idx=self.selected_idx,
            scroll_offset=self.scroll_offset,
            max_visible=self.max_visible,
            header_lines=[styled_message],
            box_width=box_total_width,
        )

    def _draw_without_border(self) -> None:
        import shutil
        term_cols, _ = shutil.get_terminal_size()

        message_line = f"{self.qmark} {self.message}"
        message_visible_len = get_visible_length(message_line)
        message_offset = self._get_position_offset(message_visible_len, term_cols)

        styled_qmark = StyleParser.parse(f"[{self.qmark_style}]{self.qmark}[/]")
        styled_message = f"{' ' * message_offset}{styled_qmark} {self.message}"

        pointer_visible_len = get_visible_length(self.pointer)
        amark_visible_len = get_visible_length(self.amark) if self.multiselect else 0

        max_items = min(self.max_visible, len(self.choices))
        visible_slice = self.choices[self.scroll_offset:self.scroll_offset + max_items]

        content_lines = []
        for idx, choice in enumerate(visible_slice):
            actual_idx = self.scroll_offset + idx

            if self.multiselect:
                if actual_idx in self.selected_indices:
                    if actual_idx == self.selected_idx:
                        styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                        styled_amark = StyleParser.parse(f"[{self.amark_style}]{self.amark}[/]")
                        prefix = styled_pointer + " " + styled_amark + " "
                    else:
                        cursor_spaces = " " * pointer_visible_len
                        styled_amark = StyleParser.parse(f"[{self.amark_style}]{self.amark}[/]")
                        prefix = cursor_spaces + " " + styled_amark + " "
                else:
                    if actual_idx == self.selected_idx:
                        mark_spaces = " " * amark_visible_len
                        styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                        prefix = styled_pointer + " " + mark_spaces + " "
                    else:
                        cursor_spaces = " " * pointer_visible_len
                        mark_spaces = " " * amark_visible_len
                        prefix = cursor_spaces + " " + mark_spaces + " "
            else:
                if actual_idx == self.selected_idx:
                    styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
                    prefix = styled_pointer + " "
                else:
                    prefix = "  "

            if actual_idx == self.selected_idx and self.selected_style:
                styled_choice = StyleParser.parse(f"[{self.selected_style}]{choice}[/]")
            else:
                styled_choice = choice

            content_lines.append(prefix + styled_choice)

        buf = _OutputBuffer()

        if self._border_renderer._prev_total_lines > 0:
            buf.write("\r")
            for i in range(self._border_renderer._prev_total_lines):
                buf.write("\033[2K")
                if i < self._border_renderer._prev_total_lines - 1:
                    buf.write("\033[1B")
            buf.write(f"\r\033[{self._border_renderer._prev_total_lines - 1}A")
        else:
            buf.write("\r\033[2K")

        choice_offset = self._get_position_offset(
            max(get_visible_length(line) for line in content_lines) if content_lines else 0,
            term_cols,
        )
        buf.write(f"{styled_message}\n")

        for line in content_lines:
            if choice_offset > 0:
                buf.write(" " * choice_offset)
            buf.write(f"{line}\n")

        buf.write(f"\033[{len(content_lines) + 1}A")

        self._border_renderer._prev_total_lines = len(content_lines) + 1
        self._border_renderer._prev_header_lines = 1
        self._border_renderer._box_state = None

        buf.flush()

    def _clear_dialog(self, visible_count: int) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25h")

        self._border_renderer.clear_rendered()

    def run(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        def _on_resize(signum, frame):
            self._resize_pending = True
            self._border_renderer.on_sigwinch()
        old_handler = signal.getsignal(signal.SIGWINCH)
        try:
            signal.signal(signal.SIGWINCH, _on_resize)
        except (OSError, ValueError):
            pass

        self._draw_dialog()

        try:
            while True:
                ch = self.input_handler.read_char()

                if self._resize_pending or self._border_renderer._resize_during_render:
                    self._resize_pending = False
                    self._border_renderer.handle_resize()
                    self._draw_dialog()
                    continue

                if ch == '\r' or ch == '\n':
                    if self.multiselect:
                        self._clear_dialog(0)

                        selected_items = [self.choices[idx] for idx in sorted(self.selected_indices)]

                        if not self.hidden_select:
                            if selected_items:
                                sys.stdout.write(f"{self.qmark} {self.message} ")
                                for i, item in enumerate(selected_items):
                                    if i > 0:
                                        sys.stdout.write(", ")
                                    sys.stdout.write(item)
                                sys.stdout.write("\n")
                            else:
                                sys.stdout.write(f"{self.qmark} {self.message} (No selection)\n")

                        if self.transformer:
                            return self.transformer(selected_items)
                        return selected_items
                    else:
                        selected_choice = self.choices[self.selected_idx]

                        self._clear_dialog(0)

                        if not self.hidden_select:
                            sys.stdout.write(f"{self.qmark} {self.message} {self.pointer} {selected_choice}\n")

                        if self.transformer:
                            return self.transformer(selected_choice)
                        return selected_choice

                elif ch == '\x1b[A':
                    if self.selected_idx > 0:
                        self.selected_idx -= 1
                        if self.selected_idx < self.scroll_offset:
                            self.scroll_offset = self.selected_idx
                        self._draw_dialog()

                elif ch == '\x1b[B':
                    if self.selected_idx < len(self.choices) - 1:
                        self.selected_idx += 1
                        if self.selected_idx >= self.scroll_offset + self.max_visible:
                            self.scroll_offset = self.selected_idx - self.max_visible + 1
                        self._draw_dialog()

                elif ch == ' ' or ch == '\t':
                    if self.multiselect:
                        if self.selected_idx in self.selected_indices:
                            self.selected_indices.remove(self.selected_idx)
                        else:
                            self.selected_indices.add(self.selected_idx)
                        self._draw_dialog()

                elif ch == '\x03':
                    self._clear_dialog(0)

                    print("^C")
                    raise KeyboardInterrupt
        finally:
            try:
                signal.signal(signal.SIGWINCH, old_handler)
            except (OSError, ValueError):
                pass

    async def run_async(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        self._draw_dialog()

        try:
            while True:
                ch = await asyncio.to_thread(self.input_handler.read_char)

                if ch == '\r' or ch == '\n':
                    if self.multiselect:
                        visible_count = min(self.max_visible, len(self.choices))
                        self._clear_dialog(visible_count)
                        if self.border:
                            lines_to_clear = visible_count + 3
                        else:
                            lines_to_clear = visible_count + 1
                        sys.stdout.write(f"\033[{lines_to_clear - 1}A")

                        selected_items = [self.choices[idx] for idx in sorted(self.selected_indices)]
                        if not self.hidden_select:
                            if selected_items:
                                sys.stdout.write(f"{self.qmark} {self.message} ")
                                for i, item in enumerate(selected_items):
                                    if i > 0:
                                        sys.stdout.write(", ")
                                    sys.stdout.write(item)
                                sys.stdout.write("\n")
                            else:
                                sys.stdout.write(f"{self.qmark} {self.message} (No selection)\n")

                        if self.transformer:
                            return self.transformer(selected_items)
                        return selected_items
                    else:
                        selected_choice = self.choices[self.selected_idx]
                        visible_count = min(self.max_visible, len(self.choices))
                        self._clear_dialog(visible_count)
                        if self.border:
                            lines_to_clear = visible_count + 3
                        else:
                            lines_to_clear = visible_count + 1
                        sys.stdout.write(f"\033[{lines_to_clear - 1}A")

                        if not self.hidden_select:
                            sys.stdout.write(f"{self.qmark} {self.message} {self.pointer} {selected_choice}\n")

                        if self.transformer:
                            return self.transformer(selected_choice)
                        return selected_choice

                elif ch == '\x1b[A':
                    if self.selected_idx > 0:
                        self.selected_idx -= 1
                        if self.selected_idx < self.scroll_offset:
                            self.scroll_offset = self.selected_idx
                        self._draw_dialog()

                elif ch == '\x1b[B':
                    if self.selected_idx < len(self.choices) - 1:
                        self.selected_idx += 1
                        if self.selected_idx >= self.scroll_offset + self.max_visible:
                            self.scroll_offset = self.selected_idx - self.max_visible + 1
                        self._draw_dialog()

                elif ch == ' ' or ch == '\t':
                    if self.multiselect:
                        if self.selected_idx in self.selected_indices:
                            self.selected_indices.remove(self.selected_idx)
                        else:
                            self.selected_indices.add(self.selected_idx)
                        self._draw_dialog()

                elif ch == '\x03':
                    visible_count = min(self.max_visible, len(self.choices))
                    self._clear_dialog(visible_count)
                    if self.border:
                        lines_to_clear = visible_count + 3
                    else:
                        lines_to_clear = visible_count + 1
                    sys.stdout.write(f"\033[{lines_to_clear - 1}A")
                    print("^C")
                    raise KeyboardInterrupt

        except asyncio.CancelledError:
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\n\033[J")
            sys.stdout.flush()
            raise

    def _run_fallback(self) -> Any:
        while True:
            try:
                print(f"? {self.message}")
                for i, choice in enumerate(self.choices):
                    marker = ""
                    if self.multiselect and i in self.selected_indices:
                        marker = " [x]"
                    elif not self.multiselect and i == self.selected_idx:
                        marker = " >"
                    print(f"  {i + 1}. {choice}{marker}")

                if self.multiselect:
                    prompt_text = "Enter numbers (comma-separated) or 'done': "
                    response = input(prompt_text).strip()
                    if response.lower() == "done":
                        selected_items = [self.choices[idx] for idx in sorted(self.selected_indices)]
                        if self.transformer:
                            return self.transformer(selected_items)
                        return selected_items
                    try:
                        for num_str in response.split(","):
                            num = int(num_str.strip()) - 1
                            if 0 <= num < len(self.choices):
                                if num in self.selected_indices:
                                    self.selected_indices.remove(num)
                                else:
                                    self.selected_indices.add(num)
                    except ValueError:
                        pass
                    continue
                else:
                    prompt_text = f"Enter number (1-{len(self.choices)}): "
                    response = input(prompt_text).strip()
                    try:
                        num = int(response) - 1
                        if 0 <= num < len(self.choices):
                            selected_choice = self.choices[num]
                            if self.transformer:
                                return self.transformer(selected_choice)
                            return selected_choice
                    except ValueError:
                        pass
                    continue

            except EOFError as exc:
                raise KeyboardInterrupt from exc


def select(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
    cursor: str = "►",
    transformer: Optional[Callable[[Any], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    max_visible: int = 10,
    multiselect: bool = False,
    show_cursor: bool = True,
    pointer: str = "►",
    qmark: str = "?",
    amark: str = "x",
    hidden_select: bool = False,
    position_render: str = "left",
    pointer_style: str = "bold green",
    amark_style: str = "bold green",
    qmark_style: str = "bold",
    selected_style: str = "bold"
) -> Select:
    """Create a Select dialog for choosing from a list of options.

    Args:
        message: The question/message to display.
        choices: List of options to choose from.
        default: Default selected option (value from ``choices``). Default: ``None``.
        cursor: Cursor character for the selected item (default: ``'►'``).
        transformer: Function to transform the result before returning.
        border: Whether to draw a border around the dialog (default: ``True``).
        box_style: Box style if ``border`` is ``True`` — ``'rounded'`` (default),
            ``'square'``, ``'ascii'``, ``'double'``, or ``'heavy'``.
        max_visible: Maximum number of visible items at once (default: ``10``).
        multiselect: Enable multi-select mode where SPACE/TAB toggles
            selection and ENTER submits (default: ``False``).
        show_cursor: Show terminal cursor (default: ``True``).
        pointer: Custom cursor character (default: ``'►'``).
        qmark: Custom question mark character (default: ``'?'``).
        amark: Mark character for selected items in multi-select mode
            (default: ``'x'``).
        hidden_select: Hide the result summary line after selection
            (default: ``False``).
        position_render: Horizontal position of dialog — ``'left'`` (default),
            ``'center'``, or ``'right'``.
        pointer_style: Style for the pointer (default: ``'bold green'``).
        amark_style: Style for the mark in multi-select (default: ``'bold green'``).
        qmark_style: Style for the question mark (default: ``'bold'``).
        selected_style: Style for the selected item text (default: ``'bold'``).

    Returns:
        :class:`Select` dialog instance. Call ``.run()`` (sync) or
        ``.run_async()`` (async) to execute. In single-select mode returns
        the chosen string; in multi-select mode returns a ``list[str]`` of
        chosen items.

    Examples:
        >>> choice = select("Choose a framework:", ["React", "Vue", "Angular"]).run()
        >>> choice = select("Choose:", ["A", "B", "C"], border=False).run()
        >>> choice = select("Pick one:", ["X", "Y", "Z"], default="X").run()
        >>> picks = select("Select items:", ["A", "B", "C"], multiselect=True).run()
        >>> choice = select("Choose:", ["A", "B", "C"], position_render="center").run()
        >>> choice = select("Choose:", ["A", "B", "C"], pointer_style="bold red").run()

    Note:
        In multi-select mode, use SPACE or TAB to toggle selection and
        ENTER to submit.
    """
    return Select(
        message=message,
        choices=choices,
        default=default,
        cursor=cursor,
        transformer=transformer,
        border=border,
        box_style=box_style,
        max_visible=max_visible,
        multiselect=multiselect,
        show_cursor=show_cursor,
        pointer=pointer,
        qmark=qmark,
        amark=amark,
        hidden_select=hidden_select,
        position_render=position_render,
        pointer_style=pointer_style,
        amark_style=amark_style,
        qmark_style=qmark_style,
        selected_style=selected_style
    )


class Checkbox:

    def __init__(
        self,
        message: str,
        choices: list,
        default: Optional[list] = None,
        checkbox_unchecked: str = "○",
        checkbox_checked: str = "◉",
        transformer: Optional[Callable[[list], Any]] = None,
        border: bool = True,
        box_style: str = "rounded",
        border_color: str = "",
        max_visible: int = 10,
        show_cursor: bool = True,
        pointer: str = "►",
        qmark: str = "?",
        hidden_select: bool = False,
        position_render: str = "left",
        pointer_style: str = "bold green",
        checkbox_unchecked_style: str = "",
        checkbox_checked_style: str = "bold green",
        qmark_style: str = "bold",
        selected_style: str = "bold",
        name_max_width: int = 20,
        desc_style: str = "dim",
        separator: str = "│"
    ):
        self.message = message
        self.choices = choices
        self.default = default or []
        self.checkbox_unchecked = checkbox_unchecked
        self.checkbox_checked = checkbox_checked
        self.pointer = pointer
        self.transformer = transformer
        self.border = border
        self.box_style = box_style
        self.border_color = border_color
        self.max_visible = max_visible
        self.show_cursor = show_cursor
        self.qmark = qmark
        self.hidden_select = hidden_select
        self.position_render = position_render
        self.pointer_style = pointer_style
        self.checkbox_unchecked_style = checkbox_unchecked_style
        self.checkbox_checked_style = checkbox_checked_style
        self.qmark_style = qmark_style
        self.selected_style = selected_style
        self.name_max_width = name_max_width
        self.desc_style = desc_style
        self.separator = separator

        self._two_column = any(isinstance(c, tuple) for c in choices)

        self._names: list[str] = []
        for c in choices:
            if isinstance(c, tuple):
                self._names.append(c[0])
            else:
                self._names.append(str(c))

        self.input_handler = InputHandler()
        self.box_chars = BoxChars.for_style(box_style)

        self._border_renderer = BorderRenderer(box_style=box_style, border_color=border_color)

        self.selected_idx = 0
        self.scroll_offset = 0

        self._resize_pending = False

        self.checked_indices: set[int] = set()
        for item in self.default:
            if item in self._names:
                self.checked_indices.add(self._names.index(item))

        self._box_width: int = 60
        self._name_col_width: int = name_max_width
        self._desc_col_width: int = 30

    def _get_item(self, idx: int):
        return self.choices[idx]

    def _get_name(self, idx: int) -> str:
        return self._names[idx]

    def _get_desc(self, idx: int) -> str:
        item = self._get_item(idx)
        if isinstance(item, tuple) and len(item) > 1:
            return item[1]
        return ""

    def _format_line(self, idx: int) -> str:
        is_selected = idx == self.selected_idx
        is_checked = idx in self.checked_indices
        item = self._get_item(idx)

        if is_selected:
            styled_pointer = StyleParser.parse(f"[{self.pointer_style}]{self.pointer}[/]")
            prefix = styled_pointer + " "
        else:
            prefix = " " * (get_visible_length(self.pointer) + 1)

        if is_checked:
            checkbox_style = self.checkbox_checked_style
            checkbox_char = self.checkbox_checked
        else:
            checkbox_style = self.checkbox_unchecked_style
            checkbox_char = self.checkbox_unchecked

        if checkbox_style:
            styled_checkbox = StyleParser.parse(f"[{checkbox_style}]{checkbox_char}[/]")
        else:
            styled_checkbox = checkbox_char

        prefix = prefix + styled_checkbox + " "

        if self._two_column:
            name = self._get_name(idx)
            desc = self._get_desc(idx)

            max_name = self._name_col_width
            name_len = get_visible_length(name)
            if name_len > max_name:
                name = truncate_ansi_content(name, max_name - 2) + ".."
                name_len = max_name

            max_desc = self._desc_col_width
            desc_len = get_visible_length(desc)
            if desc_len > max_desc:
                desc = truncate_ansi_content(desc, max_desc - 2) + ".."
                desc_len = max_desc

            name_padding = max_name - name_len
            padded_name = name + " " * name_padding

            desc_padding = max_desc - desc_len

            if is_selected and self.selected_style:
                styled_name = StyleParser.parse(f"[{self.selected_style}]{padded_name}[/]")
            else:
                styled_name = padded_name

            if self.desc_style:
                styled_desc = StyleParser.parse(f"[{self.desc_style}]{desc}[/]")
            else:
                styled_desc = desc

            styled_desc = styled_desc + " " * desc_padding

            sep = f" {self.separator} "
            return prefix + styled_name + sep + styled_desc
        else:
            content = str(item)
            if is_selected and self.selected_style:
                styled_content = StyleParser.parse(f"[{self.selected_style}]{content}[/]")
            else:
                styled_content = content

            return prefix + styled_content

    def _calc_desc_width(self, box_width: int) -> int:
        prefix_len = get_visible_length(self.pointer) + 1 + get_visible_length(self.checkbox_checked) + 1
        sep_len = 1 + get_visible_length(self.separator) + 1
        name_len = self.name_max_width

        desc_width = max(10, box_width - prefix_len - name_len - sep_len - 1)
        return desc_width

    def _get_position_offset(self, content_width: int, term_width: int) -> int:
        if self.position_render == "left":
            return 0
        elif self.position_render == "center":
            return max(0, (term_width - content_width) // 2)
        elif self.position_render == "right":
            return max(0, term_width - content_width)
        else:
            return 0

    def _draw_dialog(self) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25l")

        if self.border:
            self._draw_with_border()
        else:
            self._draw_without_border()

    def _draw_with_border(self) -> None:
        import shutil
        term_cols, _ = shutil.get_terminal_size()

        styled_qmark = StyleParser.parse(f"[{self.qmark_style}]{self.qmark}[/]")
        styled_message = f"{styled_qmark} {self.message}"

        message_width = get_visible_length(styled_message)
        if self.position_render == "left":
            position_offset = 0
        elif self.position_render == "center":
            position_offset = max(0, (term_cols - message_width) // 2)
        elif self.position_render == "right":
            position_offset = max(0, term_cols - message_width)
        else:
            position_offset = 0

        message_max_width = term_cols - position_offset if term_cols > position_offset else term_cols
        if get_visible_length(styled_message) > message_max_width:
            available = max(0, message_max_width - 4)
            if available > 0:
                truncated = truncate_ansi_content(styled_message, available)
                styled_message = truncated + " .."

        available_for_box = term_cols - position_offset
        max_content_width = max(0, available_for_box - 4)

        if self._two_column:
            prefix_len = get_visible_length(self.pointer) + 1 + get_visible_length(self.checkbox_checked) + 1
            sep_len = 1 + get_visible_length(self.separator) + 1

            name_col = min(self.name_max_width, max_content_width // 2)
            name_col = max(10, name_col)

            desc_col = max(10, max_content_width - prefix_len - name_col - sep_len - 1)
            desc_col = max(10, desc_col)

            self._name_col_width = name_col
            self._desc_col_width = desc_col

        content_lines = []
        for idx in range(len(self.choices)):
            content_lines.append(self._format_line(idx))

        if content_lines:
            actual_max_width = max(get_visible_length(line) for line in content_lines) if content_lines else 0
            raw_box_width = actual_max_width + 4
            raw_box_width = max(raw_box_width, 20)
        else:
            raw_box_width = 20

        box_total_width = min(raw_box_width, available_for_box)

        self._border_renderer._position_offset = position_offset

        self._border_renderer.draw_box(
            content_lines=content_lines,
            selected_idx=self.selected_idx,
            scroll_offset=self.scroll_offset,
            max_visible=self.max_visible,
            header_lines=[styled_message],
            box_width=box_total_width,
        )

    def _draw_without_border(self) -> None:
        import shutil
        term_cols, _ = shutil.get_terminal_size()

        styled_qmark = StyleParser.parse(f"[{self.qmark_style}]{self.qmark}[/]")
        message_visible_len = get_visible_length(f"{self.qmark} {self.message}")
        message_offset = self._get_position_offset(message_visible_len, term_cols)
        styled_message = f"{' ' * message_offset}{styled_qmark} {self.message}"

        max_items = min(self.max_visible, len(self.choices))
        content_lines = []
        for i in range(max_items):
            actual_idx = self.scroll_offset + i
            content_lines.append(self._format_line(actual_idx))

        buf = _OutputBuffer()

        if self._border_renderer._prev_total_lines > 0:
            buf.write("\r")
            for i in range(self._border_renderer._prev_total_lines):
                buf.write("\033[2K")
                if i < self._border_renderer._prev_total_lines - 1:
                    buf.write("\033[1B")
            buf.write(f"\r\033[{self._border_renderer._prev_total_lines - 1}A")
        else:
            buf.write("\r\033[2K")

        choice_offset = self._get_position_offset(
            max(get_visible_length(line) for line in content_lines) if content_lines else 0,
            term_cols,
        )
        buf.write(f"{styled_message}\n")

        for line in content_lines:
            if choice_offset > 0:
                buf.write(" " * choice_offset)
            buf.write(f"{line}\n")

        buf.write(f"\033[{len(content_lines) + 1}A")

        self._border_renderer._prev_total_lines = len(content_lines) + 1
        self._border_renderer._prev_header_lines = 1
        self._border_renderer._box_state = None

        buf.flush()

    def _clear_dialog(self, visible_count: int = 0) -> None:
        if not self.show_cursor:
            sys.stdout.write("\033[?25h")

        self._border_renderer.clear_rendered()

    def run(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        def _on_resize(signum, frame):
            self._resize_pending = True
            self._border_renderer.on_sigwinch()

        old_handler = signal.getsignal(signal.SIGWINCH)
        try:
            signal.signal(signal.SIGWINCH, _on_resize)
        except (OSError, ValueError):
            pass

        self._draw_dialog()

        try:
            while True:
                ch = self.input_handler.read_char()

                if self._resize_pending or self._border_renderer._resize_during_render:
                    self._resize_pending = False
                    self._border_renderer.handle_resize()
                    self._draw_dialog()
                    continue

                if ch == '\r' or ch == '\n':
                    self._clear_dialog()

                    checked_items = [self._get_name(idx) for idx in sorted(self.checked_indices)]

                    if not self.hidden_select:
                        if checked_items:
                            sys.stdout.write(f"{self.qmark} {self.message} ")
                            for i, item in enumerate(checked_items):
                                if i > 0:
                                    sys.stdout.write(", ")
                                sys.stdout.write(item)
                            sys.stdout.write("\n")
                        else:
                            sys.stdout.write(f"{self.qmark} {self.message} (No selection)\n")

                    if self.transformer:
                        return self.transformer(checked_items)
                    return checked_items

                elif ch == '\x1b[A':
                    if self.selected_idx > 0:
                        self.selected_idx -= 1
                        if self.selected_idx < self.scroll_offset:
                            self.scroll_offset = self.selected_idx
                        self._draw_dialog()

                elif ch == '\x1b[B':
                    if self.selected_idx < len(self.choices) - 1:
                        self.selected_idx += 1
                        if self.selected_idx >= self.scroll_offset + self.max_visible:
                            self.scroll_offset = self.selected_idx - self.max_visible + 1
                        self._draw_dialog()

                elif ch == '\t':
                    if self.selected_idx in self.checked_indices:
                        self.checked_indices.remove(self.selected_idx)
                    else:
                        self.checked_indices.add(self.selected_idx)
                    self._draw_dialog()

                elif ch == '\x03':
                    self._clear_dialog()
                    print("^C")
                    raise KeyboardInterrupt
        finally:
            try:
                signal.signal(signal.SIGWINCH, old_handler)
            except (OSError, ValueError):
                pass

    async def run_async(self) -> Any:
        caps = get_capabilities()
        if not caps.supports_cursor_movement or not caps.is_tty_in:
            return self._run_fallback()

        self._draw_dialog()

        try:
            while True:
                ch = await asyncio.to_thread(self.input_handler.read_char)

                if ch == '\r' or ch == '\n':
                    visible_count = min(self.max_visible, len(self.choices))
                    self._clear_dialog(visible_count)
                    if self.border:
                        lines_to_clear = visible_count + 3
                    else:
                        lines_to_clear = visible_count + 1
                    sys.stdout.write(f"\033[{lines_to_clear - 1}A")

                    checked_items = [self._get_name(idx) for idx in sorted(self.checked_indices)]
                    if not self.hidden_select:
                        if checked_items:
                            sys.stdout.write(f"{self.qmark} {self.message} ")
                            for i, item in enumerate(checked_items):
                                if i > 0:
                                    sys.stdout.write(", ")
                                sys.stdout.write(item)
                            sys.stdout.write("\n")
                        else:
                            sys.stdout.write(f"{self.qmark} {self.message} (No selection)\n")

                    if self.transformer:
                        return self.transformer(checked_items)
                    return checked_items

                elif ch == '\x1b[A':
                    if self.selected_idx > 0:
                        self.selected_idx -= 1
                        if self.selected_idx < self.scroll_offset:
                            self.scroll_offset = self.selected_idx
                        self._draw_dialog()

                elif ch == '\x1b[B':
                    if self.selected_idx < len(self.choices) - 1:
                        self.selected_idx += 1
                        if self.selected_idx >= self.scroll_offset + self.max_visible:
                            self.scroll_offset = self.selected_idx - self.max_visible + 1
                        self._draw_dialog()

                elif ch == '\t':
                    if self.selected_idx in self.checked_indices:
                        self.checked_indices.remove(self.selected_idx)
                    else:
                        self.checked_indices.add(self.selected_idx)
                    self._draw_dialog()

                elif ch == '\x03':
                    visible_count = min(self.max_visible, len(self.choices))
                    self._clear_dialog(visible_count)
                    if self.border:
                        lines_to_clear = visible_count + 3
                    else:
                        lines_to_clear = visible_count + 1
                    sys.stdout.write(f"\033[{lines_to_clear - 1}A")
                    print("^C")
                    raise KeyboardInterrupt

        except asyncio.CancelledError:
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\n\033[J")
            sys.stdout.flush()
            raise

    def _run_fallback(self) -> Any:
        while True:
            try:
                print(f"? {self.message}")
                for i, choice in enumerate(self.choices):
                    mark = self.checkbox_checked if i in self.checked_indices else self.checkbox_unchecked
                    pointer = ">" if i == self.selected_idx else " "
                    display_name = self._get_name(i)
                    if self._two_column:
                        desc = self._get_desc(i)
                        print(f"  {pointer} {mark} {display_name}  {desc}")
                    else:
                        print(f"  {pointer} {mark} {display_name}")

                prompt_text = "Enter numbers (comma-separated) or 'done': "
                response = input(prompt_text).strip()

                if response.lower() == "done":
                    checked_items = [self._get_name(idx) for idx in sorted(self.checked_indices)]
                    if self.transformer:
                        return self.transformer(checked_items)
                    return checked_items

                try:
                    for num_str in response.split(","):
                        num = int(num_str.strip()) - 1
                        if 0 <= num < len(self.choices):
                            if num in self.checked_indices:
                                self.checked_indices.remove(num)
                            else:
                                self.checked_indices.add(num)
                except ValueError:
                    pass
                continue

            except EOFError as exc:
                raise KeyboardInterrupt from exc


def checkbox(
    message: str,
    choices: list,
    default: Optional[list] = None,
    checkbox_unchecked: str = "○",
    checkbox_checked: str = "◉",
    transformer: Optional[Callable[[list], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    border_color: str = "",
    max_visible: int = 10,
    show_cursor: bool = True,
    pointer: str = "►",
    qmark: str = "?",
    hidden_select: bool = False,
    position_render: str = "left",
    pointer_style: str = "bold green",
    checkbox_unchecked_style: str = "",
    checkbox_checked_style: str = "bold green",
    qmark_style: str = "bold",
    selected_style: str = "bold",
    name_max_width: int = 20,
    desc_style: str = "dim",
    separator: str = "│"
) -> Checkbox:
    """Create a Checkbox dialog for multi-selecting items.

    Args:
        message: The question/message to display.
        choices: List of options — plain strings or ``(name, description)``
            tuples. Tuples enable a two-column layout with descriptions.
        default: List of default-checked option names (values from ``choices``).
        checkbox_unchecked: Character for unchecked checkbox (default: ``'○'``).
        checkbox_checked: Character for checked checkbox (default: ``'◉'``).
        transformer: Function to transform the ``list`` result before returning.
        border: Whether to draw a border around the dialog (default: ``True``).
        box_style: Box style if ``border`` is ``True`` — ``'rounded'`` (default),
            ``'square'``, ``'ascii'``, ``'double'``, or ``'heavy'``.
        border_color: ANSI color for border lines, e.g. ``'\\033[36m'`` for
            cyan (default: ``''``).
        max_visible: Maximum number of visible items at once (default: ``10``).
        show_cursor: Show terminal cursor (default: ``True``).
        pointer: Custom cursor character (default: ``'►'``).
        qmark: Custom question mark character (default: ``'?'``).
        hidden_select: Hide the result summary line after selection
            (default: ``False``).
        position_render: Horizontal position of dialog — ``'left'`` (default),
            ``'center'``, or ``'right'``.
        pointer_style: Style for the pointer (default: ``'bold green'``).
        checkbox_unchecked_style: Style for unchecked checkbox (default: ``''``).
        checkbox_checked_style: Style for checked checkbox (default: ``'bold green'``).
        qmark_style: Style for the question mark (default: ``'bold'``).
        selected_style: Style for the selected item text (default: ``'bold'``).
        name_max_width: Max width for the name column in two-column mode
            (default: ``20``).
        desc_style: Style for description text (default: ``'dim'``).
        separator: Column separator character (default: ``'│'``).

    Returns:
        :class:`Checkbox` dialog instance. Call ``.run()`` (sync) or
        ``.run_async()`` (async) to execute. Returns a ``list[str]`` of
        checked item names.

    Examples:
        >>> picks = checkbox("Choose frameworks:", ["React", "Vue", "Angular"]).run()
        >>> picks = checkbox("Choose:", ["A", "B", "C"], default=["A", "C"]).run()
        >>> picks = checkbox("Select:", ["X", "Y", "Z"], border=False).run()
        >>> picks = checkbox("Pick:", ["A", "B", "C"], position_render="center").run()
        >>> picks = checkbox("Choose:", ["A", "B", "C"], pointer_style="bold red").run()
        >>> # Two-column layout with descriptions:
        >>> picks = checkbox("Select tools:", [
        ...     ("wget", "download files"),
        ...     ("curl", "transfer data"),
        ... ]).run()

    Note:
        Use TAB to toggle checkbox selection, ENTER to submit.
    """
    return Checkbox(
        message=message,
        choices=choices,
        default=default,
        checkbox_unchecked=checkbox_unchecked,
        checkbox_checked=checkbox_checked,
        transformer=transformer,
        border=border,
        box_style=box_style,
        border_color=border_color,
        max_visible=max_visible,
        show_cursor=show_cursor,
        pointer=pointer,
        qmark=qmark,
        hidden_select=hidden_select,
        position_render=position_render,
        pointer_style=pointer_style,
        checkbox_unchecked_style=checkbox_unchecked_style,
        checkbox_checked_style=checkbox_checked_style,
        qmark_style=qmark_style,
        selected_style=selected_style,
        name_max_width=name_max_width,
        desc_style=desc_style,
        separator=separator
    )


async def aconfirm(
    message: str,
    default: bool = True,
    confirm_letter: str = "y",
    reject_letter: str = "n",
    transformer: Optional[Callable[[bool], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    show_cursor: bool = True,
    qmark_style: str = "bold",
    confirm_style: str = "bold green",
    reject_style: str = "bold red"
) -> Any:
    """Async version of :func:`confirm` — awaitable coroutine.

    Creates and immediately runs a :class:`Confirm` dialog via
    :meth:`Confirm.run_async`, allowing other async tasks to progress while
    waiting for user input. All arguments mirror :func:`confirm` — see its
    docstring for full details.

    Args:
        message: The question/message to display.
        default: Default value (``True`` for Yes, ``False`` for No).
        confirm_letter: Letter for Yes confirmation (default: ``'y'``).
        reject_letter: Letter for No confirmation (default: ``'n'``).
        transformer: Function to transform the ``bool`` result.
        border: Whether to draw a border (default: ``True``).
        box_style: Box style if ``border`` is ``True``.
        show_cursor: Show terminal cursor (default: ``True``).
        qmark_style: Style for the question mark.
        confirm_style: Style for the confirm letter.
        reject_style: Style for the reject letter.

    Returns:
        The result (transformed if ``transformer`` is provided).

    Raises:
        KeyboardInterrupt: When Ctrl+C is pressed.
        asyncio.CancelledError: When the async task is cancelled.

    Example:
        >>> result = await aconfirm("Continue?", default=True)
    """
    return await Confirm(
        message=message,
        default=default,
        confirm_letter=confirm_letter,
        reject_letter=reject_letter,
        transformer=transformer,
        border=border,
        box_style=box_style,
        show_cursor=show_cursor,
        qmark_style=qmark_style,
        confirm_style=confirm_style,
        reject_style=reject_style,
    ).run_async()


async def aselect(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
    cursor: str = "►",
    transformer: Optional[Callable[[Any], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    max_visible: int = 10,
    multiselect: bool = False,
    show_cursor: bool = True,
    pointer: str = "►",
    qmark: str = "?",
    amark: str = "x",
    hidden_select: bool = False,
    position_render: str = "left",
    pointer_style: str = "bold green",
    amark_style: str = "bold green",
    qmark_style: str = "bold",
    selected_style: str = "bold"
) -> Any:
    """Async version of :func:`select` — awaitable coroutine.

    Creates and immediately runs a :class:`Select` dialog via
    :meth:`Select.run_async`, allowing other async tasks to progress while
    waiting for user input. All arguments mirror :func:`select` — see its
    docstring for full details.

    Args:
        message: The question/message to display.
        choices: List of options to choose from.
        default: Default selected option (value from ``choices``).
        cursor: Cursor character for the selected item.
        transformer: Function to transform the result.
        border: Whether to draw a border (default: ``True``).
        box_style: Box style if ``border`` is ``True``.
        max_visible: Maximum number of visible items (default: ``10``).
        multiselect: Enable multi-select mode (default: ``False``).
        show_cursor: Show terminal cursor (default: ``True``).
        pointer: Custom cursor character (default: ``'►'``).
        qmark: Custom question mark character (default: ``'?'``).
        amark: Mark for selected items in multi-select (default: ``'x'``).
        hidden_select: Hide the result summary line (default: ``False``).
        position_render: ``'left'``, ``'center'``, or ``'right'``.
        pointer_style: Style for the pointer.
        amark_style: Style for the mark in multi-select.
        qmark_style: Style for the question mark.
        selected_style: Style for the selected item text.

    Returns:
        Selected choice (single-select) or ``list[str]`` (multi-select),
        transformed if ``transformer`` is provided.

    Raises:
        KeyboardInterrupt: When Ctrl+C is pressed.
        asyncio.CancelledError: When the async task is cancelled.

    Example:
        >>> choice = await aselect("Choose:", ["A", "B", "C"])
    """
    return await Select(
        message=message,
        choices=choices,
        default=default,
        cursor=cursor,
        transformer=transformer,
        border=border,
        box_style=box_style,
        max_visible=max_visible,
        multiselect=multiselect,
        show_cursor=show_cursor,
        pointer=pointer,
        qmark=qmark,
        amark=amark,
        hidden_select=hidden_select,
        position_render=position_render,
        pointer_style=pointer_style,
        amark_style=amark_style,
        qmark_style=qmark_style,
        selected_style=selected_style,
    ).run_async()


async def acheckbox(
    message: str,
    choices: list,
    default: Optional[list] = None,
    checkbox_unchecked: str = "○",
    checkbox_checked: str = "◉",
    transformer: Optional[Callable[[list], Any]] = None,
    border: bool = True,
    box_style: str = "rounded",
    border_color: str = "",
    max_visible: int = 10,
    show_cursor: bool = True,
    pointer: str = "►",
    qmark: str = "?",
    hidden_select: bool = False,
    position_render: str = "left",
    pointer_style: str = "bold green",
    checkbox_unchecked_style: str = "",
    checkbox_checked_style: str = "bold green",
    qmark_style: str = "bold",
    selected_style: str = "bold",
    name_max_width: int = 20,
    desc_style: str = "dim",
    separator: str = "│"
) -> Any:
    """Async version of :func:`checkbox` — awaitable coroutine.

    Creates and immediately runs a :class:`Checkbox` dialog via
    :meth:`Checkbox.run_async`, allowing other async tasks to progress while
    waiting for user input. All arguments mirror :func:`checkbox` — see its
    docstring for full details.

    Args:
        message: The question/message to display.
        choices: List of options — plain strings or ``(name, description)``
            tuples (two-column layout).
        default: List of default-checked option names.
        checkbox_unchecked: Character for unchecked checkbox (default: ``'○'``).
        checkbox_checked: Character for checked checkbox (default: ``'◉'``).
        transformer: Function to transform the ``list`` result.
        border: Whether to draw a border (default: ``True``).
        box_style: Box style if ``border`` is ``True``.
        border_color: ANSI color for border lines.
        max_visible: Maximum number of visible items (default: ``10``).
        show_cursor: Show terminal cursor (default: ``True``).
        pointer: Custom cursor character (default: ``'►'``).
        qmark: Custom question mark character (default: ``'?'``).
        hidden_select: Hide the result summary line (default: ``False``).
        position_render: ``'left'``, ``'center'``, or ``'right'``.
        pointer_style: Style for the pointer.
        checkbox_unchecked_style: Style for unchecked checkbox.
        checkbox_checked_style: Style for checked checkbox.
        qmark_style: Style for the question mark.
        selected_style: Style for the selected item text.
        name_max_width: Max width for name column in two-column mode.
        desc_style: Style for description text.
        separator: Column separator character (default: ``'│'``).

    Returns:
        ``list[str]`` of checked item names, transformed if ``transformer``
        is provided.

    Raises:
        KeyboardInterrupt: When Ctrl+C is pressed.
        asyncio.CancelledError: When the async task is cancelled.

    Example:
        >>> picks = await acheckbox("Choose:", ["A", "B", "C"])
        >>> # Two-column with descriptions:
        >>> picks = await acheckbox("Select tools:", [
        ...     ("wget", "download"),
        ...     ("curl", "transfer"),
        ... ])

    Note:
        Use TAB to toggle checkbox selection, ENTER to submit.
    """
    return await Checkbox(
        message=message,
        choices=choices,
        default=default,
        checkbox_unchecked=checkbox_unchecked,
        checkbox_checked=checkbox_checked,
        transformer=transformer,
        border=border,
        box_style=box_style,
        border_color=border_color,
        max_visible=max_visible,
        show_cursor=show_cursor,
        pointer=pointer,
        qmark=qmark,
        hidden_select=hidden_select,
        position_render=position_render,
        pointer_style=pointer_style,
        checkbox_unchecked_style=checkbox_unchecked_style,
        checkbox_checked_style=checkbox_checked_style,
        qmark_style=qmark_style,
        selected_style=selected_style,
        name_max_width=name_max_width,
        desc_style=desc_style,
        separator=separator,
    ).run_async()
