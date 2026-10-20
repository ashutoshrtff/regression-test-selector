#!/usr/bin/env python3
"""
itaf.parsers.message_parser - Financial message format parser (ISO 20022 pacs.008 / JSON payment specs).

Extracts data integrity requirements, mandatory business elements, and schema constraints.
"""

import json
import os
from typing import Any, Dict, List, Optional

from itaf.core.models import (
    Requirement,
    ExpectedOutcome,
    RequirementType,
    RequirementOrigin,
    RuleSeverity,
    Provenance
)


class MessageFormatParser:
    """Parses payment and banking message format specifications."""

    def __init__(self, filepath: str, domain: str = "PAYMENTS", service: str = "payment-service"):
        self.filepath = os.path.abspath(filepath)
        self.domain = domain
        self.service = service
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Message format file not found: {self.filepath}")

        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            self.content = f.read()

    def parse(self) -> List[Requirement]:
        requirements: List[Requirement] = []
        doc = {}
        try:
            doc = json.loads(self.content)
        except json.JSONDecodeError:
            pass

        msg_type = doc.get("message_type") or doc.get("standard") or "ISO20022-pacs.008"
        mandatory_fields = doc.get("mandatory_fields", ["amount", "currency", "debtorAccount", "creditorAccount"])
        interface = doc.get("interface", "POST /api/v1/payments")

        req_id = f"REQ-MSG-{msg_type.replace('.', '_').replace('-', '_').upper()}-INTEGRITY"
        outcomes = []

        for field_name in mandatory_fields:
            outcomes.append(ExpectedOutcome(
                outcome_id=f"OUT-MSG-{field_name.upper()}-REQUIRED",
                requirement_id=req_id,
                outcome_type=RequirementType.DATA_INTEGRITY,
                description=f"Field '{field_name}' is mandatory in {msg_type}; missing or null value must be rejected.",
                target_interface=interface,
                expected_status_code=400,
                required_assertions=[f"error_details contains '{field_name}'"],
                provenance=Provenance(
                    artifact_path=self.filepath,
                    artifact_type="MESSAGE_SPEC",
                    identifier=field_name
                )
            ))

        requirements.append(Requirement(
            requirement_id=req_id,
            title=f"Message Format & Mandatory Elements: {msg_type}",
            description=f"Enforce mandatory presence and semantic validity of required business fields according to {msg_type}.",
            req_type=RequirementType.DATA_INTEGRITY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain=self.domain,
            service=self.service,
            interface=interface,
            mandatory=True,
            severity=RuleSeverity.BLOCKER,
            applicable_rule_ids=["GATE-PAY-003"],
            expected_outcomes=outcomes,
            acceptance_criteria=[
                f"Verify presence and schema of all mandatory fields: {', '.join(mandatory_fields)}.",
                "Reject payloads with missing mandatory fields with HTTP 400 Bad Request."
            ],
            provenance=Provenance(
                artifact_path=self.filepath,
                artifact_type="MESSAGE_SPEC",
                identifier=msg_type
            )
        ))

        return requirements
