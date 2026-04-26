import re
from typing import Any

from workflow_engine.domain.errors import InputMappingError

TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")


def render_inputs(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {key: _render_value(value, context) for key, value in inputs.items()}


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        matches = list(TEMPLATE_PATTERN.finditer(value))
        if not matches:
            return value
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return _resolve_path(matches[0].group(1), context)
        return TEMPLATE_PATTERN.sub(
            lambda match: str(_resolve_path(match.group(1), context)),
            value,
        )
    if isinstance(value, dict):
        return {key: _render_value(inner, context) for key, inner in value.items()}
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    return value


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    clean_path = path.strip()
    for part in clean_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise InputMappingError(f"Missing input mapping path: {clean_path}")
    return current
