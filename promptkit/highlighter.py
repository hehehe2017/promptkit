from __future__ import annotations

import os
from typing import Any
from pygments import highlight
from pygments.lexers import get_lexer_by_name, PythonLexer  # pylint: disable=E0611
from pygments.formatters import (  # pylint: disable=E0611
    TerminalTrueColorFormatter,
    Terminal256Formatter,
    TerminalFormatter,
)
from pygments.token import Token
from .terminal import get_capabilities


class Highlighter:

    def __init__(
        self,
        style: str = "monokai",
        truecolor: bool | None = None,
        language: str | None = None,
    ) -> None:
        self.style: str = style
        self.truecolor: bool = truecolor if truecolor is not None else self._detect_truecolor()
        self.language: str | None = language
        self._lexer_cache: dict[str, Any] = {}
        self._formatter_cache: dict[str, Any] = {}

    def _detect_truecolor(self) -> bool:
        try:
            caps = get_capabilities()
            if caps.color_level >= 3:
                return True
            if caps.color_level == 0:
                return False
        except Exception:
            pass

        colorterm = os.environ.get("COLORTERM", "").lower()
        if colorterm in ("truecolor", "24bit"):
            return True

        term = os.environ.get("TERM", "").lower()
        if "256color" in term or "truecolor" in term:
            return True

        return False

    def _get_lexer(self, language: str | None = None) -> Any:
        lang = language or self.language

        if lang in self._lexer_cache:
            return self._lexer_cache[lang]

        try:
            if lang:
                lexer = get_lexer_by_name(lang)
            else:
                lexer = PythonLexer()
        except Exception:
            lexer = PythonLexer()

        self._lexer_cache[lang or "python"] = lexer
        return lexer

    def _get_formatter(self) -> Any:
        cache_key = f"{self.style}_{self.truecolor}"

        if cache_key in self._formatter_cache:
            return self._formatter_cache[cache_key]

        try:
            if self.truecolor:
                formatter = TerminalTrueColorFormatter(style=self.style)
            else:
                formatter = Terminal256Formatter(style=self.style)
        except Exception:
            formatter = TerminalFormatter(style=self.style)

        self._formatter_cache[cache_key] = formatter
        return formatter

    def highlight(self, text: str, language: str | None = None) -> str:
        if not text:
            return ""

        try:
            caps = get_capabilities()
            if caps.color_level == 0:
                return text
        except Exception:
            pass

        try:
            lexer = self._get_lexer(language)
            formatter = self._get_formatter()
            highlighted = highlight(text, lexer, formatter)
            return highlighted.rstrip('\n')
        except Exception:
            return text

    def highlight_token(
        self,
        text: str,
        token_type: str = "Text",
    ) -> str:
        if not text:
            return ""

        try:
            caps = get_capabilities()
            if caps.color_level == 0:
                return text
        except Exception:
            pass

        try:
            token = Token.Text
            if '.' in token_type:
                parts = token_type.split('.')
                current = Token
                for part in parts:
                    current = getattr(current, part, Token.Text)
                token = current
            else:
                token = getattr(Token, token_type, Token.Text)

            formatter = self._get_formatter()

            style = formatter.style
            token_style = style.style_for_token(token)

            if token_style:
                color = token_style.get('color')
                bgcolor = token_style.get('bgcolor')
                bold = token_style.get('bold')
                italic = token_style.get('italic')
                underline = token_style.get('underline')

                codes: list[str] = []

                if color:
                    if self.truecolor:
                        r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
                        codes.append(f"38;2;{r};{g};{b}")
                    else:
                        codes.append(f"38;5;{self._rgb_to_256(color)}")

                if bgcolor:
                    if self.truecolor:
                        r, g, b = int(bgcolor[0:2], 16), int(bgcolor[2:4], 16), int(bgcolor[4:6], 16)
                        codes.append(f"48;2;{r};{g};{b}")
                    else:
                        codes.append(f"48;5;{self._rgb_to_256(bgcolor)}")

                if bold:
                    codes.append("1")
                if italic:
                    codes.append("3")
                if underline:
                    codes.append("4")

                if codes:
                    prefix = f"\033[{';'.join(codes)}m"
                    suffix = "\033[0m"
                    return f"{prefix}{text}{suffix}"

            return text
        except Exception:
            return text

    @staticmethod
    def _rgb_to_256(hex_color: str) -> int:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        def cube_channel(v: int) -> int:
            return round(v / 255 * 5)

        cube_idx = 16 + (cube_channel(r) * 36 + cube_channel(g) * 6 + cube_channel(b))

        if r == g == b:
            grey_idx = 232 + round(r / 255 * 23)

            def color_distance(idx: int) -> float:
                if 16 <= idx <= 231:
                    cr = (idx - 16) // 36 * 51
                    cg = ((idx - 16) % 36) // 6 * 51
                    cb = (idx - 16) % 6 * 51
                else:
                    val = 8 + (idx - 232) * 10
                    cr = cg = cb = min(val, 238)
                return (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2

            if color_distance(grey_idx) < color_distance(cube_idx):
                return grey_idx

        return cube_idx

    def get_available_styles(self) -> list[str]:
        from pygments.styles import get_all_styles
        return list(get_all_styles())

    def get_available_languages(self) -> list[str]:
        from pygments.lexers import get_all_lexers
        return [lexer[0] for lexer in get_all_lexers()]


class CompletionHighlighter:

    def __init__(self, highlighter: Highlighter) -> None:
        self.highlighter: Highlighter = highlighter

    def highlight_completion(
        self,
        text: str,
        completion_type: str = "text",
    ) -> str:
        if not text:
            return ""

        token_map: dict[str, str] = {
            "keyword": "Keyword",
            "function": "Name.Function",
            "variable": "Name",
            "class": "Name.Class",
            "module": "Name.Namespace",
            "string": "Literal.String",
            "number": "Literal.Number",
            "comment": "Comment",
            "operator": "Operator",
            "text": "Text",
        }

        token_type = token_map.get(completion_type.lower(), "Text")
        return self.highlighter.highlight_token(text, token_type)

    def highlight_description(self, description: str) -> str:
        if not description:
            return ""
        return self.highlighter.highlight_token(description, "Comment.Single")
