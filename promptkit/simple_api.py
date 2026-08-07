"""Simple one-liner API around :class:`Prompt`, :class:`WordCompleter`, and :class:`History`.

Three flavors:

1. :func:`prompt` — one shot, returns a string.
2. :func:`prompt_loop` — generator yielding inputs until Ctrl+C.
3. :class:`PromptSession` — persistent state across calls.
"""

from __future__ import annotations

import asyncio
from typing import Any, Generator, Callable, Union

from .completion import Completer, WordCompleter, MatchMode
from .prompt import Prompt
from .history import History
from .formatted_prompt import FormattedPrompt, PromptSpec


def _build_completer(
    completions: list[str] | dict[str, str] | WordCompleter | Completer | None,
    match_mode: MatchMode = "prefix",
    ignore_case: bool = True,
) -> WordCompleter | Completer | None:
    """Coerce a user-friendly ``completions`` spec into a completer instance.

    ``list[str]`` → words, ``dict[str,str]`` → words + descriptions, existing
    completer instances are passed through, ``None`` means no completion.
    """
    if completions is None:
        return None
    if isinstance(completions, (WordCompleter, Completer)):
        return completions
    if isinstance(completions, dict):
        return WordCompleter(
            words=list(completions.keys()),
            meta_dict=completions,
            ignore_case=ignore_case,
            match_mode=match_mode,
        )
    if isinstance(completions, list):
        return WordCompleter(
            words=completions,
            ignore_case=ignore_case,
            match_mode=match_mode,
        )
    raise TypeError(
        f"completions must be list[str], dict[str,str], WordCompleter, "
        f"Completer, or None — got {type(completions).__name__}"
    )


def _build_history(
    history: History | list[str] | str | None,
) -> History:
    """Coerce a ``history`` spec into a :class:`History` (``str`` → filepath, ``list`` → seed)."""
    if isinstance(history, History):
        return history
    if isinstance(history, str):
        return History(filepath=history)
    if isinstance(history, list):
        return History(strings=history)
    return History()


def _reset_prompt(p: Prompt) -> None:
    """Clear ``p``'s input buffer and completion state for a fresh call."""
    p.input_buffer = ""
    p.cursor_pos = 0
    p.show_box = False
    p.selected_idx = 0
    p.scroll_offset = 0
    p._autosuggestion = None


def prompt(
    message: PromptSpec = ">>> ",
    completions: list[str] | dict[str, str] | WordCompleter | Completer | None = None,
    match_mode: MatchMode = "prefix",
    box_style: str = "rounded",
    history: History | list[str] | str | None = None,
    ignore_case: bool = True,
    highlighter: Any | None = None,
    autosuggest: bool = True,
    completion_style: dict[str, str] | None = None,
    suggestion_style: str | None = None,
    prompt_style: str | None = None,
    cursor_style: str | None = None,
) -> str:
    """Run a single interactive prompt and return the user's input.

    Args:
        message: Prompt string, :class:`FormattedPrompt`, or callable returning
            one. Plain strings may contain inline ``[style]`` tags
            (e.g. ``"[bold green]>>>[/] "``). Default: ``">>> "``.
        completions: Completion source. Accepts:

            - ``list[str]`` — plain word list
            - ``dict[str, str]`` — mapping of word → description
            - :class:`WordCompleter` / :class:`Completer` — pre-built instance
            - ``None`` — no completion popup

        match_mode: ``"prefix"`` (default) or ``"fuzzy"`` (fzf-style scoring).
        box_style: Completion popup border style — ``"rounded"`` (default),
            ``"square"``, ``"ascii"``, ``"double"``, or ``"heavy"``.
        history: History source. Accepts a :class:`History` instance, a seed
            ``list[str]``, a filepath (``str``) for persistent history, or
            ``None`` for an ephemeral in-memory history.
        ignore_case: Case-insensitive completion matching (default: ``True``).
        highlighter: Optional :class:`Highlighter` for syntax highlighting
            the input buffer (e.g. Pygments-backed).
        autosuggest: Enable Fish-style ghost autosuggestion drawn from
            history (press ``→`` / Right Arrow to accept). Default: ``True``.
        completion_style: Popup styling dict with keys ``"selected_bg"``
            (row highlight) and ``"border_color"`` (frame color). Accepts
            hex (``"#333333"``), named colors, or raw ANSI codes.
        suggestion_style: Style string for autosuggestion ghost text
            (e.g. ``"dim"``, ``"#808080"``, ``"38;5;245"``).
        prompt_style: Style applied to ``message`` when it has no inline
            ``[style]`` tags (e.g. ``"bold cyan"``).
        cursor_style: Cursor shape — ``"block"``, ``"underline"``, or
            ``"beam"`` / ``"line"``.

    Returns:
        The user's input string (with trailing newline stripped).

    Raises:
        KeyboardInterrupt: If the user presses Ctrl+C.

    Examples:
        >>> name = prompt("Name: ")
        >>> cmd = prompt(">>> ", completions=["run", "quit", "help"])
        >>> cmd = prompt(">>> ", completions={"git": "version control", "ls": "list"})
        >>> cmd = prompt(">>> ", completions=["react", "redux"], match_mode="fuzzy")
        >>> cmd = prompt(">>> ", history="~/.myapp_history")
        >>> cmd = prompt("[bold green]➜[/] ", prompt_style="bold")
    """
    completer = _build_completer(completions, match_mode=match_mode, ignore_case=ignore_case)
    hist = _build_history(history)

    if completer is None:
        completer = WordCompleter([], match_mode=match_mode, ignore_case=ignore_case)

    p = Prompt(
        completer,
        prompt=message,
        box_style=box_style,
        highlighter=highlighter,
        history=hist,
        autosuggest=autosuggest,
        completion_style=completion_style,
        suggestion_style=suggestion_style,
        prompt_style=prompt_style,
        cursor_style=cursor_style,
    )
    try:
        result = p.run()
        return result
    finally:
        _reset_prompt(p)


