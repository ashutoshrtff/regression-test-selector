#!/usr/bin/env python3
"""
itaf.core.schemas - JSON Schema loading and validation.
Standard library fallback ensures zero pip dependencies.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "schemas"))


def load_schema(schema_name: str) -> Dict[str, Any]:
    """Loads a schema by name (e.g. 'policy-rule.schema.json')."""
    if not schema_name.endswith(".json"):
        schema_name = f"{schema_name}.schema.json"
    schema_path = os.path.join(SCHEMAS_DIR, schema_name)
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_dict(instance: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a dictionary instance against a JSON schema.
    Uses jsonschema if available, otherwise runs a thorough standard-library validation.
    Returns (is_valid, list_of_error_messages).
    """
    try:
        import jsonschema
        try:
            jsonschema.validate(instance=instance, schema=schema)
            return True, []
        except jsonschema.ValidationError as e:
            return False, [e.message]
    except ImportError:
        pass

    # Built-in lightweight validator for Python standard library
    errors = []
    
    # Check required fields
    required = schema.get("required", [])
    for req in required:
        if req not in instance:
            errors.append(f"Missing required property: '{req}'")

    properties = schema.get("properties", {})
    for prop, prop_schema in properties.items():
        if prop in instance:
            val = instance[prop]
            expected_type = prop_schema.get("type")
            
            # Type checks
            if expected_type == "string" and not isinstance(val, str):
                errors.append(f"Property '{prop}' expected string, got {type(val).__name__}")
            elif expected_type == "integer" and not isinstance(val, int):
                errors.append(f"Property '{prop}' expected integer, got {type(val).__name__}")
            elif expected_type == "boolean" and not isinstance(val, bool):
                errors.append(f"Property '{prop}' expected boolean, got {type(val).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                errors.append(f"Property '{prop}' expected array, got {type(val).__name__}")
            elif expected_type == "object" and not isinstance(val, dict):
                errors.append(f"Property '{prop}' expected object, got {type(val).__name__}")

            # Enum checks
            if "enum" in prop_schema and val not in prop_schema["enum"]:
                errors.append(f"Property '{prop}' has value '{val}' not in allowed enum: {prop_schema['enum']}")

            # Pattern check
            if "pattern" in prop_schema and isinstance(val, str):
                if not re.search(prop_schema["pattern"], val):
                    errors.append(f"Property '{prop}' ('{val}') does not match pattern {prop_schema['pattern']}")

    return (len(errors) == 0, errors)
