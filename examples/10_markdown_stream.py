#!/usr/bin/env python3
"""Markdown rendering: stream a document to a styled terminal.

MarkdownStream turns Markdown (headings, bullets, blockquotes, tables, fenced
code, inline styles) into ANSI-colored terminal output. feed() handles chunks
as they arrive (e.g. from an LLM or a subprocess), flush() finishes buffered
blocks. Non-interactive: prints straight to stdout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import MarkdownStream, render_markdown  # noqa: E402

DOC = """# PromptKit

Modular terminal input for **Python**.

- Line editor with **cursor movement** and kill/yank
- Fuzzy `completion` with descriptions
- Inquirer-style prompts ([docs](https://example.com))

> Streaming markdown renders as it arrives.

| Feature  | Status |
|----------|--------|
| sync     | done   |
| async    | done   |

```python
print("hello")
```

---

The `--done--` bits and ~~struck~~ text show inline styling.
"""

# 1. One-shot: render a complete string (returns ANSI text, print it).
print("=== render_markdown() ===\n")
print(render_markdown(DOC))

# 2. Streaming: feed in chunks, then flush the tail.
print("\n=== MarkdownStream streaming ===\n")
md = MarkdownStream()
for line in DOC.splitlines(keepends=True):
    md.feed(line)
md.flush()

# 3. Custom theme via constructor kwargs.
print("\n=== Custom theme ===\n")
custom = MarkdownStream(
    heading_style="#ff79c6 bold",
    bullet_style="#50fa7b",
    code_style="#f1fa8c",
    table_border_style="#6272a4",
    bullet_char=">",
    pygments_style="monokai",
)
custom.feed("# Custom\n\n- one\n- two\n")
custom.flush()