def prompt_loop(
    message: PromptSpec = ">>> ",
    completions: list[str] | dict[str, str] | WordCompleter | Completer | None = None,
    match_mode: MatchMode = "prefix",
    box_style: str = "rounded",
    history: History | list[str] | str | None = None,
    ignore_case: bool = True,
    highlighter: Any | None = None,
    autosuggest: bool = True,
    completion_style: dict[str, str] | None = None,
    suggestion_style: str | None = None,
    prompt_style: str | None = None,
    cursor_style: str | None = None,
) -> Generator[str, None, None]:
    """Yield inputs in a REPL loop; exits cleanly on Ctrl+C.

    State is auto-reset between iterations while history persists across
    the loop, making this ideal for interactive shells. All arguments
    mirror :func:`prompt` — see its docstring for full details.

    Args:
        message: Prompt string, :class:`FormattedPrompt`, or callable.
        completions: ``list[str]``, ``dict[str,str]``, completer instance,
            or ``None``.
        match_mode: ``"prefix"`` or ``"fuzzy"``.
        box_style: Completion popup border style.
        history: :class:`History`, list, filepath, or ``None``.
        ignore_case: Case-insensitive matching.
        highlighter: Optional syntax :class:`Highlighter`.
        autosuggest: Fish-style ghost suggestion from history.
        completion_style: Popup styling (``selected_bg``, ``border_color``).
        suggestion_style: Style for autosuggestion ghost text.
        prompt_style: Fallback style for ``message`` without inline tags.
        cursor_style: ``"block"``, ``"underline"``, ``"beam"``/``"line"``.

    Yields:
        Each user input string as it is entered.

    Examples:
        >>> for line in prompt_loop(">>> ", completions=["run", "quit"]):
        ...     if line == "quit":
        ...         break
        ...     print(f"Got: {line}")
    """
    completer = _build_completer(completions, match_mode=match_mode, ignore_case=ignore_case)
    hist = _build_history(history)

    if completer is None:
        completer = WordCompleter([], match_mode=match_mode, ignore_case=ignore_case)

    p = Prompt(
        completer,
        prompt=message,
        box_style=box_style,
        highlighter=highlighter,
        history=hist,
        autosuggest=autosuggest,
        completion_style=completion_style,
        suggestion_style=suggestion_style,
        prompt_style=prompt_style,
        cursor_style=cursor_style,
    )

    try:
        while True:
            result = p.run()
            yield result
            _reset_prompt(p)
    except KeyboardInterrupt:
        return


