from __future__ import annotations

import re
from .terminal import get_capabilities
from .text_utils import hex_to_rgb, visible_width, truncate_ansi, ANSI_ESCAPE_RE


class StyleParser:

    COLORS: dict[str, str] = {
        "black": "30",
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "white": "37",
        "bright_black": "90",
        "bright_red": "91",
        "bright_green": "92",
        "bright_yellow": "93",
        "bright_blue": "94",
        "bright_magenta": "95",
        "bright_cyan": "96",
        "bright_white": "97",
    }

    BG_COLORS: dict[str, str] = {
        "black": "40",
        "red": "41",
        "green": "42",
        "yellow": "43",
        "blue": "44",
        "magenta": "45",
        "cyan": "46",
        "white": "47",
        "bright_black": "100",
        "bright_red": "101",
        "bright_green": "102",
        "bright_yellow": "103",
        "bright_blue": "104",
        "bright_magenta": "105",
        "bright_cyan": "106",
        "bright_white": "107",
    }

    STYLES: dict[str, str] = {
        "bold": "1",
        "dim": "2",
        "italic": "3",
        "underline": "4",
        "blink": "5",
        "reverse": "7",
        "hidden": "8",
        "strikethrough": "9",
    }

    NAMED_HEX: dict[str, str] = {
        "dark_orange":   "#ff8c00",
        "orange":        "#ff8c00",
        "dark_red":      "#8b0000",
        "dark_green":    "#006400",
        "dark_blue":     "#00008b",
        "dark_yellow":   "#8b8b00",
        "dark_magenta":  "#8b008b",
        "dark_cyan":     "#008b8b",
        "light_grey":    "#d3d3d3",
        "light_gray":   "#d3d3d3",
        "dark_grey":     "#a9a9a9",
        "dark_gray":    "#a9a9a9",
        "gold":          "#ffd700",
        "coral":         "#ff7f50",
        "salmon":        "#fa8072",
        "tomato":        "#ff6347",
        "crimson":       "#dc143c",
        "indigo":        "#4b0082",
        "violet":        "#ee82ee",
        "turquoise":     "#40e0d0",
        "khaki":         "#f0e68c",
        "lavender":      "#e6e6fa",
        "maroon":        "#800000",
        "navy":          "#000080",
        "olive":         "#808000",
        "teal":          "#008080",
        "silver":        "#c0c0c0",
        "lime":          "#00ff00",
        "aqua":          "#00ffff",
        "fuchsia":       "#ff00ff",
        "plum":          "#dda0dd",
        "orchid":        "#da70d6",
        "tan":           "#d2b48c",
        "sienna":        "#a0522d",
        "chocolate":     "#d2691e",
        "peru":          "#cd853f",
    }

    @classmethod
    def parse(cls, text: str) -> str:
        if not text:
            return ""

        caps = get_capabilities()
        if caps.color_level == 0:
            return caps.strip_rich_tags(text)

        result: list[str] = []
        style_stack: list[list[str]] = []
        i = 0

        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in ('[', ']'):
                result.append(text[i + 1])
                i += 2
                continue

            if text[i] == '[':
                close_idx = text.find(']', i)
                if close_idx == -1:
                    result.append(text[i])
                    i += 1
                    continue

                if text[i+1] == '/':
                    if style_stack:
                        style_stack.pop()
                        if style_stack:
                            parent_codes = style_stack[-1]
                            result.append(f'\033[{";".join(parent_codes)}m')
                        else:
                            result.append('\033[0m')
                    else:
                        result.append('\033[0m')
                    i = close_idx + 1
                    continue

                tag_content = text[i+1:close_idx]
                codes = cls._parse_styles(tag_content)

                if codes:
                    result.append(f'\033[{";".join(codes)}m')
                    style_stack.append(codes)
                else:
                    result.append(f'[{tag_content}]')

                i = close_idx + 1
            else:
                result.append(text[i])
                i += 1

        result.append('\033[0m')

        return ''.join(result)

    @classmethod
    def _parse_styles(cls, tag_content: str) -> list[str]:
        codes: list[str] = []
        parts = tag_content.split()

        i = 0
        n = len(parts)
        while i < n:
            part = parts[i]

            if part.startswith('on_'):
                color_name = part[3:]
                if color_name in cls.BG_COLORS:
                    codes.append(cls.BG_COLORS[color_name])
                elif cls._is_hex_color(color_name):
                    codes.append(cls._hex_to_bg_ansi(color_name))
                elif color_name in cls.NAMED_HEX:
                    codes.append(cls._hex_to_bg_ansi(cls.NAMED_HEX[color_name]))
            elif part == 'on' and i + 1 < n:
                color_name = parts[i + 1]
                if color_name in cls.BG_COLORS:
                    codes.append(cls.BG_COLORS[color_name])
                elif cls._is_hex_color(color_name):
                    codes.append(cls._hex_to_bg_ansi(color_name))
                elif color_name in cls.NAMED_HEX:
                    codes.append(cls._hex_to_bg_ansi(cls.NAMED_HEX[color_name]))
                i += 1
            elif part in cls.COLORS:
                codes.append(cls.COLORS[part])
            elif cls._is_hex_color(part):
                codes.append(cls._hex_to_fg_ansi(part))
            elif part in cls.NAMED_HEX:
                codes.append(cls._hex_to_fg_ansi(cls.NAMED_HEX[part]))
            elif part in cls.STYLES:
                codes.append(cls.STYLES[part])

            i += 1

        return codes

    @classmethod
    def _is_hex_color(cls, color: str) -> bool:
        return bool(re.match(r'^#[0-9a-fA-F]{6}$', color))

    @classmethod
    def _hex_to_fg_ansi(cls, hex_color: str) -> str:
        rgb = hex_to_rgb(hex_color)
        if rgb is None:
            return hex_color.lstrip('#')
        r, g, b = rgb
        return f"38;2;{r};{g};{b}"

    @classmethod
    def _hex_to_bg_ansi(cls, hex_color: str) -> str:
        rgb = hex_to_rgb(hex_color)
        if rgb is None:
            return hex_color.lstrip('#')
        r, g, b = rgb
        return f"48;2;{r};{g};{b}"

    @classmethod
    def get_visible_length(cls, text: str) -> int:
        return visible_width(cls.parse(text))

    @classmethod
    def truncate(cls, text: str, max_width: int, suffix: str = "...") -> str:
        return truncate_ansi(cls.parse(text), max_width, suffix)



