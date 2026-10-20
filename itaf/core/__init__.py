"""
ITAF Core - Models, Schemas, and Provenance Tracking.
"""

from itaf.core.models import (
    RequirementType,
    RequirementOrigin,
    RuleSeverity,
    MappingConfidence,
    CoverageStatus,
    ExecutionStatus,
    Provenance,
    ExpectedOutcome,
    Requirement,
    AssertionEvidence,
    DiscoveredTestCase,
    RequirementTestMapping,
    PolicyRule,
    RequirementCoverageAssessment,
    RegressionSelectionDecision
)

__all__ = [
    "RequirementType",
    "RequirementOrigin",
    "RuleSeverity",
    "MappingConfidence",
    "CoverageStatus",
    "ExecutionStatus",
    "Provenance",
    "ExpectedOutcome",
    "Requirement",
    "AssertionEvidence",
    "DiscoveredTestCase",
    "RequirementTestMapping",
    "PolicyRule",
    "RequirementCoverageAssessment",
    "RegressionSelectionDecision"
]
