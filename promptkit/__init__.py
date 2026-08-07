from .completion import CompletionItem, Completer, WordCompleter, MatchMode
from .input import InputHandler
from .renderer import Renderer
from .prompt import Prompt
from .box_chars import BoxChars
from .highlighter import Highlighter, CompletionHighlighter
from .terminal import TerminalCapabilities, get_capabilities, reset_capabilities
from .history import History
from .styling import (
    StyleParser,
    style,
    bold,
    dim,
    italic,
    underline,
    red,
    green,
    blue,
    yellow,
    magenta,
    cyan,
    white,
    on_red,
    on_green,
    on_blue,
    on_yellow,
    on_magenta,
    on_cyan,
    on_white,
    on_black,
)
from .inquirer import Confirm, confirm, Select, select, Checkbox, checkbox
from .inquirer import aconfirm, aselect, acheckbox
from .simple_api import prompt, prompt_loop, PromptSession
from .formatted_prompt import FormattedPrompt, PromptSpec, resolve_prompt
from .markdown_stream import MarkdownStream, render_markdown

__version__ = "0.1.0"

__all__ = [
    # --- Completion ---
    "CompletionItem",
    "Completer",
    "WordCompleter",
    "MatchMode",
    # --- Core ---
    "InputHandler",
    "Renderer",
    "Prompt",
    "BoxChars",
    "Highlighter",
    "CompletionHighlighter",
    # --- Terminal ---
    "TerminalCapabilities",
    "get_capabilities",
    "reset_capabilities",
    # --- History ---
    "History",
    # --- Styling ---
    "StyleParser",
    "style",
    "bold",
    "dim",
    "italic",
    "underline",
    "red",
    "green",
    "blue",
    "yellow",
    "magenta",
    "cyan",
    "white",
    "on_red",
    "on_green",
    "on_blue",
    "on_yellow",
    "on_magenta",
    "on_cyan",
    "on_white",
    "on_black",
    # --- Inquirer ---
    "Confirm",
    "confirm",
    "Select",
    "select",
    "Checkbox",
    "checkbox",
    "aconfirm",
    "aselect",
    "acheckbox",
    # --- Simple API ---
    "prompt",
    "prompt_loop",
    "PromptSession",
    # --- Custom Prompt ---
    "FormattedPrompt",
    "PromptSpec",
    "resolve_prompt",
    # --- Markdown Stream ---
    "MarkdownStream",
    "render_markdown",
]
