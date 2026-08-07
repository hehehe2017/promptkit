#!/usr/bin/env python3
"""Select prompt: single-choice menu, plus a two-column variant with descriptions.

Arrow keys move the cursor, Enter selects. Pass ``(name, description)`` tuples to
get an aligned two-column layout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import select   # noqa: E402

# Plain single-select menu.
color = select(
    message="Pick a favorite color:",
    choices=["red", "green", "blue", "magenta", "cyan"],
    default="blue",
    border=True,
    box_style="rounded",
    pointer_style="bold green",
).run()
print(f"\nYou picked: {color}")

# Two-column layout: (value, description) tuples render the description dimmed
# next to each choice.
print("\n--- Two-column select ---")
action = select(
    message="What would you like to do?",
    choices=[
        ("init", "Create a new project in the current directory"),
        ("build", "Compile the project and emit artifacts"),
        ("test", "Run the full test suite"),
        ("deploy", "Ship the latest build to production"),
    ],
    border=True,
    box_style="double",
    position_render="left",
).run()
print(f"\nAction: {action}")
