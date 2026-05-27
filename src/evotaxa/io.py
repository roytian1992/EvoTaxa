from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path}:{line_no}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object in {path}:{line_no}")
            yield value


def read_json_or_jsonl(path: str | Path) -> Any:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return list(iter_jsonl(path))
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def slugify(text: str, *, max_len: int = 80) -> str:
    value = str(text or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    value = value[:max_len].strip("_")
    return value or "unknown"


def normalize_space(text: Any) -> str:
    return " ".join(str(text or "").split())


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def as_str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in listify(value) if str(item).strip()]


def get_path(row: dict[str, Any], path: str) -> Any:
    current: Any = row
    for part in str(path).split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def first_value(row: dict[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = get_path(row, field)
        if value not in (None, "", [], {}):
            return value
    return None


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}", raw):
        return date(int(raw), 1, 1)
    raw = raw.replace("/", "-")
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not match:
        return None
    year, month, day = [int(part) for part in match.groups()]
    try:
        return date(year, month, day)
    except ValueError:
        return None

