#!/usr/bin/env python3
"""Confirm prompt: yes/no questions with borders, custom keys, and transformers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import confirm  # noqa: E402

# Plain yes/no with a rounded border and styled answer letters.
result = confirm(
    message="Continue with the installation?",
    default=True,
    border=True,
    box_style="rounded",
    qmark_style="bold",
    confirm_style="bold green",
    reject_style="bold red",
).run()
print(f"\nResult: {result}")

# Custom accept/reject keys ('s' = yes, 'd' = no) instead of y/n.
print("\n--- Custom keys ---")
result = confirm(
    message="Do you want to save changes?",
    confirm_letter="s",
    reject_letter="d",
    border=True,
    box_style="rounded",
).run()
print(f"Save changes: {result}")

# A transformer turns the bool into the final line shown after answering.
print("\n--- With transformer ---")
result = confirm(
    message="Delete all files?",
    default=False,
    transformer=lambda x: "Files will be deleted!" if x else "Deletion cancelled.",
    border=True,
    box_style="rounded",
).run()
print(f"Result: {result}")
