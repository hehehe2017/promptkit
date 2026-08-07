#!/usr/bin/env python3
"""Single-line prompt with fuzzy completion, autosuggest, and a styled info bar.

Type a few letters of any Unix command to see the fuzzy completion popup, then
press Enter to return the input.
"""
import json
import sys
from pathlib import Path

# Make the package importable when running from a checkout (not pip-installed).
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from promptkit import prompt, FormattedPrompt  # noqa: E402

CMDS = json.loads((ROOT / "examples" / "commands_desc.json").read_text())

custom_prompt = FormattedPrompt(
    info_line=(
        "╭─✓ [bold cyan]ngisync_agent-cli[/] [dim]51029c17[/] "
        "([bold green]0[/])msgs [bold yellow]0 paid[/] "
        "([dim]0 cached[/]) [bold red]$0.0000[/] ↓↑"
    ),
    prompt_prefix="╰─❯ ",
)

result = prompt(
        #custom_prompt,
    ">>> ",
    completions=CMDS,
    match_mode="fuzzy",
    box_style="rounded",
    autosuggest=True,
    completion_style={"selected_bg": "#333366", "border_color": "#555588"},
)

print(f"\nYou entered: {result}")
