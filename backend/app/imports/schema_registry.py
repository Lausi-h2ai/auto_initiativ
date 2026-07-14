from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from backend.app.core.config import get_settings
from backend.app.imports.file_classifier import FILENAME_TO_SCHEMA, JOB_RESEARCH_DIRECTORY_TO_SCHEMA


class SchemaRegistry:
    def __init__(self, schemas_root: Path | None = None) -> None:
        self.schemas_root = schemas_root or get_settings().schemas_root
        self._schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft202012Validator] = {}

    @property
    def schema_names(self) -> tuple[str, ...]:
        return tuple(sorted(set(FILENAME_TO_SCHEMA.values()) | set(JOB_RESEARCH_DIRECTORY_TO_SCHEMA.values()) | {"application_answer_kit.schema.json"}))

    def load_all(self) -> None:
        for schema_name in self.schema_names:
            self.get_schema(schema_name)

    def get_schema(self, schema_name: str) -> dict[str, Any]:
        if schema_name not in self.schema_names:
            raise KeyError(f"Unknown schema: {schema_name}")
        if schema_name not in self._schemas:
            schema_path = self.schemas_root / schema_name
            with schema_path.open("r", encoding="utf-8") as file:
                self._schemas[schema_name] = json.load(file)
        return self._schemas[schema_name]

    def get_validator(self, schema_name: str) -> Draft202012Validator:
        if schema_name not in self._validators:
            schema = self.get_schema(schema_name)
            Draft202012Validator.check_schema(schema)
            self._validators[schema_name] = Draft202012Validator(schema, format_checker=FormatChecker())
        return self._validators[schema_name]