def style(text: str, style_str: str = "") -> str:
    if style_str:
        text = f"[{style_str}]{text}[/]"

    return StyleParser.parse(text)


def bold(text: str) -> str:
    return style(text, "bold")


def dim(text: str) -> str:
    return style(text, "dim")


def italic(text: str) -> str:
    return style(text, "italic")


def underline(text: str) -> str:
    return style(text, "underline")


def red(text: str) -> str:
    return style(text, "red")


def green(text: str) -> str:
    return style(text, "green")


def blue(text: str) -> str:
    return style(text, "blue")


def yellow(text: str) -> str:
    return style(text, "yellow")


def magenta(text: str) -> str:
    return style(text, "magenta")


def cyan(text: str) -> str:
    return style(text, "cyan")


def white(text: str) -> str:
    return style(text, "white")


def on_red(text: str) -> str:
    return style(text, "on red")


def on_green(text: str) -> str:
    return style(text, "on green")


def on_blue(text: str) -> str:
    return style(text, "on blue")


def on_yellow(text: str) -> str:
    return style(text, "on yellow")


def on_magenta(text: str) -> str:
    return style(text, "on magenta")


def on_cyan(text: str) -> str:
    return style(text, "on cyan")


def on_white(text: str) -> str:
    return style(text, "on white")


def on_black(text: str) -> str:
    return style(text, "on black")
