#!/usr/bin/env python3
"""Styling helpers: inline [tags], the style() function, and color shortcuts.

PromptKit understands Rich-style ``[bold cyan]...[/]`` markup. StyleParser turns
it into ANSI, and the color helpers (red, green, on_blue, ...) wrap text directly.
No prompt loop here — this just prints styled text so you can see the output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import (  # noqa: E402
    StyleParser,
    style,
    bold,
    dim,
    italic,
    red,
    green,
    cyan,
    yellow,
    on_blue,
)

# 1. Rich-style markup parsed to ANSI.
print(StyleParser.parse("[bold #0a9382]Bold cyan[/] and [italic red]italic red[/] text"))
print(StyleParser.parse("[dim]dim[/] · [underline]underline[/] · [bold yellow on blue]badge[/]"))

# 2. The style() function: text + a style string.
print(style("styled via style()", "bold magenta"))

# 3. One-shot color/attribute helpers.
print(f"{bold('bold')} {dim('dim')} {italic('italic')}")
print(f"{red('red')} {green('green')} {cyan('cyan')} {yellow('yellow')} {on_blue('on_blue')}")

# 4. Visible length ignores the markup — useful for alignment/padding.
label = "[bold green]OK[/]"
print(f"\nvisible width of {label!r} = {StyleParser.get_visible_length(label)} (not {len(label)})")
