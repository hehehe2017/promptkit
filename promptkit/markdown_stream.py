from __future__ import annotations

import logging
import re
import sys
from io import StringIO
from wcwidth import wcswidth, wcwidth as _wcwidth
from .styling import StyleParser
from .box_chars import BoxChars
from .terminal import get_capabilities
from .highlighter import Highlighter

__all__ = ["MarkdownStream", "render_markdown"]

log = logging.getLogger(__name__)

_ESCAPABLE = set(r"\`*_{}()#+-.!|~>")
_INLINE_PATTERNS = (
    (re.compile(r"`([^`]+?)`"),    r"[{code_style}]\1[/]"),
    (re.compile(r"!\[([^\]]*?)\]\(([^)]+?)\)"),
     r"[bold #d3869b]\1[/] [dim #a89984](\2)[/]"),
    (re.compile(r"\[([^\]]+?)\]\(([^)]+?)\)"),
     r"[bold #83a598]\1[/] [dim #a89984](\2)[/]"),
    (re.compile(r"\*\*(.+?)\*\*"), r"[bold]\1[/]"),
    (re.compile(r"__(.+?)__"),     r"[bold]\1[/]"),
    (re.compile(r"~~(.+?)~~"),    r"[strikethrough]\1[/]"),
)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET_RE = re.compile(r"^([-*]|\d+\.)\s+(.*)")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)")
_TABLE_SEP_CELL_RE = re.compile(r":?-+:?")
_FENCE_RE = re.compile(r"^```(\w*)")
_ESCAPE_RE = re.compile(r"\\(.)")


_PROMPTKIT_TO_RICH_STYLE: dict[str, str] = {
    "ansiblack":       "black",
    "ansired":         "red",
    "ansigreen":       "green",
    "ansiyellow":      "yellow",
    "ansiblue":        "blue",
    "ansimagenta":     "magenta",
    "ansicyan":        "cyan",
    "ansiwhite":       "white",
    "ansibrightblack": "bright_black",
    "ansibrightred":   "bright_red",
    "ansibrightgreen": "bright_green",
    "ansibrightyellow":"bright_yellow",
    "ansibrightblue":  "bright_blue",
    "ansibrightmagenta":"bright_magenta",
    "ansibrightcyan":  "bright_cyan",
    "ansibrightwhite": "bright_white",
    "ansidarkgrey":    "bright_black",
    "ansidarkgray":    "bright_black",
    "ansilightgrey":   "white",
    "ansilightgray":   "white",
    "ansiorange":      "dark_orange",
    "ansipink":        "bright_magenta",
    "ansipurple":      "magenta",
    "ansiteal":        "cyan",
    "ansinavy":        "blue",
    "ansimaroon":      "red",
    "red":             "red",
    "green":           "green",
    "blue":            "blue",
    "yellow":          "yellow",
    "magenta":         "magenta",
    "cyan":            "cyan",
    "white":           "white",
    "black":           "black",
    "grey":            "bright_black",
    "gray":            "bright_black",
    "orange":          "dark_orange",
    "purple":          "magenta",
    "pink":            "bright_magenta",
    "bold":            "bold",
    "italic":          "italic",
    "underline":       "underline",
    "dim":             "dim",
    "strikethrough":   "strikethrough",
    "blink":           "blink",
    "reverse":         "reverse",
}


def _style_to_rich(style: str) -> str:
    if not style:
        return ""

    tokens: list[str] = []
    for part in style.split():
        resolved = _PROMPTKIT_TO_RICH_STYLE.get(part.lower(), part.lower())
        tokens.append(resolved)

    _MODIFIERS = frozenset(("bold", "dim", "italic", "underline", "strikethrough", "blink", "reverse"))
    modifiers = [t for t in tokens if t in _MODIFIERS]
    colors = [t for t in tokens if t not in _MODIFIERS]
    ordered = modifiers + colors

    return " ".join(ordered)


