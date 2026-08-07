from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

from .styling import StyleParser


@dataclass
class FormattedPrompt:
    info_line: str | None = None
    prompt_prefix: str = "╰─❯ "
    rprompt: str | None = None

    @property
    def styled_info_line(self) -> str:
        if not self.info_line:
            return ""
        return StyleParser.parse(self.info_line)

    @property
    def styled_prompt_prefix(self) -> str:
        return StyleParser.parse(self.prompt_prefix)

    @property
    def info_line_visible_length(self) -> int:
        if not self.info_line:
            return 0
        return StyleParser.get_visible_length(self.info_line)

    @property
    def prompt_prefix_visible_length(self) -> int:
        return StyleParser.get_visible_length(self.prompt_prefix)

    @property
    def styled_rprompt(self) -> str:
        if not self.rprompt:
            return ""
        return StyleParser.parse(self.rprompt)

    @property
    def rprompt_visible_length(self) -> int:
        if not self.rprompt:
            return 0
        return StyleParser.get_visible_length(self.rprompt)


PromptSpec = Union[str, FormattedPrompt, Callable[[], FormattedPrompt]]


def resolve_prompt(spec: PromptSpec) -> FormattedPrompt:
    if isinstance(spec, str):
        return FormattedPrompt(info_line=None, prompt_prefix=spec)
    if callable(spec):
        return spec()
    return spec
