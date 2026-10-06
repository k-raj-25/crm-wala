from __future__ import annotations

import re
from typing import Annotated, Any, Optional, Type, TypeVar

from flask import request
from pydantic import AfterValidator, BaseModel, ConfigDict, create_model, model_validator

from app.core.errors import bad_request

T = TypeVar("T", bound=BaseModel)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address")
    return v


Email = Annotated[str, AfterValidator(_check_email)]


class Schema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and not v.strip() else v) for k, v in data.items()}
        return data


def parse(schema: Type[T], data: Any = None) -> T:
    """Validate JSON body (or provided data). Pydantic errors become 422 via the global handler."""
    if data is None:
        data = request.get_json(silent=True)
        if data is None:
            raise bad_request("Request body must be valid JSON", "invalid_json")
    return schema.model_validate(data)


def patchify(schema: Type[BaseModel], name: str | None = None) -> Type[BaseModel]:
    """Make every field optional (PATCH semantics). Use `.model_fields_set` for the provided keys."""
    fields: dict[str, Any] = {}
    for k, f in schema.model_fields.items():
        fields[k] = (Optional[f.annotation], None)
    return create_model(name or f"{schema.__name__}Patch", __base__=Schema, **fields)


def provided(model: BaseModel) -> dict[str, Any]:
    return {k: getattr(model, k) for k in model.model_fields_set}