class PromptSession:
    """Persistent prompt session — history and completer state survive across calls.

    Unlike :func:`prompt` (which builds a fresh :class:`Prompt` each call),
    :class:`PromptSession` reuses a single :class:`Prompt` and :class:`History`
    pair, so command history accumulates naturally across ``.prompt()`` calls.
    Input buffer, completion popup, and autosuggestion state are auto-reset
    on each call.

    All constructor arguments mirror :func:`prompt` — see its docstring for
    full details. ``history_file`` is a convenience shortcut for
    ``history=<filepath>``.

    Args:
        message: Prompt string, :class:`FormattedPrompt`, or callable.
        completions: ``list[str]``, ``dict[str,str]``, completer instance,
            or ``None``.
        match_mode: ``"prefix"`` or ``"fuzzy"``.
        box_style: Completion popup border style.
        history: :class:`History`, list, filepath, or ``None``.
        history_file: Shortcut for ``history=<filepath>``; ignored if
            ``history`` is also provided.
        ignore_case: Case-insensitive matching.
        highlighter: Optional syntax :class:`Highlighter`.
        autosuggest: Fish-style ghost suggestion from history.
        completion_style: Popup styling (``selected_bg``, ``border_color``).
        suggestion_style: Style for autosuggestion ghost text.
        prompt_style: Fallback style for ``message`` without inline tags.
        cursor_style: ``"block"``, ``"underline"``, ``"beam"``/``"line"``.

    Examples:
        >>> session = PromptSession(">>> ", history_file="~/.myapp_history")
        >>> while True:
        ...     line = session.prompt()
        ...     if line == "quit":
        ...         break
        >>>
        >>> # Swap completions at runtime for context-sensitive completion:
        >>> session.set_completions(["file1.txt", "file2.txt"])
    """

    def __init__(
        self,
        message: PromptSpec = ">>> ",
        completions: list[str] | dict[str, str] | WordCompleter | Completer | None = None,
        match_mode: MatchMode = "prefix",
        box_style: str = "rounded",
        history: History | list[str] | str | None = None,
        history_file: str | None = None,
        ignore_case: bool = True,
        highlighter: Any | None = None,
        autosuggest: bool = True,
        completion_style: dict[str, str] | None = None,
        suggestion_style: str | None = None,
        prompt_style: str | None = None,
        cursor_style: str | None = None,
    ) -> None:
        self.message: PromptSpec = message
        self.match_mode: MatchMode = match_mode
        self.box_style: str = box_style
        self.ignore_case: bool = ignore_case
        self.autosuggest: bool = autosuggest
        self.completion_style: dict[str, str] | None = completion_style
        self.suggestion_style: str | None = suggestion_style
        self.prompt_style: str | None = prompt_style
        self.cursor_style: str | None = cursor_style

        if history_file is not None and history is None:
            hist = _build_history(history_file)
        else:
            hist = _build_history(history)

        completer = _build_completer(completions, match_mode=match_mode, ignore_case=ignore_case)
        if completer is None:
            completer = WordCompleter([], match_mode=match_mode, ignore_case=ignore_case)

        self._prompt: Prompt = Prompt(
            completer,
            prompt=message,
            box_style=box_style,
            highlighter=highlighter,
            history=hist,
            autosuggest=autosuggest,
            completion_style=completion_style,
            suggestion_style=suggestion_style,
            prompt_style=prompt_style,
            cursor_style=cursor_style,
        )
        self._history: History = hist

    @property
    def history(self) -> History:
        """The underlying :class:`History` instance."""
        return self._history

    @property
    def prompt_obj(self) -> Prompt:
        """The underlying :class:`Prompt` (for advanced use)."""
        return self._prompt

    def prompt(self) -> str:
        """Run one prompt turn and return the input; auto-resets on exit.

        Raises:
            KeyboardInterrupt: If the user presses Ctrl+C.
        """
        try:
            result = self._prompt.run()
            return result
        finally:
            _reset_prompt(self._prompt)

    async def prompt_async(self) -> str:
        """Async variant of :meth:`prompt`.

        Raises:
            KeyboardInterrupt: On Ctrl+C.
            asyncio.CancelledError: If the task is cancelled.
        """
        try:
            result = await self._prompt.run_async()
            return result
        finally:
            _reset_prompt(self._prompt)

    def loop(
        self,
        on_input: Callable[[str], None] | None = None,
    ) -> None:
        """REPL loop until Ctrl+C. ``on_input`` (if given) is called per input."""
        try:
            while True:
                result = self._prompt.run()
                if on_input is not None:
                    on_input(result)
                _reset_prompt(self._prompt)
        except KeyboardInterrupt:
            pass

    async def loop_async(
        self,
        on_input: Callable[[str], Any] | None = None,
    ) -> None:
        """Async REPL loop until Ctrl+C. Restores terminal state on cancellation."""
        try:
            while True:
                result = await self._prompt.run_async()
                if on_input is not None:
                    on_input(result)
                _reset_prompt(self._prompt)
        except KeyboardInterrupt:
            pass
        except asyncio.CancelledError:
            import sys
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\n\033[J")
            sys.stdout.flush()
            raise

    def set_completions(
        self,
        completions: list[str] | dict[str, str] | WordCompleter | Completer | None,
        match_mode: MatchMode | None = None,
    ) -> None:
        """Swap the completer at runtime for context-sensitive completions."""
        mode = match_mode or self.match_mode
        completer = _build_completer(completions, match_mode=mode, ignore_case=self.ignore_case)
        if completer is None:
            completer = WordCompleter([], match_mode=mode, ignore_case=self.ignore_case)
        self._prompt.completer = completer

    def __repr__(self) -> str:
        return (
            f"PromptSession(message={self.message!r}, "
            f"history={len(self._history)} entries)"
        )
