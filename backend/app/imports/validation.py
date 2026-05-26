from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from backend.app.imports.file_classifier import classify_filename, classify_output_path
from backend.app.imports.schema_registry import SchemaRegistry


@dataclass(frozen=True)
class ValidationOutcome:
    status: str
    schema_name: str | None
    error_count: int
    errors: list[dict[str, Any]]
    reason_codes: list[str]
    data: dict[str, Any] | list[Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "schema_validation_passed"


def _json_path(error: ValidationError) -> str:
    if not error.absolute_path:
        return "$"
    return "$." + ".".join(str(part) for part in error.absolute_path)


def _reason_code(error: ValidationError) -> str:
    if error.validator == "required":
        return "missing_required_field"
    if error.validator == "additionalProperties":
        return "additional_property"
    if error.validator == "enum":
        return "invalid_enum"
    if error.validator in {"minimum", "maximum"}:
        return "invalid_range"
    if error.validator == "format":
        return f"invalid_{error.validator_value}"
    return "schema_validation_failed"


class JsonValidationService:
    def __init__(self, registry: SchemaRegistry | None = None) -> None:
        self.registry = registry or SchemaRegistry()

    def validate_file(self, path: Path, *, relative_path: str | None = None) -> ValidationOutcome:
        schema_name = classify_output_path(relative_path) if relative_path is not None else classify_filename(path.name)
        if schema_name is None:
            label = relative_path or path.name
            return ValidationOutcome(
                status="unknown_file_type",
                schema_name=None,
                error_count=1,
                errors=[
                    {
                        "path": "$",
                        "message": f"No schema is registered for filename '{label}'.",
                        "reason_code": "unknown_file_type",
                    }
                ],
                reason_codes=["unknown_file_type"],
            )

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except JSONDecodeError as exc:
            return ValidationOutcome(
                status="invalid_json",
                schema_name=schema_name,
                error_count=1,
                errors=[
                    {
                        "path": "$",
                        "message": exc.msg,
                        "line": exc.lineno,
                        "column": exc.colno,
                        "reason_code": "invalid_json",
                    }
                ],
                reason_codes=["invalid_json"],
            )
        except OSError as exc:
            return ValidationOutcome(
                status="file_read_failed",
                schema_name=schema_name,
                error_count=1,
                errors=[
                    {
                        "path": "$",
                        "message": str(exc),
                        "reason_code": "file_read_failed",
                    }
                ],
                reason_codes=["file_read_failed"],
            )

        validator = self.registry.get_validator(schema_name)
        validation_errors = sorted(validator.iter_errors(data), key=lambda error: list(error.absolute_path))
        if validation_errors:
            errors = []
            reason_codes = []
            for error in validation_errors:
                reason_code = _reason_code(error)
                reason_codes.append(reason_code)
                errors.append(
                    {
                        "path": _json_path(error),
                        "message": error.message,
                        "validator": error.validator,
                        "reason_code": reason_code,
                    }
                )
            return ValidationOutcome(
                status="schema_validation_failed",
                schema_name=schema_name,
                error_count=len(errors),
                errors=errors,
                reason_codes=sorted(set(reason_codes)),
                data=data,
            )

        return ValidationOutcome(
            status="schema_validation_passed",
            schema_name=schema_name,
            error_count=0,
            errors=[],
            reason_codes=["schema_validation_passed"],
            data=data,
        )
