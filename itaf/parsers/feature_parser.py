#!/usr/bin/env python3
"""
itaf.parsers.feature_parser - Parses Feature descriptions, User Stories, and MVDs.

Extracts structured requirements, acceptance criteria, resilience expectations,
and business duplicate detection rules with line-level provenance and ambiguity detection.
"""

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

JIRA_KEY_REGEX = re.compile(r'\b([A-Z]{2,10}-\d+)\b')


class FeatureParser:
    """Parses Markdown / text feature specs, User Stories, and MVD documents."""

    def __init__(self, filepath: str, domain: str = "PAYMENTS", service: str = "payment-service"):
        self.filepath = os.path.abspath(filepath)
        self.domain = domain
        self.service = service
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Feature document not found: {self.filepath}")

        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            self.content = f.read()

    def parse(self) -> List[Requirement]:
        requirements: List[Requirement] = []
        lines = self.content.splitlines()

        # Find Jira keys
        jira_keys = set(JIRA_KEY_REGEX.findall(self.content))
        primary_jira = sorted(list(jira_keys))[0] if jira_keys else "REQ-FEAT"

        # Track sections
        current_section = ""
        current_req: Optional[Requirement] = None
        target_interface = "POST /api/v1/payments" # default heuristic if not stated

        # Scan for explicit interface in document
        interface_match = re.search(r'(POST|GET|PUT|DELETE|PATCH)\s+(/[a-zA-Z0-9_\-\/\{\}]+)', self.content)
        if interface_match:
            target_interface = f"{interface_match.group(1)} {interface_match.group(2)}"

        # Check for Business Duplicate Detection
        has_dup_spec = re.search(r'(duplicate\s+(?:detection|prevention|check|transaction)|velocity\s+window|409\s+conflict)', self.content, re.IGNORECASE)
        if has_dup_spec:
            req_id = f"{primary_jira}-DUPLICATE-DETECTION"
            line_no = self.content[:has_dup_spec.start()].count("\n") + 1
            requirements.append(Requirement(
                requirement_id=req_id,
                title="Business Duplicate Detection Control",
                description="Reject separate submissions that represent the identical financial transaction within the velocity window.",
                req_type=RequirementType.DUPLICATE_DETECTION,
                origin=RequirementOrigin.EXPLICIT_SPEC,
                domain=self.domain,
                service=self.service,
                interface=target_interface,
                mandatory=True,
                severity=RuleSeverity.BLOCKER,
                applicable_rule_ids=["GATE-PAY-002"],
                expected_outcomes=[
                    ExpectedOutcome(
                        outcome_id=f"OUT-{primary_jira}-DUP-409",
                        requirement_id=req_id,
                        outcome_type=RequirementType.DUPLICATE_DETECTION,
                        description="Second payment submission with identical business fields returns HTTP 409 Conflict.",
                        target_interface=target_interface,
                        expected_status_code=409,
                        expected_error_code="DUPLICATE_PAYMENT",
                        required_assertions=["status == 409", "errorCode == 'DUPLICATE_PAYMENT'"],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="FEATURE_SPEC",
                            line_number=line_no,
                            identifier=primary_jira
                        )
                    )
                ],
                acceptance_criteria=[
                    "Detect identical recipient, amount, and reference within velocity window.",
                    "Return HTTP 409 Conflict with DUPLICATE_PAYMENT code.",
                    "Do not execute duplicate debit."
                ],
                provenance=Provenance(
                    artifact_path=self.filepath,
                    artifact_type="FEATURE_SPEC",
                    line_number=line_no,
                    identifier=primary_jira
                )
            ))

        # Check for Resilience & Retry requirement
        has_retry_spec = re.search(r'(retry\s+(?:behaviour|policy|logic|mechanism)|transient\s+failure|503|backoff|downstream\s+timeout)', self.content, re.IGNORECASE)
        if has_retry_spec:
            req_id = f"{primary_jira}-RETRY-RECOVERY"
            line_no = self.content[:has_retry_spec.start()].count("\n") + 1

            # Check for ambiguity: are backoff intervals and max retries specified?
            ambiguity_notes = []
            if not re.search(r'(?:max\s+retries|attempt|\b3\s+times|exponential\s+backoff)', self.content, re.IGNORECASE):
                ambiguity_notes.append("Retry behavior is mandated but maximum attempt limit or backoff interval is not specified.")

            requirements.append(Requirement(
                requirement_id=req_id,
                title="Transient Failure Retry and Recovery",
                description="Automatically retry requests when downstream schemes return transient 503 errors or gateway timeouts.",
                req_type=RequirementType.RESILIENCE_RETRY,
                origin=RequirementOrigin.EXPLICIT_SPEC,
                domain=self.domain,
                service=self.service,
                interface=target_interface,
                mandatory=True,
                severity=RuleSeverity.BLOCKER,
                applicable_rule_ids=["GATE-RET-001", "GATE-RET-002"],
                expected_outcomes=[
                    ExpectedOutcome(
                        outcome_id=f"OUT-{primary_jira}-RETRY-503-RECOVERY",
                        requirement_id=req_id,
                        outcome_type=RequirementType.RESILIENCE_RETRY,
                        description="Transient downstream 503 triggers automated retry with exponential backoff and succeeds upon downstream recovery.",
                        target_interface=target_interface,
                        expected_status_code=200,
                        required_assertions=["retry_count >= 1", "status == 200"],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="FEATURE_SPEC",
                            line_number=line_no,
                            identifier=primary_jira
                        )
                    ),
                    ExpectedOutcome(
                        outcome_id=f"OUT-{primary_jira}-RETRY-EXHAUSTION",
                        requirement_id=req_id,
                        outcome_type=RequirementType.RESILIENCE_RETRY,
                        description="Exhaustion of max retries returns HTTP 504 Gateway Timeout or 503 Service Unavailable with terminal error code.",
                        target_interface=target_interface,
                        expected_status_code=504,
                        required_assertions=["retry_count == 3", "status == 504"],
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="FEATURE_SPEC",
                            line_number=line_no,
                            identifier=primary_jira
                        )
                    )
                ],
                acceptance_criteria=[
                    "Automatically retry on HTTP 503 or network timeout.",
                    "Apply exponential backoff.",
                    "Cease retrying after configured maximum attempts."
                ],
                provenance=Provenance(
                    artifact_path=self.filepath,
                    artifact_type="FEATURE_SPEC",
                    line_number=line_no,
                    identifier=primary_jira
                ),
                ambiguity_notes=ambiguity_notes
            ))

        # Check for generic User Story / Feature sections if no specialized requirements were extracted
        if not requirements:
            section_matches = list(re.finditer(r'^###\s+(?:Requirement\s*\d*:\s*)?([^\n]+)', self.content, re.MULTILINE))
            for i, sm in enumerate(section_matches):
                sec_title = sm.group(1).strip()
                start_pos = sm.end()
                end_pos = section_matches[i+1].start() if i + 1 < len(section_matches) else len(self.content)
                sec_body = self.content[start_pos:end_pos].strip()
                line_no = self.content[:sm.start()].count("\n") + 1

                bullets = [b.strip("-* ").strip() for b in sec_body.splitlines() if b.strip().startswith(("-", "*"))]
                outcomes = []
                # Check for status codes in bullets
                for b_idx, b in enumerate(bullets):
                    status_m = re.search(r'HTTP\s+([1-5][0-9]{2})', b, re.IGNORECASE)
                    status_code = int(status_m.group(1)) if status_m else None
                    rtype = RequirementType.POSITIVE if status_code and status_code < 300 else (
                        RequirementType.SECURITY if status_code in (401, 403) else (
                            RequirementType.NEGATIVE if status_code and status_code >= 400 else RequirementType.FUNCTIONAL
                        )
                    )
                    outcomes.append(ExpectedOutcome(
                        outcome_id=f"OUT-{primary_jira}-SEC{i+1}-{b_idx+1}",
                        requirement_id=f"{primary_jira}-REQ-{i+1}",
                        outcome_type=rtype,
                        description=b,
                        target_interface=target_interface,
                        expected_status_code=status_code,
                        provenance=Provenance(
                            artifact_path=self.filepath,
                            artifact_type="FEATURE_SPEC",
                            line_number=line_no,
                            identifier=primary_jira
                        )
                    ))

                requirements.append(Requirement(
                    requirement_id=f"{primary_jira}-REQ-{i+1}",
                    title=sec_title,
                    description=bullets[0] if bullets else sec_title,
                    req_type=RequirementType.FUNCTIONAL,
                    origin=RequirementOrigin.EXPLICIT_SPEC,
                    domain=self.domain,
                    service=self.service,
                    interface=target_interface,
                    mandatory=True,
                    severity=RuleSeverity.MAJOR,
                    expected_outcomes=outcomes,
                    acceptance_criteria=bullets,
                    provenance=Provenance(
                        artifact_path=self.filepath,
                        artifact_type="FEATURE_SPEC",
                        line_number=line_no,
                        identifier=primary_jira
                    )
                ))

        return requirements
