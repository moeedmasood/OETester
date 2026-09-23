"""Builds a dynamic Pydantic model from a list of user-defined fields.

Each field is a dict: {"name": str, "type": str, "description": str (optional)}.
Supported "type" values: str, int, float, bool, date.
"""
from datetime import date
from typing import Any, Optional, Type

from pydantic import BaseModel, Field, create_model

_TYPE_MAP: dict[str, type] = {
    "str": str,
    "text": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
    "date": date,
}


def resolve_field_type(type_name: str) -> type:
    return _TYPE_MAP.get((type_name or "str").strip().lower(), str)


def build_pydantic_model(model_name: str, fields: list[dict[str, Any]]) -> Type[BaseModel]:
    """Create a pydantic BaseModel subclass at runtime from field definitions."""
    field_definitions: dict[str, Any] = {}
    for f in fields:
        name = f["name"]
        py_type = resolve_field_type(f.get("type", "str"))
        description = f.get("description") or f"Value for {name}"
        field_definitions[name] = (
            Optional[py_type],
            Field(default=None, description=description),
        )

    return create_model(model_name, **field_definitions)  # type: ignore[call-overload, no-any-return]
