"""
Database registration service adapter / re-export
AI Powered Smart Hospital Referral System
"""

from src.services.registration_service import RegistrationService, CANONICAL_DIVISIONS
from src.services.registration_exceptions import (
    RegistrationServiceError,
    ValidationError,
    InvalidHierarchyError,
    DuplicateApplicationError,
    ApplicationNotFoundError,
    DocumentError,
    UnauthorizedReviewerError,
    GeographicAccessError,
    SelfApprovalError,
    InvalidStageTransitionError,
    IneligibleForApprovalError,
    TrackingTokenError,
)

__all__ = [
    "RegistrationService",
    "CANONICAL_DIVISIONS",
    "RegistrationServiceError",
    "ValidationError",
    "InvalidHierarchyError",
    "DuplicateApplicationError",
    "ApplicationNotFoundError",
    "DocumentError",
    "UnauthorizedReviewerError",
    "GeographicAccessError",
    "SelfApprovalError",
    "InvalidStageTransitionError",
    "IneligibleForApprovalError",
    "TrackingTokenError",
]
