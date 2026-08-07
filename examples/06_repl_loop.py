#!/usr/bin/env python3
"""REPL loop: keep prompting until Ctrl+C, with persistent history and completion.

``prompt_loop`` is a generator that yields each submitted line. History persists
across iterations, so ↑/↓ recalls previous entries and autosuggest offers them
as ghost text.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import prompt_loop  # noqa: E402

COMMANDS = ["help", "status", "add", "commit", "push", "pull", "log", "quit"]

print("Mini REPL — type 'quit' or press Ctrl+C to exit.\n")

for line in prompt_loop(
    "repl> ",
    completions=COMMANDS,
    match_mode="fuzzy",
    prompt_style="bold cyan",
    autosuggest=True,
):
    line = line.strip()
    if line in ("quit", "exit"):
        break
    if line:
        print(f"  → executed: {line!r}")

print("\nBye!")
