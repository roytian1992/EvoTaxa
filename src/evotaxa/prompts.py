from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_VAR_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    template: str
    task_variables: list[dict[str, Any]]
    static_variables: list[dict[str, Any]]
    source_path: Path
    raw: dict[str, Any]


class YAMLPromptLoader:
    """Load YAML prompt specs and render declared variables only."""

    def __init__(self, prompt_dir: str | Path | None = None, global_values: dict[str, Any] | None = None) -> None:
        self.prompt_dir = Path(prompt_dir) if prompt_dir else default_prompt_dir()
        self.prompt_dir = self.prompt_dir.expanduser().resolve()
        if not self.prompt_dir.exists():
            raise FileNotFoundError(f"Prompt dir not found: {self.prompt_dir}")
        self.global_values = dict(global_values or {})

    def load(self, prompt_id: str) -> PromptSpec:
        raw_id = str(prompt_id or "").strip()
        if not raw_id:
            raise ValueError("prompt_id must be non-empty")
        path = Path(raw_id)
        if path.is_absolute():
            return self._load_file(path)
        if raw_id.endswith((".yaml", ".yml")):
            return self._load_file(self.prompt_dir / raw_id)
        for candidate in [self.prompt_dir / f"{raw_id}.yaml", self.prompt_dir / f"{raw_id}.yml"]:
            if candidate.exists():
                return self._load_file(candidate)
        matches = list(self.prompt_dir.rglob(f"{raw_id}.yaml")) + list(self.prompt_dir.rglob(f"{raw_id}.yml"))
        if not matches:
            raise FileNotFoundError(f"Prompt id not found under {self.prompt_dir}: {prompt_id}")
        if len(matches) > 1:
            raise RuntimeError(f"Ambiguous prompt id {prompt_id}: {matches}")
        return self._load_file(matches[0])

    def render(
        self,
        prompt_id: str,
        values: dict[str, Any] | None = None,
        *,
        task_values: dict[str, Any] | None = None,
        static_values: dict[str, Any] | None = None,
        strict: bool = True,
    ) -> str:
        spec = self.load(prompt_id)
        merged: dict[str, Any] = {}
        merged.update(self.global_values)
        merged.update(static_values or {})
        merged.update(values or {})
        merged.update(task_values or {})
        declared = _declared_names(spec.task_variables) | _declared_names(spec.static_variables)
        if strict:
            required = _required_names(spec.task_variables) | _required_names(spec.static_variables)
            missing = sorted(name for name in required if name not in merged)
            if missing:
                raise ValueError(f"Missing prompt variables for {prompt_id}: {missing}")
        return _safe_replace(spec.template, declared=declared, values=merged)

    def _load_file(self, path: Path) -> PromptSpec:
        path = path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Prompt YAML must be an object: {path}")
        template = raw.get("template")
        if not isinstance(template, str) or not template.strip():
            raise ValueError(f"Prompt YAML missing template: {path}")
        task_variables = raw.get("task_variables") or []
        static_variables = raw.get("static_variables") or []
        if not isinstance(task_variables, list):
            raise ValueError(f"task_variables must be a list: {path}")
        if not isinstance(static_variables, list):
            raise ValueError(f"static_variables must be a list: {path}")
        return PromptSpec(
            prompt_id=str(raw.get("id") or path.stem),
            template=template,
            task_variables=[row for row in task_variables if isinstance(row, dict)],
            static_variables=[row for row in static_variables if isinstance(row, dict)],
            source_path=path,
            raw=raw,
        )


def default_prompt_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "task_specs" / "prompts"


def render_prompt(prompt_id: str, values: dict[str, Any] | None = None, *, prompt_dir: str | Path | None = None) -> str:
    return _loader(str(Path(prompt_dir).expanduser().resolve()) if prompt_dir else "").render(prompt_id, values or {})


@lru_cache(maxsize=16)
def _loader(prompt_dir_key: str) -> YAMLPromptLoader:
    return YAMLPromptLoader(prompt_dir_key or None)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _declared_names(rows: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(rows, list):
        return names
    for row in rows:
        if isinstance(row, dict) and str(row.get("name") or "").strip():
            names.add(str(row["name"]).strip())
    return names


def _required_names(rows: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(rows, list):
        return names
    for row in rows:
        if isinstance(row, dict) and row.get("required") is True and str(row.get("name") or "").strip():
            names.add(str(row["name"]).strip())
    return names


def _safe_replace(template: str, *, declared: set[str], values: dict[str, Any]) -> str:
    rendered = {name: _stringify(values.get(name)) for name in declared if name in values}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in declared:
            return match.group(0)
        return rendered.get(name, "")

    return _VAR_PATTERN.sub(replace, template)
