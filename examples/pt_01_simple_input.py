#!/usr/bin/env python3
"""prompt_toolkit version of examples/01_simple_input.py for comparison.

A simple single-line prompt (not a full-screen TUI) with fuzzy completion and
autosuggest, mirroring promptkit's one-shot `prompt()` call in 01_simple_input.
"""
import json
from pathlib import Path
from typing import Iterable

# command -> description, loaded from the repo's example data.
ROOT = Path(__file__).parent.parent
CMDS = json.loads((ROOT / "examples" / "commands_desc.json").read_text())

from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion  # noqa: E402
from prompt_toolkit.completion import Completer, Completion  # noqa: E402
from prompt_toolkit.document import Document  # noqa: E402
from prompt_toolkit.shortcuts import prompt  # noqa: E402


def fuzzy_match(query: str, word: str) -> bool:
    """Subsequence match, like promptkit's fuzzy mode."""
    query, word = query.lower(), word.lower()
    it = iter(word)
    return all(any(c == q for c in it) for q in query)


class DictCompleter(Completer):
    """Fuzzy completion against {command: description}, two-column popup."""

    def get_completions(
        self, document: Document, complete_event: object
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        for word, desc in CMDS.items():
            if fuzzy_match(text, word):
                yield Completion(
                    word,
                    start_position=-len(text),
                    display_meta=desc,
                    style="fg:#333366",
                )


class CmdAutosuggest(AutoSuggest):
    """Ghost hint: first command that starts with the current text."""

    def get_suggestion(self, buffer: object, document: Document) -> Suggestion | None:
        text = document.text_before_cursor
        if not text:
            return None
        for word in CMDS:
            if word.lower().startswith(text.lower()):
                return Suggestion(word[len(text):])
        return None


if __name__ == "__main__":
    result = prompt(
        ">>> ",
        completer=DictCompleter(),
        complete_while_typing=True,
        auto_suggest=CmdAutosuggest(),
    )
    print(f"\nYou entered: {result}")