class MarkdownStream:

    def __init__(
        self,
        *,
        heading_style: str = "#fe8019 bold",
        bullet_style: str = "#8ec07c",
        code_style: str = "#b8bb26",
        code_fence_style: str = "#928374 dim",
        blockquote_style: str = "#a89984 dim italic",
        table_header_style: str = "#83a598 bold",
        table_border_style: str = "#665c54",
        table_border: str = "rounded",
        rule_style: str = "#928374 dim",
        bullet_char: str = "\u2022",
        pygments_style: str = "monokai",
        padding: int = 1,
    ) -> None:
        self._heading_rich = _style_to_rich(heading_style)
        self._bullet_rich = _style_to_rich(bullet_style)
        self._code_rich = _style_to_rich(code_style)
        self._code_fence_rich = _style_to_rich(code_fence_style)
        self._blockquote_rich = _style_to_rich(blockquote_style)
        self._table_header_rich = _style_to_rich(table_header_style)
        self._table_border_rich = _style_to_rich(table_border_style)
        self._rule_rich = _style_to_rich(rule_style)
        self._bullet_char = bullet_char
        self._padding = max(0, int(padding))

        self._caps = get_capabilities()
        self._box_style = table_border

        self._pending = ""
        self._in_code_fence = False
        self._table_rows: list[list[str]] = []
        self._table_alignments: list[str] | None = None
        self._fence_lang: str = ""
        self._fence_buf: list[str] = []

        self._active_colorstyle: str = ""
        self._active_border_style: str = ""

        self._highlighter = Highlighter(style=pygments_style)

        self._capture: StringIO | None = None

    def __repr__(self) -> str:
        state = "in_code_fence" if self._in_code_fence else "idle"
        if self._table_rows:
            state = f"table({len(self._table_rows)} rows)"
        elif self._pending:
            state = f"pending({len(self._pending)} chars)"
        return f"<MarkdownStream state={state} border={self._box_style!r}>"

    def __str__(self) -> str:
        parts: list[str] = []
        if self._pending:
            parts.append(f"pending: {self._pending!r}")
        if self._in_code_fence:
            parts.append(f"code_fence({self._fence_lang or 'unknown'}): {len(self._fence_buf)} lines buffered")
        if self._table_rows:
            parts.append(f"table: {len(self._table_rows)} rows buffered")
        return "MarkdownStream({})".format(", ".join(parts) if parts else "idle")

    def __enter__(self) -> MarkdownStream:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.flush()

    def feed(self, chunk: str, colorstyle: str = "", border_style: str = "") -> None:
        if not chunk:
            return

        provided_colorstyle = bool(colorstyle)
        provided_border = bool(border_style)

        if colorstyle:
            self._active_colorstyle = _style_to_rich(colorstyle)
        if border_style:
            self._active_border_style = border_style

        self._pending += chunk
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._emit_line(line)

        if provided_colorstyle:
            self._active_colorstyle = ""
        if provided_border:
            self._active_border_style = ""

    def flush(self) -> None:
        if self._in_code_fence:
            self._in_code_fence = False
            self._flush_code_block()

        if self._pending:
            self._emit_line(self._pending)
            self._pending = ""

        self._flush_table()

    def reset(self) -> None:
        self._pending = ""
        self._in_code_fence = False
        self._table_rows = []
        self._table_alignments = None
        self._fence_lang = ""
        self._fence_buf = []
        self._active_colorstyle = ""
        self._active_border_style = ""
        self._highlighter._lexer_cache.clear()
        self._highlighter._formatter_cache.clear()

    def _line_prefix(self) -> str:
        return " " * self._padding

    def _print(self, text: str) -> None:
        line = StyleParser.parse(text) if self._caps.supports_ansi else self._caps.strip_rich_tags(text)
        line = self._line_prefix() + line
        if self._capture is not None:
            self._capture.write(line + "\n")
        else:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _print_raw(self, text: str) -> None:
        line = self._line_prefix() + text
        if self._capture is not None:
            self._capture.write(line + "\n")
        else:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _flush_code_block(self) -> None:
        if not self._fence_buf:
            return

        code = "\n".join(self._fence_buf)

        if not self._caps.supports_ansi:
            for line in self._fence_buf:
                self._print(self._rich_wrap(line, self._code_rich))
            self._fence_buf = []
            self._fence_lang = ""
            return

        if not self._fence_lang:
            for line in self._fence_buf:
                self._print(self._rich_wrap(line, self._code_rich))
            self._fence_buf = []
            self._fence_lang = ""
            return

        try:
            lang = self._fence_lang or None
            highlighted = self._highlighter.highlight(code, language=lang)
            for hl_line in highlighted.split("\n"):
                self._print_raw(hl_line)
        except Exception as exc:
            log.debug(
                "Pygments highlight failed for lang=%r: %s — falling back to plain style",
                self._fence_lang,
                exc,
            )
            for line in self._fence_buf:
                self._print(self._rich_wrap(line, self._code_rich))

        self._fence_buf = []
        self._fence_lang = ""

    def _render_inline(self, text: str) -> str:
        _protected: dict[str, str] = {}
        _counter: int = 0

        def _protect(m: re.Match[str]) -> str:
            nonlocal _counter
            ch = m.group(1)
            if ch in _ESCAPABLE:
                key = f"\x1f{_counter}\x1f"
                _protected[key] = ch
                _counter += 1
                return key
            return m.group(0)
        text = _ESCAPE_RE.sub(_protect, text)

        for pattern, repl in _INLINE_PATTERNS:
            if "{code_style}" in repl:
                repl = repl.format(code_style=self._code_rich)
            text = pattern.sub(repl, text)

        for key, ch in _protected.items():
            text = text.replace(key, ch)

        return text

    @staticmethod
    def _display_width(text: str) -> int:
        for pattern, _repl in _INLINE_PATTERNS:
            text = pattern.sub(r"\1", text)
        width = wcswidth(text)
        if width >= 0:
            return width
        total = 0
        for ch in text:
            w = _wcwidth(ch)
            if w > 0:
                total += w
        return total

    def _rich_wrap(self, text: str, rich_style: str) -> str:
        if not rich_style:
            return text
        return f"[{rich_style}]{text}[/{rich_style}]"

    @staticmethod
    def _is_table_row(stripped: str) -> bool:
        return (
            stripped.startswith("|")
            and stripped.endswith("|")
            and stripped.count("|") >= 2
        )

    @staticmethod
    def _split_table_cells(stripped: str) -> list[str]:
        return [c.strip() for c in stripped.strip("|").split("|")]

    @classmethod
    def _is_table_separator(cls, stripped: str) -> bool:
        cells = cls._split_table_cells(stripped)
        return bool(cells) and all(_TABLE_SEP_CELL_RE.fullmatch(c) for c in cells)

    @classmethod
    def _parse_table_alignments(cls, stripped: str) -> list[str] | None:
        cells = cls._split_table_cells(stripped)
        if not cells or not all(_TABLE_SEP_CELL_RE.fullmatch(c) for c in cells):
            return None
        alignments: list[str] = []
        for c in cells:
            left_dash = c.startswith(":")
            right_dash = c.endswith(":")
            if left_dash and right_dash and len(c) > 2:
                alignments.append("center")
            elif right_dash and len(c) > 1:
                alignments.append("right")
            elif left_dash and len(c) > 1:
                alignments.append("left")
            else:
                alignments.append("left")
        return alignments

    def _apply_width_cap(
        self,
        widths: list[int],
        col_count: int,
        border_type: str,
        min_widths: list[int] | None = None,
    ) -> list[int]:
        fallback_min = 3
        available = max(1, self._caps.term_cols - self._padding)
        if border_type == "none":
            overhead = 2 * (col_count - 1)
        else:
            pad = 1
            overhead = (col_count + 1) + col_count * 2 * pad
        total = sum(widths) + overhead
        if total <= available:
            return widths

        if min_widths is None:
            min_widths = [fallback_min] * col_count
        else:
            min_widths = [max(fallback_min, w) for w in min_widths[:col_count]]
            while len(min_widths) < col_count:
                min_widths.append(fallback_min)

        excess = total - available
        capped = widths[:]

        while excess > 0:
            shrinkable = [
                (i, capped[i] - min_widths[i])
                for i in range(col_count)
                if capped[i] > min_widths[i]
            ]
            if not shrinkable:
                break
            total_shrinkable = sum(s for _, s in shrinkable)
            if total_shrinkable <= 0:
                break
            made_progress = False
            for i, room in shrinkable:
                share = int(excess * (room / total_shrinkable) + 0.5)
                trim = min(share, room, excess)
                if trim > 0:
                    capped[i] -= trim
                    excess -= trim
                    made_progress = True
            if not made_progress:
                break

        return capped

    def _longest_table_word_width(self, text: str) -> int:
        words = [word for paragraph in text.split("\n") for word in paragraph.split()]
        if not words:
            return 0
        return max(self._display_width(word) for word in words)

    def _wrap_cell_text(self, text: str, width: int) -> list[str]:
        if width < 1:
            return [""]
        if not text:
            return [""]

        lines: list[str] = []
        for paragraph in text.split("\n"):
            if paragraph == "":
                lines.append("")
                continue

            words = paragraph.split(" ")
            current = ""

            def _hard_wrap(token: str) -> None:
                chunk = ""
                chunk_width = 0
                for ch in token:
                    w = _wcwidth(ch)
                    if w < 0:
                        w = 1
                    if chunk and chunk_width + w > width:
                        lines.append(chunk)
                        chunk = ch
                        chunk_width = w
                    else:
                        chunk += ch
                        chunk_width += w
                if chunk:
                    lines.append(chunk)

            for word in words:
                if word == "":
                    candidate = f"{current} " if current else ""
                elif current:
                    candidate = f"{current} {word}"
                else:
                    candidate = word

                if candidate and self._display_width(candidate) <= width:
                    current = candidate
                    continue

                if current:
                    lines.append(current)
                    current = ""

                if not word:
                    continue

                if self._display_width(word) <= width:
                    current = word
                else:
                    _hard_wrap(word)

            if current:
                lines.append(current)

        return lines or [""]

    def _align_cell(self, text: str, width: int, alignment: str = "left") -> str:
        rendered = self._render_inline(text)
        visible = self._display_width(text)
        if visible >= width:
            return rendered
        space = width - visible
        if alignment == "right":
            return " " * space + rendered
        elif alignment == "center":
            left = space // 2
            right = space - left
            return " " * left + rendered + " " * right
        else:
            return rendered + " " * space

    def _render_cell_block(self, text: str, width: int, alignment: str = "left") -> list[str]:
        wrapped = self._wrap_cell_text(text, width)
        return [self._align_cell(line, width, alignment) for line in wrapped]

    def _flush_table(self) -> None:
        if not self._table_rows:
            return
        col_count = max(len(r) for r in self._table_rows)
        alignments = self._table_alignments or ["left"] * col_count
        while len(alignments) < col_count:
            alignments.append("left")
        widths = [
            max(
                (self._display_width(row[i]) for row in self._table_rows if i < len(row)),
                default=0,
            )
            for i in range(col_count)
        ]

        min_widths = [
            max(
                (self._longest_table_word_width(row[i]) for row in self._table_rows if i < len(row)),
                default=0,
            )
            for i in range(col_count)
        ]

        effective_border = self._resolve_border()
        widths = self._apply_width_cap(widths, col_count, effective_border, min_widths)

        if effective_border == "none":
            self._flush_table_plain(widths, col_count, alignments)
        else:
            self._flush_table_boxed(widths, col_count, effective_border, alignments)

        self._table_rows = []
        self._table_alignments = None

    def _flush_table_plain(self, widths: list[int], col_count: int, alignments: list[str]) -> None:
        for i, row in enumerate(self._table_rows):
            cells = [(row[c] if c < len(row) else "") for c in range(col_count)]
            cell_blocks = [
                self._render_cell_block(cells[c], widths[c], alignments[c])
                for c in range(col_count)
            ]
            row_height = max((len(block) for block in cell_blocks), default=1)
            empty_cells = [self._align_cell("", widths[c], alignments[c]) for c in range(col_count)]

            for line_idx in range(row_height):
                padded = [
                    cell_blocks[c][line_idx] if line_idx < len(cell_blocks[c]) else empty_cells[c]
                    for c in range(col_count)
                ]
                rendered = "  ".join(padded)
                if i == 0:
                    self._print(self._rich_wrap(rendered, self._table_header_rich))
                else:
                    self._print(rendered)

            if i == 0:
                rule_len = sum(widths) + 2 * (col_count - 1)
                self._print(self._rich_wrap("-" * rule_len, self._rule_rich))

    def _flush_table_boxed(self, widths: list[int], col_count: int, border_style: str | None = None, alignments: list[str] | None = None) -> None:
        bc = BoxChars.for_style(border_style or self._box_style)
        pad = 1
        if alignments is None:
            alignments = ["left"] * col_count

        def _rule(left: str, mid: str, right: str) -> str:
            segments = [bc.horizontal * (w + 2 * pad) for w in widths]
            return left + mid.join(segments) + right

        top = _rule(bc.top_left, bc.tee_down, bc.top_right)
        header_sep = _rule(bc.tee_right, bc.cross, bc.tee_left)
        bottom = _rule(bc.bottom_left, bc.tee_up, bc.bottom_right)

        self._print(self._rich_wrap(top, self._table_border_rich))
        for i, row in enumerate(self._table_rows):
            cells = [(row[c] if c < len(row) else "") for c in range(col_count)]
            cell_blocks = [
                self._render_cell_block(cells[c], widths[c], alignments[c])
                for c in range(col_count)
            ]
            row_height = max((len(block) for block in cell_blocks), default=1)
            empty_cells = [self._align_cell("", widths[c], alignments[c]) for c in range(col_count)]
            v = self._rich_wrap(bc.vertical, self._table_border_rich)
            style = self._table_header_rich if i == 0 else ""

            for line_idx in range(row_height):
                padded_cells = []
                for c in range(col_count):
                    text = cell_blocks[c][line_idx] if line_idx < len(cell_blocks[c]) else empty_cells[c]
                    text = f"{' ' * pad}{text}{' ' * pad}"
                    padded_cells.append(self._rich_wrap(text, style) if style else text)
                self._print(v + v.join(padded_cells) + v)

            if i == 0:
                self._print(self._rich_wrap(header_sep, self._table_border_rich))
        self._print(self._rich_wrap(bottom, self._table_border_rich))


    def _resolve_color(self, fallback: str) -> str:
        return self._active_colorstyle if self._active_colorstyle else fallback

    def _resolve_border(self) -> str:
        return self._active_border_style if self._active_border_style else self._box_style

    def _emit_line(self, line: str) -> None:
        stripped = line.strip()

        if self._is_table_row(stripped):
            if self._is_table_separator(stripped):
                self._table_alignments = self._parse_table_alignments(stripped)
            else:
                cells = self._split_table_cells(stripped)
                self._table_rows.append(cells)
            return
        elif self._table_rows:
            self._flush_table()

        if stripped.startswith("```"):
            if not self._in_code_fence:
                m = _FENCE_RE.match(stripped)
                self._fence_lang = (m.group(1) if m else "") or ""
                self._in_code_fence = True
                self._fence_buf = []
                self._print(self._rich_wrap(stripped, self._code_fence_rich))
                return
            else:
                self._in_code_fence = False
                self._flush_code_block()
                self._print(self._rich_wrap(stripped, self._code_fence_rich))
                return

        if self._in_code_fence:
            self._fence_buf.append(line)
            return

        header_match = _HEADER_RE.match(stripped)
        if header_match:
            _level, content = header_match.groups()
            rendered = self._render_inline(content)
            self._print(self._rich_wrap(rendered, self._resolve_color(self._heading_rich)))
            return

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            marker, content = bullet_match.groups()
            rendered = self._render_inline(content)
            if marker.isdigit() or (len(marker) > 1 and marker[:-1].isdigit()):
                prefix = self._rich_wrap(marker, self._resolve_color(self._bullet_rich))
            else:
                prefix = self._rich_wrap(self._bullet_char, self._resolve_color(self._bullet_rich))
            self._print(f"  {prefix} {self._rich_wrap(rendered, self._resolve_color(''))}")
            return

        bq_match = _BLOCKQUOTE_RE.match(stripped)
        if bq_match:
            content = bq_match.group(1)
            rendered = self._render_inline(content)
            bar = self._rich_wrap("\u2502", "dim")
            self._print(f"  {bar} {self._rich_wrap(rendered, self._resolve_color(self._blockquote_rich))}")
            return

        if not stripped:
            if self._capture is not None:
                self._capture.write("\n")
            else:
                sys.stdout.write("\n")
                sys.stdout.flush()
            return

        rendered = self._render_inline(line)
        self._print(self._rich_wrap(rendered, self._resolve_color('')))


def render_markdown(markdown_text: str, **kwargs) -> str:
    md = MarkdownStream(**kwargs)
    buf = StringIO()
    md._capture = buf
    md.feed(markdown_text if markdown_text.endswith("\n") else markdown_text + "\n")
    md.flush()
    md._capture = None
    return buf.getvalue()
