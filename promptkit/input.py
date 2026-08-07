from __future__ import annotations

import sys
import os

_HAS_TERMIOS = False
_HAS_MSVCRT = False

try:
    import tty
    import termios
    _HAS_TERMIOS = True
except ImportError:
    pass

try:
    import msvcrt  # type: ignore[import-not-found]
    _HAS_MSVCRT = True
except ImportError:
    pass


class InputHandler:

    def __init__(self) -> None:
        self._mode: str = self._detect_mode()
        self.fd: int = -1
        if self._mode == "termios":
            try:
                self.fd = sys.stdin.fileno()
            except Exception:
                self._mode = "fallback"
        self._pending_paste: str | None = None
        self._leftover: bytes = b""

    @staticmethod
    def _detect_mode() -> str:
        if not sys.stdin.isatty():
            return "fallback"

        if _HAS_TERMIOS:
            return "termios"
        if _HAS_MSVCRT:
            return "msvcrt"
        return "fallback"

    def read_char(self, *, already_raw: bool = False) -> str:
        if self._mode == "termios":
            return self._read_char_termios(already_raw=already_raw)
        elif self._mode == "msvcrt":
            return self._read_char_msvcrt()
        else:
            return self._read_char_fallback()

    def _read_char_termios(self, *, already_raw: bool = False) -> str:
        import select

        if self._leftover:
            first_byte = self._leftover[:1]
            self._leftover = self._leftover[1:]
            return self._process_byte(first_byte, select, already_raw=already_raw)

        if already_raw:
            try:
                first_byte = os.read(self.fd, 1)
                if not first_byte:
                    return ''
                return self._process_raw_byte(first_byte, select)
            except Exception:
                return ''

        old_settings = termios.tcgetattr(self.fd)  # type: ignore[attr-defined]
        try:
            tty.setraw(self.fd)  # type: ignore[attr-defined]

            first_byte = os.read(self.fd, 1)
            if not first_byte:
                return ''

            return self._process_raw_byte(first_byte, select)

        except Exception:
            return ''
        finally:
            if _HAS_TERMIOS:
                try:
                    termios.tcsetattr(  # pyright: ignore[reportPossiblyUnboundVariable]
                        self.fd, termios.TCSADRAIN, old_settings,  # pyright: ignore[reportPossiblyUnboundVariable]
                    )
                except Exception:
                    pass

    def _process_raw_byte(self, first_byte: bytes, select: object) -> str:
        b0 = first_byte[0]

        if b0 >= 0xC0:
            needed = 1 if b0 < 0xE0 else (2 if b0 < 0xF0 else 3)
            buf = first_byte
            while needed > 0 and select.select([self.fd], [], [], 0.2)[0]:  # type: ignore[operator]
                buf += os.read(self.fd, 1)
                needed -= 1
            return buf.decode('utf-8', errors='replace')

        ch = first_byte.decode('utf-8', errors='replace')

        if ch == '\x1b':
            if not select.select([self.fd], [], [], 0.1)[0]:  # type: ignore[operator]
                return '\x1b'

            ch2_byte = os.read(self.fd, 1)
            ch2 = ch2_byte.decode('utf-8', errors='replace')

            if ch2 == '[':
                if not select.select([self.fd], [], [], 0.05)[0]:  # type: ignore[operator]
                    return '\x1b['
                ch3_byte = os.read(self.fd, 1)
                ch3 = ch3_byte.decode('utf-8', errors='replace')

                if ch3.isdigit():
                    rest = ch3
                    while select.select([self.fd], [], [], 0.05)[0]:  # type: ignore[operator]
                        next_byte = os.read(self.fd, 1)
                        next_ch = next_byte.decode('utf-8', errors='replace')
                        rest += next_ch
                        if next_ch.isalpha() or next_ch == '~':
                            break

                    full_seq = '\x1b[' + rest

                    if full_seq == '\x1b[200~':
                        self._pending_paste = self._read_paste_raw(select)
                        return '\x1b[200~'

                    return full_seq
                return '\x1b[' + ch3
            elif ch2 == 'O':
                if select.select([self.fd], [], [], 0.05)[0]:  # type: ignore[operator]
                    ch3_byte = os.read(self.fd, 1)
                    ch3 = ch3_byte.decode('utf-8', errors='replace')
                    return '\x1bO' + ch3
                return '\x1bO'
            else:
                return '\x1b' + ch2
        return ch

    def _read_paste_raw(self, select: object) -> str:
        buf = b""
        end_mark = b"\x1b[201~"
        while True:
            if not select.select([self.fd], [], [], 0.5)[0]:  # type: ignore[operator]
                if end_mark in buf:
                    break
                if not select.select([self.fd], [], [], 1.0)[0]:  # type: ignore[operator]
                    break
            chunk = os.read(self.fd, 4096)
            if not chunk:
                break
            buf += chunk
            if end_mark in buf:
                break

        idx = buf.find(end_mark)
        if idx >= 0:
            content = buf[:idx]
            after_end = idx + len(end_mark)
            if after_end < len(buf):
                self._leftover = buf[after_end:]
        else:
            content = buf

        text = content.decode('utf-8', errors='replace')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        return text

    def _process_byte(self, first_byte: bytes, select: object, already_raw: bool) -> str:
        b0 = first_byte[0]

        if b0 >= 0xC0:
            needed = 1 if b0 < 0xE0 else (2 if b0 < 0xF0 else 3)
            buf = first_byte
            while needed > 0 and self._leftover:
                buf += self._leftover[:1]
                self._leftover = self._leftover[1:]
                needed -= 1
            return buf.decode('utf-8', errors='replace')

        ch = first_byte.decode('utf-8', errors='replace')

        if ch == '\x1b':
            self._leftover = b""
            old_settings = termios.tcgetattr(self.fd)  # type: ignore[attr-defined]
            try:
                tty.setraw(self.fd)  # type: ignore[attr-defined]
                if select.select([self.fd], [], [], 0.1)[0]:  # type: ignore[operator]
                    return self._process_raw_byte(b'\x1b', select)
                return '\x1b'
            finally:
                if _HAS_TERMIOS:
                    try:
                        termios.tcsetattr(  # pyright: ignore[reportPossiblyUnboundVariable]
                            self.fd, termios.TCSADRAIN, old_settings,  # pyright: ignore[reportPossiblyUnboundVariable]
                        )
                    except Exception:
                        pass

        return ch

    def _read_char_msvcrt(self) -> str:
        ch = msvcrt.getwch()  # type: ignore[attr-defined]

        if ch == '\x00' or ch == '\xe0':
            ch2 = msvcrt.getwch()  # type: ignore[attr-defined]
            key_map: dict[str, str] = {
                'H': '\x1b[A',
                'P': '\x1b[B',
                'K': '\x1b[D',
                'M': '\x1b[C',
                'I': '\x1b[5~',
                'Q': '\x1b[6~',
                'G': '\x1b[F',
                'O': '\x1b[H',
            }
            return key_map.get(ch2) or ('\x00' + ch2)

        return ch

    def _read_char_fallback(self) -> str:
        try:
            line = input()
            if line:
                return line[0]
            return '\n'
        except EOFError:
            return '\x03'
        except KeyboardInterrupt:
            return '\x03'

    def is_enter(self, ch: str) -> bool:
        return ch == '\r' or ch == '\n'

    def is_tab(self, ch: str) -> bool:
        return ch == '\t'

    def is_backspace(self, ch: str) -> bool:
        return ch == '\x7f' or ch == '\x08'

    def is_ctrl_c(self, ch: str) -> bool:
        return ch == '\x03'

    def is_arrow_up(self, ch: str) -> bool:
        return ch == '\x1b[A'

    def is_arrow_down(self, ch: str) -> bool:
        return ch == '\x1b[B'

    def is_arrow_right(self, ch: str) -> bool:
        return ch == '\x1b[C'

    def is_arrow_left(self, ch: str) -> bool:
        return ch == '\x1b[D'

    def is_space(self, ch: str) -> bool:
        return ch == ' '

    def is_printable(self, ch: str) -> bool:
        return bool(ch) and ch.isprintable() and ch != '\x1b'

    def is_escape(self, ch: str) -> bool:
        return ch == '\x1b'

    def is_paste_start(self, ch: str) -> bool:
        return ch == '\x1b[200~'

    def is_paste_end(self, ch: str) -> bool:
        return ch == '\x1b[201~'

    def read_paste_content(self) -> str:
        if self._pending_paste is not None:
            text = self._pending_paste
            self._pending_paste = None
            return text
        return ""

    def is_ctrl_arrow_right(self, ch: str) -> bool:
        return ch in ('\x1b[1;5C', '\x1bOc')

    _resize_detected: bool = False

    def check_resize(self) -> bool:
        if self._resize_detected:
            self._resize_detected = False
            return True
        return False

    def set_resize_flag(self) -> None:
        self._resize_detected = True

    def read_char_with_resize_check(self, timeout: float = 0.5) -> str:
        if self._mode == "termios":
            return self._read_char_with_resize_termios(timeout)
        elif self._mode == "msvcrt":
            import select as _select
            if _select.select([self.fd], [], [], 0.0)[0]:
                return self._read_char_msvcrt()
            return '\x00'
        else:
            return self._read_char_fallback()

    def _read_char_with_resize_termios(self, timeout: float) -> str:
        import select

        old_settings = termios.tcgetattr(self.fd)  # type: ignore[attr-defined]
        try:
            tty.setraw(self.fd)  # type: ignore[attr-defined]

            while True:
                if self._resize_detected:
                    self._resize_detected = False
                    termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
                    return '\x00RESIZE'

                rlist, _, _ = select.select([self.fd], [], [], timeout)
                if rlist:
                    first_byte = os.read(self.fd, 1)
                    if not first_byte:
                        termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
                        return ''
                    result = self._process_raw_byte(first_byte, select)
                    termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
                    return result

        except Exception:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
            except Exception:
                pass
            return ''

    RESIZE_SENTINEL = '\x00RESIZE'
