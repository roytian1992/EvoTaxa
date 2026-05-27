from __future__ import annotations

import ast
import re
from typing import Any


try:  # pragma: no cover - runtime dependent
    import tomllib as _tomllib
except ModuleNotFoundError:  # pragma: no cover - runtime dependent
    _tomllib = None


def loads(text: str) -> dict[str, Any]:
    if _tomllib is not None:
        return _tomllib.loads(text)
    return _minimal_loads(text)


def load(handle: Any) -> dict[str, Any]:
    raw = handle.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return loads(str(raw))


def _minimal_loads(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current = data
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            path = [part.strip() for part in line[1:-1].split(".") if part.strip()]
            if not path:
                raise ValueError(f"Invalid TOML table at line {line_no}")
            current = data
            for part in path:
                current = current.setdefault(part, {})
                if not isinstance(current, dict):
                    raise ValueError(f"Cannot redefine TOML scalar as table at line {line_no}")
            continue
        if "=" not in line:
            raise ValueError(f"Invalid TOML assignment at line {line_no}")
        key, value = line.split("=", 1)
        key = key.strip().strip('"').strip("'")
        current[key] = _parse_value(value.strip(), line_no)
    return data


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if char == "\\" and in_double and not escaped:
            escaped = True
            continue
        if char == '"' and not in_single and not escaped:
            in_double = not in_double
        elif char == "'" and not in_double:
            in_single = not in_single
        elif char == "#" and not in_single and not in_double:
            return line[:index]
        escaped = False
    return line


def _parse_value(value: str, line_no: int) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?\d+\.\d+", value):
        return float(value)
    if value.startswith("[") or value.startswith("{") or value.startswith('"') or value.startswith("'"):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Invalid TOML literal at line {line_no}: {value}") from exc
    return value
