from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CleanedText:
    text: str
    original_length: int
    cleaned_length: int
    removed_length: int
    removed_markers: list[str]


_NOISE_PREFIX_PATTERNS = [
    ("previous_next", re.compile(r"^\s*(previousnext|return to issue\s*prev|prev\s*news\s*next)\b", re.IGNORECASE)),
    ("access_banner", re.compile(r"^\s*(no access|open access|full access)\b", re.IGNORECASE)),
]

_CUT_PATTERNS = [
    ("doi_url", re.compile(r"https?://doi\.org/\S+", re.IGNORECASE)),
    ("sections_about", re.compile(r"\bsections\s+about\b", re.IGNORECASE)),
    ("tools_menu", re.compile(r"\b(pdf/ePub|tools|add to favorites|download citations|track citations|permissions|share)\b", re.IGNORECASE)),
    ("cited_by", re.compile(r"\bcited by\b", re.IGNORECASE)),
    ("references", re.compile(r"\breferences\b", re.IGNORECASE)),
    ("related_details", re.compile(r"\brelated\s+details\b", re.IGNORECASE)),
    ("notes", re.compile(r"\bnotes\b", re.IGNORECASE)),
]


def clean_title_abstract(title: str, abstract: str) -> CleanedText:
    original = _normalize_whitespace(abstract)
    text = original
    markers: list[str] = []
    for marker, pattern in _NOISE_PREFIX_PATTERNS:
        updated = pattern.sub("", text).strip()
        if updated != text:
            markers.append(marker)
            text = updated
    for marker, pattern in _CUT_PATTERNS:
        match = pattern.search(text)
        if match and _should_cut_at_marker(text, match.start()):
            text = text[: match.start()].strip()
            markers.append(marker)
            break
    text = _remove_repeated_title_prefix(title=title, text=text, markers=markers)
    text = _strip_author_header(text, markers=markers)
    text = _strip_trailing_author_fragment(text, markers=markers)
    text = _normalize_whitespace(text)
    return CleanedText(
        text=text,
        original_length=len(original),
        cleaned_length=len(text),
        removed_length=max(0, len(original) - len(text)),
        removed_markers=markers,
    )


def _normalize_whitespace(text: str) -> str:
    return " ".join(str(text or "").split())


def _should_cut_at_marker(text: str, marker_index: int) -> bool:
    if marker_index <= 0:
        return False
    if marker_index < 300:
        return True
    remaining = len(text) - marker_index
    return remaining > 400 and remaining > len(text) * 0.25


def _remove_repeated_title_prefix(title: str, text: str, markers: list[str]) -> str:
    title = _normalize_whitespace(title)
    if not title:
        return text
    lower = text.lower()
    title_lower = title.lower()
    index = lower.find(title_lower)
    if index <= 0 or index > 220:
        return text
    prefix = text[:index].strip()
    if not prefix:
        return text
    noisy_prefix_terms = ["no access", "previousnext", "authors:", "doi", "abstracts", "expanded abstracts"]
    if any(term in prefix.lower() for term in noisy_prefix_terms):
        markers.append("repeated_title_prefix")
        return text[index:].strip()
    return text


def _strip_author_header(text: str, markers: list[str]) -> str:
    match = re.search(r"\bauthors?:\s+", text, flags=re.IGNORECASE)
    if not match or match.start() > 260:
        return text
    end_markers = [
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\babstract\b", re.IGNORECASE),
        re.compile(r"\bsections\b", re.IGNORECASE),
    ]
    after = text[match.end() :]
    cut_points = [m.start() for pattern in end_markers if (m := pattern.search(after))]
    if not cut_points:
        return text
    cut = match.end() + min(cut_points)
    markers.append("author_header")
    return (text[: match.start()] + " " + text[cut:]).strip()


def _strip_trailing_author_fragment(text: str, markers: list[str]) -> str:
    match = re.search(r"\bauthors?:\s+", text, flags=re.IGNORECASE)
    if not match:
        return text
    tail = text[match.start() :].strip()
    if len(tail) <= 180 and not re.search(r"[.!?]\s+\w", tail):
        markers.append("author_fragment")
        return text[: match.start()].strip()
    return text
