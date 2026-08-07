#!/usr/bin/env python3
"""Right-aligned prompt (rprompt): ghost text pinned to the right edge.

The rprompt renders at the far right of the input line — handy for showing a
mode, a git branch, or a clock without cluttering the left prompt.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from promptkit import prompt, FormattedPrompt  # noqa: E402

CMDS = json.loads((ROOT / "examples" / "commands_desc.json").read_text())

custom_prompt = FormattedPrompt(
    prompt_prefix="❯ ",
    rprompt="[bold #832919]<<<( hello )[/]",
)

result = prompt(
    custom_prompt,
    completions=CMDS,
    match_mode="fuzzy",
    box_style="rounded",
)

print(f"\nResult: {result}")
