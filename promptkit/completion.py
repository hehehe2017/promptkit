from __future__ import annotations
from typing import Any, Literal

MatchMode = Literal["prefix", "fuzzy"]

class CompletionItem:

    def __init__(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self.text: str = text
        self.metadata: dict[str, Any] = metadata or {}
        self.match_indices: list[int] = []

    @property
    def description(self) -> str:
        return self.metadata.get("description", "")

    @property
    def display_text(self) -> str:
        return self.metadata.get("display_text", self.text)

    @property
    def type(self) -> str:
        return self.metadata.get("type", "")

    def __repr__(self) -> str:
        return f"CompletionItem(text='{self.text}', metadata={self.metadata})"


def _fuzzy_match(query: str, text: str) -> tuple[float, list[int]]:
    if not query:
        return 0.0, []

    query_len = len(query)
    text_len = len(text)

    if query_len > text_len:
        return -1.0, []

    match_indices: list[int] = []
    text_pos = 0

    for qi in range(query_len):
        found = False
        while text_pos < text_len:
            if text[text_pos] == query[qi]:
                match_indices.append(text_pos)
                text_pos += 1
                found = True
                break
            text_pos += 1
        if not found:
            return -1.0, []

    score = 0.0

    if match_indices[0] == 0:
        score += 10.0

    for idx in match_indices:
        if idx == 0:
            pass
        elif text[idx - 1] in ('_', '-', '.', '/', ' '):
            score += 3.0
        elif idx > 0 and text[idx].isupper() and text[idx - 1].islower():
            score += 3.0

    for i in range(1, len(match_indices)):
        if match_indices[i] == match_indices[i - 1] + 1:
            score += 2.0

    if len(match_indices) >= 2:
        span = match_indices[-1] - match_indices[0] + 1
        gaps = span - len(match_indices)
        score -= gaps * 0.5

    score -= text_len * 0.1

    coverage = len(match_indices) / text_len
    score += coverage * 5.0

    return score, match_indices


def _fuzzy_match_optimal(query: str, text: str) -> tuple[float, list[int]]:
    if not query:
        return 0.0, []

    query_len = len(query)
    text_len = len(text)

    if query_len > text_len:
        return -1.0, []

    NEG_INF = float('-inf')
    dp: list[list[float]] = [[NEG_INF] * text_len for _ in range(query_len)]
    parent: list[list[int]] = [[-1] * text_len for _ in range(query_len)]

    for ti in range(text_len):
        if text[ti] == query[0]:
            s = 0.0
            if ti == 0:
                s += 10.0
            elif text[ti - 1] in ('_', '-', '.', '/', ' '):
                s += 3.0
            elif text[ti].isupper() and text[ti - 1].islower():
                s += 3.0
            s -= ti * 0.5
            s -= text_len * 0.1
            dp[0][ti] = s

    for qi in range(1, query_len):
        for ti in range(qi, text_len):
            if text[ti] != query[qi]:
                continue

            best_score = NEG_INF
            best_prev = -1

            for pt in range(qi - 1, ti):
                if dp[qi - 1][pt] == NEG_INF:
                    continue

                s = dp[qi - 1][pt]

                if ti == pt + 1:
                    s += 2.0

                gap = ti - pt - 1
                s -= gap * 0.5

                if text[ti - 1] in ('_', '-', '.', '/', ' '):
                    s += 3.0
                elif text[ti].isupper() and text[ti - 1].islower():
                    s += 3.0

                if s > best_score:
                    best_score = s
                    best_prev = pt

            if best_prev >= 0:
                dp[qi][ti] = best_score
                parent[qi][ti] = best_prev

    best_score = NEG_INF
    best_end = -1
    for ti in range(text_len):
        if dp[query_len - 1][ti] > best_score:
            best_score = dp[query_len - 1][ti]
            best_end = ti

    if best_end < 0:
        return -1.0, []

    indices: list[int] = []
    ti = best_end
    for qi in range(query_len - 1, -1, -1):
        indices.append(ti)
        ti = parent[qi][ti]
        if qi == 0:
            break

    indices.reverse()

    coverage = len(indices) / text_len
    best_score += coverage * 5.0

    return best_score, indices


class WordCompleter:

    def __init__(
        self,
        words: list[str],
        meta_dict: dict[str, str] | None = None,
        type_dict: dict[str, str] | None = None,
        ignore_case: bool = True,
        match_mode: MatchMode = "prefix",
    ) -> None:
        self.words: list[str] = words
        self.meta_dict: dict[str, str] = meta_dict or {}
        self.type_dict: dict[str, str] = type_dict or {}
        self.ignore_case: bool = ignore_case
        self.match_mode: MatchMode = match_mode

        self.completions: list[CompletionItem] = []
        for word in words:
            metadata: dict[str, str] = {}
            if word in self.meta_dict:
                metadata["description"] = self.meta_dict[word]
            if word in self.type_dict:
                metadata["type"] = self.type_dict[word]
            self.completions.append(CompletionItem(word, metadata))

    def get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        if not query:
            for item in self.completions:
                item.match_indices = []
            return self.completions[:limit] if limit else self.completions

        if query.endswith(" "):
            return []

        if self.match_mode == "fuzzy":
            return self._fuzzy_get_matches(query, limit)
        else:
            return self._prefix_get_matches(query, limit)

    def _prefix_get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        matches: list[tuple[int, CompletionItem]] = []
        query_lower = query.lower() if self.ignore_case else query
        query_has_at = query.startswith("@")
        query_has_slash = query.startswith("/")

        for item in self.completions:
            if item.text.startswith("@") and not query_has_at:
                continue
            if item.text.startswith("/") and not query_has_slash:
                continue
            text = item.text.lower() if self.ignore_case else item.text
            if text.startswith(query_lower):
                item.match_indices = list(range(len(query_lower)))
                matches.append((0, item))

        matches.sort(key=lambda x: x[1].text.lower())

        if limit is not None:
            return [item for _, item in matches[:limit]]
        else:
            return [item for _, item in matches]

    def _fuzzy_get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        matches: list[tuple[float, CompletionItem]] = []
        query_lower = query.lower() if self.ignore_case else query
        query_has_at = query.startswith("@")
        query_has_slash = query.startswith("/")

        for item in self.completions:
            if item.text.startswith("@") and not query_has_at:
                continue
            if item.text.startswith("/") and not query_has_slash:
                continue
            text = item.text.lower() if self.ignore_case else item.text

            score, indices = _fuzzy_match_optimal(query_lower, text)

            if score >= 0:
                item.match_indices = indices
                matches.append((score, item))

        matches.sort(key=lambda x: (-x[0], x[1].text.lower()))

        if limit is not None:
            return [item for _, item in matches[:limit]]
        else:
            return [item for _, item in matches]

    def get_last_word(self, text: str) -> str:
        words = text.split()
        return words[-1] if words else ""


class Completer:

    def __init__(
        self,
        completions: list[CompletionItem],
        match_mode: MatchMode = "prefix",
    ) -> None:
        self.completions: list[CompletionItem] = completions
        self.match_mode: MatchMode = match_mode

    def get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        if not query:
            for item in self.completions:
                item.match_indices = []
            return self.completions[:limit] if limit else self.completions

        if query.endswith(" "):
            return []

        if self.match_mode == "fuzzy":
            return self._fuzzy_get_matches(query, limit)
        else:
            return self._prefix_get_matches(query, limit)

    def _prefix_get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        matches: list[tuple[int, CompletionItem]] = []
        query_lower = query.lower()

        for item in self.completions:
            text_lower = item.text.lower()
            if text_lower.startswith(query_lower):
                item.match_indices = list(range(len(query_lower)))
                matches.append((0, item))

        matches.sort(key=lambda x: x[1].text.lower())

        if limit is not None:
            return [item for _, item in matches[:limit]]
        else:
            return [item for _, item in matches]

    def _fuzzy_get_matches(self, query: str, limit: int | None = None) -> list[CompletionItem]:
        matches: list[tuple[float, CompletionItem]] = []
        query_lower = query.lower()

        for item in self.completions:
            text_lower = item.text.lower()
            score, indices = _fuzzy_match_optimal(query_lower, text_lower)

            if score >= 0:
                item.match_indices = indices
                matches.append((score, item))

        matches.sort(key=lambda x: (-x[0], x[1].text.lower()))

        if limit is not None:
            return [item for _, item in matches[:limit]]
        else:
            return [item for _, item in matches]

    def get_last_word(self, text: str) -> str:
        words = text.split()
        return words[-1] if words else ""
