#!/usr/bin/env python3
"""
itaf.core.models - Canonical Data Models for the Intelligent Test Assurance Framework.

Technology-neutral, auditable data classes with stable identifiers, versioned schemas,
provenance tracking, and distinct separation between:
- Business requirements vs expected outcomes vs policy rules
- Discovered tests vs assertions vs execution evidence
- Requirement coverage vs execution status vs mapping confidence
"""

import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class RequirementType(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    SECURITY = "SECURITY"
    IDEMPOTENCY = "IDEMPOTENCY"
    DUPLICATE_DETECTION = "DUPLICATE_DETECTION"
    RESILIENCE_RETRY = "RESILIENCE_RETRY"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    API_CONTRACT = "API_CONTRACT"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    OBSERVABILITY = "OBSERVABILITY"


class RequirementOrigin(str, Enum):
    EXPLICIT_SPEC = "EXPLICIT_SPEC"       # Directly stated in OpenAPI / User Story / MVD
    POLICY_GATE = "POLICY_GATE"           # Mandated by an organizational hard gate
    INFERRED = "INFERRED"                 # Deduced from design context or architecture record


class RuleSeverity(str, Enum):
    BLOCKER = "BLOCKER"                   # Cannot release; deployment/merge blocked
    CRITICAL = "CRITICAL"                 # High risk; requires approval if unmitigated
    MAJOR = "MAJOR"                       # Notable risk; must be addressed in sprint
    MINOR = "MINOR"                       # Best practice / recommendation


class MappingConfidence(str, Enum):
    CONFIRMED = "CONFIRMED"               # Explicit link (Jira ID in test title/metadata)
    HIGH = "HIGH"                         # Direct technical interface & asserted condition match
    MEDIUM = "MEDIUM"                     # Inferred from PageObject/route & semantic terms
    LOW = "LOW"                           # Domain keyword proximity only
    AMBIGUOUS = "AMBIGUOUS"               # Multiple conflicting candidates
    MISSING = "MISSING"                   # No matching test exists


class CoverageStatus(str, Enum):
    COVERED = "COVERED"                   # Expected outcome is directly asserted with evidence
    PARTIALLY_COVERED = "PARTIALLY_COVERED" # Some scenarios covered, or mentioned without deep assertion
    MISSING_COVERAGE = "MISSING_COVERAGE" # Zero automated or manual tests mapped
    BLOCKED = "BLOCKED"                   # Evaluation blocked due to missing artifact/dependency
    AMBIGUOUS = "AMBIGUOUS"               # Contradictory requirements or mappings
    NOT_APPLICABLE = "NOT_APPLICABLE"     # Rule does not apply to this component/interface


class ExecutionStatus(str, Enum):
    EXECUTION_PASSED = "EXECUTION_PASSED" # Real test execution succeeded
    EXECUTION_FAILED = "EXECUTION_FAILED" # Real test execution failed
    TEST_NOT_EXECUTED = "TEST_NOT_EXECUTED" # Test exists in repo but has not been run
    EVIDENCE_MISSING = "EVIDENCE_MISSING" # No execution records available in Xray/CI


@dataclass
class Provenance:
    """Tracks origin of requirements, rules, and assertions to prevent hallucinations."""
    artifact_path: str
    artifact_type: str                   # "OPENAPI", "FEATURE_SPEC", "ADR", "POLICY", "DIFF"
    section: Optional[str] = None
    line_number: Optional[int] = None
    identifier: Optional[str] = None     # e.g. OperationId or Header name
    extracted_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


@dataclass
class ExpectedOutcome:
    """A discrete verifiable behavior or condition that must be demonstrated."""
    outcome_id: str                      # Unique stable ID e.g. "OUT-PAY-001"
    requirement_id: str                  # Parent requirement
    outcome_type: RequirementType
    description: str
    target_interface: str                # e.g. "POST /api/v1/payments"
    expected_status_code: Optional[int] = None
    expected_headers: Dict[str, str] = field(default_factory=dict)
    expected_error_code: Optional[str] = None
    required_assertions: List[str] = field(default_factory=list)
    provenance: Optional[Provenance] = None


@dataclass
class Requirement:
    """Canonical representation of an engineering or business requirement."""
    requirement_id: str                  # e.g. "REQ-PAY-IDEMPOTENCY"
    title: str
    description: str
    req_type: RequirementType
    origin: RequirementOrigin
    domain: str                          # e.g. "PAYMENTS", "AUTH", "CORE"
    service: str                         # e.g. "payment-submission-service"
    interface: str                       # e.g. "POST /api/v1/payments"
    mandatory: bool = True
    severity: RuleSeverity = RuleSeverity.CRITICAL
    applicable_rule_ids: List[str] = field(default_factory=list)
    expected_outcomes: List[ExpectedOutcome] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    provenance: Optional[Provenance] = None
    ambiguity_notes: List[str] = field(default_factory=list)


@dataclass
class AssertionEvidence:
    """Structure of assertions inside an automated test case."""
    assertion_type: str                  # "STATUS_CODE", "HEADER", "BODY_FIELD", "ERROR_CODE", "RETRY_COUNT"
    target: str                          # e.g. "Idempotency-Key", "200", "ERR_CARD_EXPIRED"
    raw_statement: str                   # e.g. "expect(response.status).toBe(200)"
    line_number: int = 0
    is_deep_assertion: bool = True       # True if validates outcome rather than mere presence


@dataclass
class DiscoveredTestCase:
    """Canonical representation of an automated test across repositories."""
    test_id: str                         # e.g. "tests/payment.spec.ts:6:submitPayment"
    title: str
    file_path: str
    line_number: int
    framework: str                       # "playwright-ts", "selenium-java", "gherkin"
    in_regression_suite: bool = False
    in_smoke_suite: bool = False
    tags: List[str] = field(default_factory=list)
    jira_keys: List[str] = field(default_factory=list)
    endpoints_visited: List[str] = field(default_factory=list)
    routes_visited: List[str] = field(default_factory=list)
    http_methods: List[str] = field(default_factory=list)
    headers_sent: List[str] = field(default_factory=list)
    assertions: List[AssertionEvidence] = field(default_factory=list)
    page_objects_used: List[str] = field(default_factory=list)
    execution_status: ExecutionStatus = ExecutionStatus.TEST_NOT_EXECUTED
    last_execution_timestamp: Optional[str] = None
    execution_duration_sec: float = 0.0


@dataclass
class RequirementTestMapping:
    """Explicit mapping from requirement to test with explainable confidence and evidence."""
    requirement_id: str
    outcome_id: str
    test_id: str
    confidence: MappingConfidence
    evidence_summary: str
    asserts_outcome: bool                # True if test actually asserts the expected outcome
    mapping_source: str                  # "EXPLICIT_JIRA", "INTERFACE_ASSERTION", "INFERRED_PO", "MANUAL_OVERRIDE"
    is_override: bool = False
    override_reason: Optional[str] = None


@dataclass
class PolicyRule:
    """A deterministic organizational hard gate or compliance control."""
    rule_id: str                         # e.g. "GATE-PAY-001"
    name: str
    category: str                        # "SECURITY", "RESILIENCE", "PAYMENT_CORRECTNESS", "API_STANDARDS"
    description: str
    severity: RuleSeverity
    mandatory: bool
    applies_to: Dict[str, Any]           # Applicability conditions (e.g. operations: ["POST"], domain: ["PAYMENTS"])
    required_outcomes: List[str]         # Outcomes that must be demonstrated
    failure_criteria: str
    source_standard: str                 # e.g. "PCI-DSS 4.0", "ISO 20022", "PSP Architecture Gate 3.1"
    version: str = "1.0.0"


@dataclass
class RequirementCoverageAssessment:
    """Detailed coverage evaluation for a single requirement."""
    requirement_id: str
    title: str
    domain: str
    service: str
    coverage_status: CoverageStatus
    mapped_tests: List[RequirementTestMapping] = field(default_factory=list)
    uncovered_outcomes: List[ExpectedOutcome] = field(default_factory=list)
    applicable_rules: List[str] = field(default_factory=list)
    failing_gate_ids: List[str] = field(default_factory=list)
    execution_status: ExecutionStatus = ExecutionStatus.TEST_NOT_EXECUTED
    assessment_notes: List[str] = field(default_factory=list)
    suggested_test_scenario: Optional[Dict[str, Any]] = None


@dataclass
class RegressionSelectionDecision:
    """A ranked test selection recommendation tied to requirements and risk."""
    test_id: str
    title: str
    file_path: str
    framework: str
    in_regression_suite: bool
    priority: str                        # "MUST_RUN", "SHOULD_RUN", "SMOKE_ONLY"
    confidence: str                      # "HIGH", "MEDIUM", "LOW"
    selection_reasons: List[str] = field(default_factory=list)
    affected_requirement_ids: List[str] = field(default_factory=list)
    affected_outcomes: List[str] = field(default_factory=list)
    triggered_by_gates: List[str] = field(default_factory=list)
