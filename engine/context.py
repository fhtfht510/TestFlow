"""Variable context, template rendering, and JSONPath extraction."""

from __future__ import annotations

import random
import re
import string
import time
import uuid
from datetime import datetime
from typing import Any

_VAR_PATTERN = re.compile(r"\{\{\s*(\$[a-zA-Z0-9_]+(?:\([^)]*\))?|[a-zA-Z0-9_.-]+)\s*\}\}")
_EXACT_VAR_PATTERN = re.compile(r"^\{\{\s*(\$[a-zA-Z0-9_]+(?:\([^)]*\))?|[a-zA-Z0-9_.-]+)\s*\}\}$")
_PATH_TOKEN_PATTERN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _eval_builtin(token: str) -> tuple[bool, Any]:
    """Evaluate built-in dynamic functions like $timestamp, $uuid, $random_int(1,100)."""
    if not token.startswith("$"):
        return False, None
    m = re.match(r"^\$([a-zA-Z0-9_]+)(?:\(([^)]*)\))?$", token)
    if not m:
        return False, None
    fn = m.group(1).lower()
    raw_args = m.group(2)

    if fn == "timestamp":
        return True, int(time.time())
    if fn == "timestamp_ms":
        return True, int(time.time() * 1000)
    if fn == "uuid":
        return True, str(uuid.uuid4())
    if fn == "date":
        return True, datetime.now().strftime("%Y-%m-%d")
    if fn == "datetime":
        return True, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if fn == "random_int":
        lo, hi = 1000, 9999
        if raw_args:
            parts = [p.strip() for p in raw_args.split(",") if p.strip()]
            try:
                if len(parts) == 2:
                    lo, hi = int(parts[0]), int(parts[1])
                elif len(parts) == 1:
                    hi = int(parts[0])
                    lo = 0
            except ValueError:
                lo, hi = 1000, 9999
        if lo > hi:
            lo, hi = hi, lo
        return True, random.randint(lo, hi)
    if fn == "random_str":
        length = 8
        if raw_args and raw_args.strip():
            try:
                length = int(raw_args.strip())
            except ValueError:
                length = 8
        length = max(1, min(length, 128))
        alphabet = string.ascii_letters + string.digits
        return True, "".join(random.choices(alphabet, k=length))
    return False, None


class TestContext:
    """Holds environment and runtime-extracted variables for a test case."""

    __test__ = False

    def __init__(self, initial_vars: dict[str, Any] | None = None) -> None:
        self.variables: dict[str, Any] = dict(initial_vars or {})
        self.http_session: Any = None

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def render(self, value: Any) -> Any:
        return render_template(value, self.variables)


def render_template(value: Any, variables: dict[str, Any]) -> Any:
    """Recursively replace {{var_name}} and {{$func(...)}} placeholders."""
    if isinstance(value, str):
        exact = _EXACT_VAR_PATTERN.match(value)
        if exact:
            key = exact.group(1)
            ok, dyn_val = _eval_builtin(key)
            if ok:
                return dyn_val
            if key in variables:
                return variables[key]

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            ok, dyn_val = _eval_builtin(key)
            if ok:
                return str(dyn_val)
            if key in variables:
                return str(variables[key])
            return match.group(0)

        return _VAR_PATTERN.sub(_replace, value)
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if isinstance(value, dict):
        return {k: render_template(v, variables) for k, v in value.items()}
    return value


def extract_json_path(data: Any, expr: str) -> Any:
    """Extract a value using a simple JSONPath expression like $.data.items[0].id."""
    if not expr:
        return None
    cleaned = expr.strip()
    if cleaned.startswith("$."):
        cleaned = cleaned[2:]
    elif cleaned.startswith("$"):
        cleaned = cleaned[1:]
    if not cleaned:
        return data

    current = data
    for match in _PATH_TOKEN_PATTERN.finditer(cleaned):
        key, idx = match.group(1), match.group(2)
        if key is not None:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        elif idx is not None:
            index = int(idx)
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
    return current
