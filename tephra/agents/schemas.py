"""JSON schemas for Gemini structured output, and tolerant parsing of what comes back.

Gemini accepts a subset of JSON Schema (types, ``properties``, ``required``, ``items``,
``enum``, ``minimum``/``maximum``, ``minItems``/``maxItems``, ``prefixItems``, ``anyOf``,
``description``, ``format: date-time``). Pydantic emits more than that (``$defs``/``$ref``,
``title``, ``default``, ``exclusiveMinimum``...), so the schema is inlined and filtered here.
The pydantic model stays the real contract: every response is validated against it.
"""

import re
from typing import Any

from pydantic import BaseModel, ValidationError

__all__ = ["gemini_schema", "parse_json_model"]

_KEPT_KEYS = frozenset(
    {
        "type",
        "required",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "prefixItems",
        "anyOf",
        "description",
        "nullable",
    }
)
_FENCE = re.compile(r"^```[A-Za-z]*\s*(.*?)\s*```$", re.DOTALL)
_MAX_REPORTED_ERRORS = 6


def gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's validation JSON schema, inlined and reduced to what Gemini accepts."""
    raw = model.model_json_schema(mode="validation")
    return _clean(raw, raw.get("$defs", {}), ())


def parse_json_model[T: BaseModel](text: str, model: type[T]) -> T:
    """Parse model output into ``model``; tolerates code fences and stray prose around it."""
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced is not None:
        body = fenced.group(1).strip()
    if not body.startswith("{"):
        start, end = body.find("{"), body.rfind("}")
        if start == -1 or end < start:
            raise ValueError("no JSON object in model output")
        body = body[start : end + 1]
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        raise ValueError(f"{model.__name__}: {_error_summary(exc)}") from exc


def _clean(node: Any, defs: dict[str, Any], seen: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_clean(item, defs, seen) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        if name in seen:
            raise ValueError(f"recursive schema reference {name!r} cannot be inlined for Gemini")
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return _clean({**defs[name], **siblings}, defs, (*seen, name))
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            cleaned[key] = {name: _clean(sub, defs, seen) for name, sub in value.items()}
        elif key == "exclusiveMinimum":
            cleaned.setdefault("minimum", value)
        elif key == "exclusiveMaximum":
            cleaned.setdefault("maximum", value)
        elif key == "const":
            cleaned["enum"] = [value]
        elif key == "format":
            if value == "date-time":
                cleaned[key] = value
        elif key in _KEPT_KEYS:
            cleaned[key] = _clean(value, defs, seen)
    return cleaned


def _error_summary(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False)
    parts = [
        f"{'.'.join(str(loc) for loc in error['loc']) or '<root>'}: {error['msg']}"
        for error in errors[:_MAX_REPORTED_ERRORS]
    ]
    if len(errors) > _MAX_REPORTED_ERRORS:
        parts.append(f"... {len(errors) - _MAX_REPORTED_ERRORS} more")
    return "; ".join(parts)
