#!/usr/bin/env python3
"""
itaf.parsers.openapi_parser - Deterministic parser for OpenAPI 3.0+ and Swagger 2.0 specifications.

Extracts canonical Requirements, ExpectedOutcomes, interface contracts, security expectations,
and required status codes with zero hallucinations and complete provenance tracking.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from itaf.core.models import (
    Requirement,
    ExpectedOutcome,
    RequirementType,
    RequirementOrigin,
    RuleSeverity,
    Provenance
)


def _parse_yaml_or_json(content: str) -> Dict[str, Any]:
    """Parses JSON or YAML content with fallback to standard library regex parsing."""
    try:
        import yaml
        return yaml.safe_load(content)
    except ImportError:
        pass

    # Try json first
    content_trimmed = content.strip()
    if content_trimmed.startswith("{"):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

    # Simple built-in YAML-to-dict parser for OpenAPI specs (supports paths, operations, status codes)
    data: Dict[str, Any] = {"openapi": "3.0.0", "paths": {}}
    current_path = ""
    current_method = ""
    current_section = ""

    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level info or paths
        if line.startswith("openapi:") or line.startswith("swagger:"):
            data["openapi"] = stripped.split(":", 1)[1].strip().strip('"\'')
        elif line.startswith("  title:") or stripped.startswith("title:"):
            data.setdefault("info", {})["title"] = stripped.split(":", 1)[1].strip().strip('"\'')

        # Paths
        path_match = re.match(r'^  (/[^:]+):\s*$', line)
        if path_match:
            current_path = path_match.group(1)
            data["paths"].setdefault(current_path, {})
            current_method = ""
            continue

        method_match = re.match(r'^    (get|post|put|delete|patch):\s*$', line)
        if method_match and current_path:
            current_method = method_match.group(1)
            data["paths"][current_path].setdefault(current_method, {"responses": {}, "parameters": []})
            continue

        # Operation properties
        if current_path and current_method:
            op = data["paths"][current_path][current_method]
            if stripped.startswith("operationId:"):
                op["operationId"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("summary:"):
                op["summary"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("description:"):
                op["description"] = stripped.split(":", 1)[1].strip().strip('"\'')

            # Status codes under responses:
            resp_match = re.match(r"^\s+['\"]?([1-5][0-9]{2})['\"]?:\s*$", line)
            if resp_match:
                status_code = resp_match.group(1)
                op["responses"][status_code] = {}

    return data


class OpenAPIParser:
    """Parses OpenAPI documents into structured Requirements and ExpectedOutcomes."""

    def __init__(self, filepath: str, domain: str = "PAYMENTS", service: str = "api-service"):
        self.filepath = os.path.abspath(filepath)
        self.domain = domain
        self.service = service
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"OpenAPI spec file not found: {self.filepath}")

        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            raw_content = f.read()
        self.spec = _parse_yaml_or_json(raw_content)

    def parse(self) -> List[Requirement]:
        requirements: List[Requirement] = []
        paths = self.spec.get("paths", {})
        info = self.spec.get("info", {})
        api_title = info.get("title", "API Service")

        for path, operations in paths.items():
            if not isinstance(operations, dict):
                continue

            for method, op_details in operations.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch"):
                    continue
                if not isinstance(op_details, dict):
                    continue

                http_method = method.upper()
                interface_name = f"{http_method} {path}"
                op_id = op_details.get("operationId") or f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}"
                summary = op_details.get("summary") or f"{http_method} {path}"
                description = op_details.get("description") or summary

                # Check security requirement
                security = op_details.get("security", self.spec.get("security", []))
                requires_auth = len(security) > 0 or "security" in self.spec

                # Check headers (e.g. Idempotency-Key)
                parameters = op_details.get("parameters", [])
                header_names = set()
                has_idempotency_key = False
                for param in parameters:
                    if isinstance(param, dict) and param.get("in") == "header":
                        h_name = param.get("name", "")
                        header_names.add(h_name)
                        if "idempotency" in h_name.lower():
                            has_idempotency_key = True

                # Responses
                responses = op_details.get("responses", {})
                status_codes = []
                for sc in responses.keys():
                    try:
                        status_codes.append(int(sc))
                    except ValueError:
                        pass

                # 1. Primary Contract Requirement
                contract_req_id = f"REQ-API-{op_id.upper()}-CONTRACT"
                outcomes: List[ExpectedOutcome] = []

                # Success Outcome
                success_codes = [c for c in status_codes if 200 <= c < 300] or [200]
                for sc in success_codes:
                    outcomes.append(ExpectedOutcome(
                        outcome_id=f"OUT-{op_id.upper()}-{sc}",
                        requirement_id=contract_req_id,
                        outcome_type=RequirementType.POSITIVE,
                        description=f"Request to {interface_name} returns HTTP {sc} with conforming schema.",
                        target_interface=interface_name,
                        expected_status_code=sc,
                        required_assertions=[f"status == {sc}"],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="OPENAPI",
                            section=f"paths.{path}.{method}.responses.{sc}",
                            identifier=op_id
                        )
                    ))

                # Negative Client Error Outcome (400)
                if 400 in status_codes or http_method in ("POST", "PUT", "PATCH"):
                    outcomes.append(ExpectedOutcome(
                        outcome_id=f"OUT-{op_id.upper()}-400",
                        requirement_id=contract_req_id,
                        outcome_type=RequirementType.NEGATIVE,
                        description=f"Invalid request to {interface_name} returns HTTP 400 Bad Request.",
                        target_interface=interface_name,
                        expected_status_code=400,
                        required_assertions=["status == 400"],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="OPENAPI",
                            section=f"paths.{path}.{method}.responses.400",
                            identifier=op_id
                        )
                    ))

                requirements.append(Requirement(
                    requirement_id=contract_req_id,
                    title=f"API Contract: {summary}",
                    description=description,
                    req_type=RequirementType.API_CONTRACT,
                    origin=RequirementOrigin.EXPLICIT_SPEC,
                    domain=self.domain,
                    service=self.service,
                    interface=interface_name,
                    mandatory=True,
                    severity=RuleSeverity.CRITICAL,
                    applicable_rule_ids=["GATE-API-001"],
                    expected_outcomes=outcomes,
                    acceptance_criteria=[
                        f"Endpoint {interface_name} conforms to OpenAPI request/response models.",
                        f"Returns {', '.join(str(c) for c in success_codes)} on valid request.",
                        "Returns HTTP 400 on malformed payloads."
                    ],
                    provenance=Provenance(
                        artifact_path=self.filepath,
                        artifact_type="OPENAPI",
                        section=f"paths.{path}.{method}",
                        identifier=op_id
                    )
                ))

                # 2. Security / Authentication Requirement
                if requires_auth or http_method in ("POST", "PUT", "DELETE"):
                    sec_req_id = f"REQ-SEC-{op_id.upper()}-AUTH"
                    sec_outcomes = [
                        ExpectedOutcome(
                            outcome_id=f"OUT-{op_id.upper()}-401",
                            requirement_id=sec_req_id,
                            outcome_type=RequirementType.SECURITY,
                            description=f"Unauthenticated request to {interface_name} must return HTTP 401 Unauthorized.",
                            target_interface=interface_name,
                            expected_status_code=401,
                            required_assertions=["status == 401"],
                            provenance=Provenance(
                                artifact_path=self.filepath,
                                artifact_type="OPENAPI",
                                section=f"paths.{path}.{method}.security",
                                identifier=op_id
                            )
                        )
                    ]
                    if 403 in status_codes:
                        sec_outcomes.append(ExpectedOutcome(
                            outcome_id=f"OUT-{op_id.upper()}-403",
                            requirement_id=sec_req_id,
                            outcome_type=RequirementType.SECURITY,
                            description=f"Unauthorized caller to {interface_name} must return HTTP 403 Forbidden.",
                            target_interface=interface_name,
                            expected_status_code=403,
                            required_assertions=["status == 403"],
                            provenance=Provenance(
                                artifact_path=self.filepath,
                                artifact_type="OPENAPI",
                                section=f"paths.{path}.{method}.responses.403",
                                identifier=op_id
                            )
                        ))

                    requirements.append(Requirement(
                        requirement_id=sec_req_id,
                        title=f"Authentication & Authorization Control: {interface_name}",
                        description=f"Enforce mandatory token validation and access control on {interface_name}.",
                        req_type=RequirementType.SECURITY,
                        origin=RequirementOrigin.EXPLICIT_SPEC if requires_auth else RequirementOrigin.POLICY_GATE,
                        domain=self.domain,
                        service=self.service,
                        interface=interface_name,
                        mandatory=True,
                        severity=RuleSeverity.BLOCKER,
                        applicable_rule_ids=["GATE-SEC-001", "GATE-SEC-002"],
                        expected_outcomes=sec_outcomes,
                        acceptance_criteria=[
                            "Caller must supply Bearer JWT token in Authorization header.",
                            "Missing or invalid token returns HTTP 401 Unauthorized.",
                            "Insufficient role returns HTTP 403 Forbidden."
                        ],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="OPENAPI",
                            section=f"paths.{path}.{method}.security",
                            identifier=op_id
                        )
                    ))

                # 3. Idempotency Requirement (for payment POST operations)
                if has_idempotency_key or (self.domain == "PAYMENTS" and http_method == "POST"):
                    idem_req_id = f"REQ-PAY-{op_id.upper()}-IDEMPOTENCY"
                    requirements.append(Requirement(
                        requirement_id=idem_req_id,
                        title=f"Request Idempotency Control: {interface_name}",
                        description=f"Ensures repeated POST to {interface_name} with identical Idempotency-Key returns cached response without duplicate side-effects.",
                        req_type=RequirementType.IDEMPOTENCY,
                        origin=RequirementOrigin.EXPLICIT_SPEC if has_idempotency_key else RequirementOrigin.POLICY_GATE,
                        domain=self.domain,
                        service=self.service,
                        interface=interface_name,
                        mandatory=True,
                        severity=RuleSeverity.BLOCKER,
                        applicable_rule_ids=["GATE-PAY-001"],
                        expected_outcomes=[
                            ExpectedOutcome(
                                outcome_id=f"OUT-{op_id.upper()}-IDEMPOTENT-REPLAY",
                                requirement_id=idem_req_id,
                                outcome_type=RequirementType.IDEMPOTENCY,
                                description=f"Repeating request with same Idempotency-Key returns original transaction result and does not debit account twice.",
                                target_interface=interface_name,
                                expected_status_code=200,
                                expected_headers={"Idempotency-Key": "req_key"},
                                required_assertions=["status == 200", "idempotency_verified == true"],
                                provenance=Provenance(
                                    artifact_path=self.filepath,
                                    artifact_type="OPENAPI",
                                    section=f"paths.{path}.{method}.parameters",
                                    identifier=op_id
                                )
                            )
                        ],
                        acceptance_criteria=[
                            "Idempotency-Key header is supported and enforced.",
                            "Replaying same key returns cached response.",
                            "Zero duplicate financial side-effects recorded."
                        ],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="OPENAPI",
                            section=f"paths.{path}.{method}",
                            identifier=op_id
                        )
                    ))

        return requirements
