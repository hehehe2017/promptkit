# PromptKit Examples

Runnable demos of what the framework can do. Each file is standalone and inserts
the repo root on `sys.path`, so you can run them straight from a checkout without
installing:

```bash
python examples/05_select.py
```

Most examples are interactive — run them in a real terminal (a TTY). On a
non-interactive stream PromptKit falls back to plain `input()`.

| # | File | Shows |
|---|------|-------|
| 01 | `01_simple_input.py` | Single-line prompt, fuzzy completion, autosuggest, styled info bar |
| 02 | `02_rprompt.py` | Right-aligned prompt (`rprompt`) ghost text |
| 03 | `03_confirm.py` | Yes/no confirm: borders, custom keys, transformers |
| 04 | `04_checkbox.py` | Multi-select with pre-checked defaults and a scrolling viewport |
| 05 | `05_select.py` | Single-choice menu + two-column `(name, description)` layout |
| 06 | `06_repl_loop.py` | `prompt_loop` REPL with persistent history |
| 07 | `07_session_history.py` | `PromptSession` with a file-backed history that survives restarts |
| 08 | `08_styling.py` | `[tag]` markup, `style()`, and color helpers (non-interactive) |
| 09 | `09_async_inquirer.py` | `await` confirm/select/checkbox alongside other coroutines |
| 10 | `10_markdown_stream.py` | Markdown to styled terminal: `render_markdown()` + streaming `feed()` |

Examples 01 and 02 load `commands_desc.json` from `examples/` as their
completion source.
