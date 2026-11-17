"""
Registration Service Layer Exceptions
AI Powered Smart Hospital Referral System - Phase 1 Task 1C
"""


class RegistrationServiceError(Exception):
    """Base exception for all registration service errors."""
    pass


class ValidationError(RegistrationServiceError):
    """Raised when application details fail structural or semantic validation."""
    pass


class InvalidHierarchyError(RegistrationServiceError):
    """Raised when administrative parent-child hierarchy is invalid (e.g. district not in state)."""
    pass


class DuplicateApplicationError(RegistrationServiceError):
    """Raised when an active application already exists for the entity."""
    pass


class ApplicationNotFoundError(RegistrationServiceError):
    """Raised when an application ID or reference number cannot be found."""
    pass


class DocumentError(RegistrationServiceError):
    """Raised when document metadata, checksum, or verification fails."""
    pass


class UnauthorizedReviewerError(RegistrationServiceError):
    """Raised when a user lacks the role or authority to review at the current stage."""
    pass


class GeographicAccessError(RegistrationServiceError):
    """Raised when a reviewer attempts an action outside their assigned state or district jurisdiction."""
    pass


class SelfApprovalError(RegistrationServiceError):
    """Raised when an applicant attempts to review or approve their own application."""
    pass


class InvalidStageTransitionError(RegistrationServiceError):
    """Raised when an illegal lifecycle transition is attempted."""
    pass


class IneligibleForApprovalError(RegistrationServiceError):
    """Raised when an application fails final approval criteria."""
    pass


class TrackingTokenError(RegistrationServiceError):
    """Raised when a tracking token is invalid, expired, or revoked."""
    pass
