#!/usr/bin/env python3
"""Checkbox prompt: multi-select with pre-checked defaults and a scrolling viewport.

Use ↑/↓ to move, Space to toggle, Enter to confirm. The list scrolls when it has
more items than ``max_visible``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import Checkbox  # noqa: E402

tools = [
    "create_file",
    "create_snapshot",
    "crypto_price",
    "demo_binancetrade",
    "dns_record",
    "edit_file",
    "file_restore",
    "git",
    "glob",
    "grep",
    "list_backups",
    "list_snapshots",
    "read_file",
    "retrieve_session",
    "self_extend",
    "shell_tool",
    "subagent",
    "todo_write",
    "weather",
    "web_fetch",
    "web_fetch_async",
    "web_search",
]

default_checked = [
    "demo_binancetrade",
    "edit_file",
    "file_restore",
    "glob",
    "grep",
    "list_backups",
    "read_file",
    "retrieve_session",
    "self_extend",
    "shell_tool",
    "todo_write",
    "web_fetch",
    "web_search",
]

result = Checkbox(
    message="Selected tools: 13 items",
    choices=tools,
    default=default_checked,
    border=True,
    box_style="rounded",
    max_visible=10,
    checkbox_unchecked="○",
    checkbox_checked="◉",
    pointer="> ",
    selected_style="reverse",
    position_render="center",
).run()

print(f"\nYou selected {len(result)} tools:")
for item in result:
    print(f"  + {item}")
