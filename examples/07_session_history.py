#!/usr/bin/env python3
"""PromptSession with file-backed history that survives across program runs.

A PromptSession reuses one Prompt + History, so state persists between calls.
Point it at a history file and entries are saved on submit and reloaded next run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import PromptSession  # noqa: E402

HISTORY_FILE = str(Path(__file__).parent / ".demo_history")

session = PromptSession(
    "sql> ",
    completions=["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE", "JOIN"],
    match_mode="prefix",
    history_file=HISTORY_FILE,
    prompt_style="bold magenta",
)

print(f"History file: {HISTORY_FILE}")
print("Enter a couple of queries (blank line to stop). Re-run to see them recalled with ↑.\n")

while True:
    try:
        query = session.prompt().strip()
    except (KeyboardInterrupt, EOFError):
        break
    if not query:
        break
    print(f"  stored: {query}")

print(f"\nSession history now holds {len(session.history.entries)} entries.")
