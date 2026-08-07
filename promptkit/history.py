from __future__ import annotations

from pathlib import Path


class History:

    def __init__(
        self,
        strings: list[str] | None = None,
        filepath: str | None = None,
        max_entries: int = 1000,
    ) -> None:
        self._entries: list[str] = list(strings) if strings else []
        self._filepath: str | None = filepath
        self._max_entries: int = max_entries
        self._position: int = len(self._entries)
        self._draft: str = ""

        if self._filepath:
            self._load_from_file()

    def _load_from_file(self) -> None:
        if not self._filepath:
            return
        try:
            path = Path(self._filepath)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                for line in lines:
                    stripped = line.rstrip("\n")
                    if stripped:
                        self._entries.append(stripped)
                if len(self._entries) > self._max_entries:
                    self._entries = self._entries[-self._max_entries:]
                self._position = len(self._entries)
        except Exception:
            pass

    def _save_to_file(self) -> None:
        if not self._filepath:
            return
        try:
            path = Path(self._filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._entries) + "\n")
        except Exception:
            pass

    def append(self, entry: str) -> None:
        if not entry or not entry.strip():
            return

        if self._entries and self._entries[-1] == entry:
            self._position = len(self._entries)
            self._draft = ""
            return

        self._entries.append(entry)

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._position = len(self._entries)
        self._draft = ""

        self._save_to_file()

    def up(self, current: str) -> str:
        if not self._entries:
            return current

        if self._position == len(self._entries):
            self._draft = current

        if self._position > 0:
            self._position -= 1

        return self._entries[self._position]

    def down(self) -> str:
        if not self._entries:
            return self._draft

        if self._position < len(self._entries):
            self._position += 1

        if self._position >= len(self._entries):
            return self._draft

        return self._entries[self._position]

    def reset(self) -> None:
        self._position = len(self._entries)
        self._draft = ""

    @property
    def entries(self) -> list[str]:
        return list(self._entries)

    @property
    def position(self) -> int:
        return self._position

    @property
    def is_navigating(self) -> bool:
        return self._position < len(self._entries)

    def get_suggestion(self, prefix: str) -> str | None:
        if not prefix or not prefix.strip():
            return None

        for entry in reversed(self._entries):
            if entry == prefix:
                continue
            if entry.startswith(prefix):
                suffix = entry[len(prefix):]
                nl = suffix.find("\n")
                if nl >= 0:
                    suffix = suffix[:nl]
                return suffix if suffix else None
        return None

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"History(entries={len(self._entries)}, position={self._position})"
