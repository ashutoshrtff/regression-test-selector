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

from itaf.core.cache import (
    compute_file_hash,
    ArtifactCache,
    GLOBAL_ARTIFACT_CACHE
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
    "RegressionSelectionDecision",
    "compute_file_hash",
    "ArtifactCache",
    "GLOBAL_ARTIFACT_CACHE"
]
