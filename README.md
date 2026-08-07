# PromptKit

Modular terminal input for Python — completion, history, syntax highlighting, and
inquirer-style prompts (confirm / select / checkbox), sync **and** async.

Small, dependency-light, and built to feel native in a real TTY while degrading
gracefully to plain `input()` when stdin is a pipe.

```python
from promptkit import prompt, confirm, select, checkbox

cmd = prompt("cmd> ", completions=["git", "wget", "curl"])
ok  = confirm("Deploy now?", default=False)
env = select("Environment?", choices=["staging", "production"]).run()
tags = checkbox("Features?", choices=["metrics", "tracing", "cache"]).run()
```

## Features

- **Line editor** with cursor movement, kill/yank, word ops, and multi-line paste
- **Completion** — prefix / fuzzy matching, two-column menu with descriptions
- **History** — in-memory or file-backed, ↑/↓ recall, Fish-style ghost autosuggest
- **Syntax highlighting** for the current line (Pygments)
- **Rich-style markup** — `[bold cyan]hello[/]` parsed to ANSI, plus color helpers
- **Inquirer prompts** — `confirm`, `select`, `checkbox` with borders and custom keys
- **Async variants** — `aconfirm`, `aselect`, `acheckbox` that yield to `asyncio`
- **Right-prompt** (`rprompt`) and multi-line info bars via `FormattedPrompt`
- **Terminal-aware** — detects TTY, color depth, ANSI support; falls back cleanly
- **Resize-safe** rendering with SIGWINCH handling and flicker-free redraws

## Installation

```bash
pip install promptkit
```

Requires Python 3.9+. Runtime dependencies:

| Package    | Why                                     |
|------------|-----------------------------------------|
| `wcwidth`  | Correct column width for CJK / emoji    |
| `pygments` | Syntax highlighting of the input buffer |

## Quick start

### One-shot prompt

```python
from promptkit import prompt

name = prompt("Your name: ")
print(f"hello, {name}")
```

### With completion and history

```python
from promptkit import prompt

cmd = prompt(
    "cmd> ",
    completions=["git", "wget", "curl", "kubectl"],
    match_mode="fuzzy",       # "prefix" | "fuzzy"
    history_file="~/.myapp_history",
    prompt_style="bold cyan",
    autosuggest=True,
)
```

Pass a `dict[str, str]` to attach descriptions:

```python
cmd = prompt(
    "cmd> ",
    completions={
        "git":  "distributed VCS",
        "curl": "transfer data over URLs",
        "wget": "non-interactive downloader",
    },
)
```

### REPL loop

```python
from promptkit import prompt_loop

for line in prompt_loop("repl> ", completions=["help", "quit"], autosuggest=True):
    if line.strip() in ("quit", "exit"):
        break
    print(f"→ {line}")
```

### Persistent session

```python
from promptkit import PromptSession

session = PromptSession(
    "sql> ",
    completions=["SELECT", "FROM", "WHERE", "JOIN"],
    history_file="~/.sql_history",
)

while True:
    query = session.prompt()
    if not query.strip():
        break
    ...
```

### Inquirer-style prompts

```python
from promptkit import confirm, select, checkbox

ok = confirm("Continue?", default=True, border=True)

env = select(
    "Deploy where?",
    choices=[
        ("staging",    "internal QA cluster"),
        ("production", "customer-facing"),
    ],
    border=True,
    box_style="rounded",
).run()

features = checkbox(
    "Enable which features?",
    choices=["metrics", "tracing", "cache", "beta-ui"],
    default=["metrics"],
    border=True,
).run()
```

### Async prompts

Drop-in async variants that cooperate with `asyncio`:

```python
import asyncio
from promptkit import aconfirm, aselect

async def main() -> None:
    env = await aselect("Environment?", choices=["staging", "production"])
    go  = await aconfirm(f"Deploy to {env}?", default=False)
    print(env, go)

asyncio.run(main())
```

### Styled text

```python
from promptkit import StyleParser, style, bold, red, on_blue

print(StyleParser.parse("[bold cyan]hello[/] [italic red]world[/]"))
print(style("emphasized", "bold magenta"))
print(f"{red('error')} {bold('bold')} {on_blue('badge')}")
```

## Examples

See [`examples/`](examples/) for runnable, standalone demos:

| # | File | Shows |
|---|------|-------|
| 01 | `01_simple_input.py`    | Single-line prompt, fuzzy completion, styled info bar |
| 02 | `02_rprompt.py`         | Right-aligned prompt (`rprompt`) ghost text |
| 03 | `03_confirm.py`         | Confirm: borders, custom keys, transformers |
| 04 | `04_checkbox.py`        | Multi-select with pre-checked defaults and scrolling viewport |
| 05 | `05_select.py`          | Single-choice menu + two-column `(name, description)` layout |
| 06 | `06_repl_loop.py`       | `prompt_loop` REPL with persistent history |
| 07 | `07_session_history.py` | `PromptSession` with a file-backed history |
| 08 | `08_styling.py`         | `[tag]` markup, `style()`, and color helpers |
| 09 | `09_async_inquirer.py`  | `await` confirm/select/checkbox alongside other coroutines |
| 10 | `10_markdown_stream.py` | Markdown to styled terminal: `render_markdown()` + streaming `feed()` |
---
https://github.com/user-attachments/assets/5bd2fac8-745d-4cc9-94b4-c50897199241



Run any of them from a checkout — they add the repo root to `sys.path`:

```bash
python examples/05_select.py
```

## Public API

Top-level exports from `promptkit`:

- **Simple API** — `prompt`, `prompt_loop`, `PromptSession`
- **Inquirer** — `confirm`, `select`, `checkbox`, `Confirm`, `Select`, `Checkbox`
- **Async inquirer** — `aconfirm`, `aselect`, `acheckbox`
- **Building blocks** — `Prompt`, `Renderer`, `InputHandler`, `History`, `WordCompleter`,
  `CompletionItem`, `Completer`, `MatchMode`
- **Formatting** — `FormattedPrompt`, `PromptSpec`, `resolve_prompt`
- **Styling** — `StyleParser`, `style`, `bold`, `dim`, `italic`, `underline`,
  color helpers (`red`, `green`, `blue`, `yellow`, `magenta`, `cyan`, `white`),
  background helpers (`on_red`, `on_green`, `on_blue`, ...)
- **Highlighting** — `Highlighter`, `CompletionHighlighter`
- **Terminal** — `TerminalCapabilities`, `get_capabilities`, `reset_capabilities`
- **Box drawing** — `BoxChars`

## Terminal support

PromptKit checks whether stdin/stdout are a TTY and whether the terminal
advertises color / ANSI support. On a non-TTY (piped input, CI logs) it falls
back to `input()` and prints plain text — no escape codes leak into logs.

Tested on Linux and macOS with common terminals (iTerm2, Alacritty, kitty,
Terminal.app, GNOME Terminal, xterm, Windows Terminal). Windows uses `msvcrt`
for raw input where available.

## License

MIT.
