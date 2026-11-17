"""
PostgreSQL SQLAlchemy 2.0 Relational Models
AI Powered Smart Hospital Referral System
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Boolean,
    Float,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
    desc,
    event,
    inspect,
    select,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.orm.attributes import NO_VALUE


class PgBase(DeclarativeBase):
    pass


class Role(PgBase):
    __tablename__ = "roles"

    id = Column(String(32), primary_key=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    users = relationship("User", back_populates="role")


class Hospital(PgBase):
    __tablename__ = "hospitals"

    hospital_id = Column(String(32), primary_key=True)
    name = Column(String(255), nullable=False)
    state = Column(String(100), nullable=False, index=True)
    district = Column(String(100), nullable=False, index=True)
    city = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    total_beds = Column(Integer, default=0, nullable=False)
    occupied_beds = Column(Integer, default=0, nullable=False)
    available_beds = Column(Integer, default=0, nullable=False)
    icu_beds = Column(Integer, default=0, nullable=False)
    available_icu_beds = Column(Integer, default=0, nullable=False)
    occupied_icu_beds = Column(Integer, default=0, nullable=False)
    emergency_beds = Column(Integer, default=0, nullable=False)
    available_emergency_beds = Column(Integer, default=0, nullable=False)
    occupied_emergency_beds = Column(Integer, default=0, nullable=False)

    # Capability Flags
    emergency_24x7 = Column(String(10), default="Yes", nullable=False)
    accepts_referral = Column(String(10), default="Yes", nullable=False)
    ambulance = Column(String(10), default="Yes", nullable=False)
    oxygen_support = Column(String(10), default="Yes", nullable=False)
    ventilator = Column(String(10), default="Yes", nullable=False)
    blood_bank = Column(String(10), default="Yes", nullable=False)

    # Specialties
    cardiology = Column(String(10), default="No", nullable=False)
    neurology = Column(String(10), default="No", nullable=False)
    nephrology = Column(String(10), default="No", nullable=False)
    pulmonology = Column(String(10), default="No", nullable=False)
    orthopedics = Column(String(10), default="No", nullable=False)
    general_medicine = Column(String(10), default="Yes", nullable=False)
    general_surgery = Column(String(10), default="Yes", nullable=False)
    trauma_unit = Column(String(10), default="No", nullable=False)
    burn_unit = Column(String(10), default="No", nullable=False)

    # Equipment & Diagnostics
    ct_scan = Column(String(10), default="No", nullable=False)
    mri = Column(String(10), default="No", nullable=False)
    xray = Column(String(10), default="Yes", nullable=False)
    ultrasound = Column(String(10), default="Yes", nullable=False)
    ecg = Column(String(10), default="Yes", nullable=False)
    dialysis = Column(String(10), default="No", nullable=False)
    blood_test = Column(String(10), default="Yes", nullable=False)
    cbc = Column(String(10), default="Yes", nullable=False)
    troponin_test = Column(String(10), default="No", nullable=False)
    dengue_ns1_test = Column(String(10), default="No", nullable=False)
    malaria_test = Column(String(10), default="No", nullable=False)
    blood_glucose_test = Column(String(10), default="Yes", nullable=False)
    hba1c_test = Column(String(10), default="No", nullable=False)
    kidney_function_test = Column(String(10), default="No", nullable=False)
    pulmonary_function_test = Column(String(10), default="No", nullable=False)
    blood_culture = Column(String(10), default="No", nullable=False)
    lactate_test = Column(String(10), default="No", nullable=False)
    stool_test = Column(String(10), default="No", nullable=False)

    # Hierarchical Registration & Grandfathering Metadata
    approval_status = Column(String(30), default="PENDING", nullable=False)
    is_grandfathered = Column(Boolean, default=False, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_hospitals_approval", "approval_status", "is_grandfathered"),
        Index("idx_hospitals_application_id", "application_id"),
        Index(
            "uq_hospitals_application_id",
            "application_id",
            unique=True,
            postgresql_where=Column("application_id").is_not(None),
            sqlite_where=Column("application_id").is_not(None),
        ),
        CheckConstraint("approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUSPENDED')", name="chk_hospitals_approval_status"),
    )

    beds = relationship("Bed", back_populates="hospital", cascade="all, delete-orphan")
    users = relationship("User", back_populates="hospital")
    registration_application = relationship("RegistrationApplication", back_populates="provisioned_hospital")


class User(PgBase):
    __tablename__ = "users"

    user_id = Column(String(32), primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role_id = Column(String(32), ForeignKey("roles.id", onupdate="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), nullable=True, index=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Contact & Application Metadata
    email = Column(String(255), nullable=True)
    phone_number = Column(String(30), nullable=True)
    designation = Column(String(100), nullable=True)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_application_id", "application_id"),
        Index(
            "uq_users_application_id",
            "application_id",
            unique=True,
            postgresql_where=Column("application_id").is_not(None),
            sqlite_where=Column("application_id").is_not(None),
        ),
    )

    role = relationship("Role", back_populates="users")
    hospital = relationship("Hospital", back_populates="users")
    registration_application = relationship("RegistrationApplication", back_populates="provisioned_user")


class Patient(PgBase):
    __tablename__ = "patients"

    patient_id = Column(String(32), primary_key=True)
    abha_id = Column(String(64), unique=True, nullable=True)
    name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    disease = Column(String(255), nullable=True)
    priority = Column(String(20), nullable=False, default="Stable")
    icu_required = Column(String(10), default="No", nullable=False)
    ambulance_required = Column(String(10), default="No", nullable=False)
    referral_required = Column(String(10), default="Yes", nullable=False)
    spo2 = Column(Integer, nullable=True)
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    severity_score = Column(Float, nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    visits = relationship("HospitalVisit", back_populates="patient", cascade="all, delete-orphan")
    referrals = relationship("Referral", back_populates="patient")


class HospitalVisit(PgBase):
    __tablename__ = "hospital_visits"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    patient_id = Column(String(32), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(30), default="NEW", nullable=False)
    admission_type = Column(String(30), default="DIRECT", nullable=False)
    admitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    treatment_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("Patient", back_populates="visits")


class Bed(PgBase):
    __tablename__ = "beds"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    bed_number = Column(String(50), nullable=False)
    bed_type = Column(String(20), nullable=False)
    status = Column(String(20), default="AVAILABLE", nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("hospital_id", "bed_number", name="uq_hospital_bed"),
        CheckConstraint("bed_type IN ('GENERAL', 'ICU', 'EMERGENCY')", name="chk_bed_type"),
        CheckConstraint("status IN ('AVAILABLE', 'RESERVED', 'OCCUPIED', 'MAINTENANCE')", name="chk_bed_status"),
    )

    hospital = relationship("Hospital", back_populates="beds")
    reservations = relationship("BedReservation", back_populates="bed")


class Referral(PgBase):
    __tablename__ = "referrals"

    referral_id = Column(String(64), primary_key=True)
    patient_id = Column(String(32), ForeignKey("patients.patient_id", ondelete="RESTRICT"), nullable=False, index=True)
    from_hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False, index=True)
    to_hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(30), default="PENDING", nullable=False, index=True)
    priority = Column(String(20), nullable=False)
    bed_type = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    ambulance_id = Column(String(64), nullable=True)
    eta_minutes = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    arrived_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient", back_populates="referrals")
    reservations = relationship("BedReservation", back_populates="referral", cascade="all, delete-orphan")


class BedReservation(PgBase):
    __tablename__ = "bed_reservations"

    reservation_id = Column(String(64), primary_key=True)
    referral_id = Column(String(64), ForeignKey("referrals.referral_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    bed_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("beds.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(20), default="RESERVED", nullable=False, index=True)
    reserved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    bed = relationship("Bed", back_populates="reservations")
    referral = relationship("Referral", back_populates="reservations")


class AuditLog(PgBase):
    __tablename__ = "audit_logs"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    performed_by = Column(String(64), nullable=True)
    previous_state = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    new_state = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class Notification(PgBase):
    __tablename__ = "notifications"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=True, index=True)
    referral_id = Column(String(64), ForeignKey("referrals.referral_id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(String(20), default="NORMAL", nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Workflow & Reviewer Notification Extensions (Phase 4D-2)
    user_id = Column(String(32), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True, index=True)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="CASCADE"), nullable=True, index=True)
    role_id = Column(String(32), ForeignKey("roles.id", ondelete="CASCADE"), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True, index=True)
    action_url = Column(String(255), nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=True, index=True)

    hospital = relationship("Hospital")
    referral = relationship("Referral")
    user = relationship("User")
    application = relationship("RegistrationApplication")
    role = relationship("Role")


class RegistrationApplication(PgBase):
    __tablename__ = "registration_applications"

    application_id = Column(String(64), primary_key=True)
    application_number = Column(String(64), unique=True, nullable=False)
    applicant_type = Column(String(20), nullable=False)  # STATE, DISTRICT, HOSPITAL
    applicant_name = Column(String(255), nullable=False)
    applicant_email = Column(String(255), nullable=False)
    applicant_phone = Column(String(30), nullable=False)
    state = Column(String(100), nullable=False)
    district = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    pincode = Column(String(20), nullable=True)
    official_designation = Column(String(100), nullable=True)
    nodal_officer_name = Column(String(255), nullable=True)
    parent_state = Column(String(100), nullable=True)
    parent_district = Column(String(100), nullable=True)
    profile_data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    current_stage = Column(String(30), default="DRAFT", nullable=False)
    status = Column(String(30), default="DRAFT", nullable=False)
    resubmission_version = Column(Integer, default=1, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    correction_notes = Column(Text, nullable=True)
    provisioned_entity_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    resubmitted_at = Column(DateTime(timezone=True), nullable=True)
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    final_approved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "applicant_type IN ('STATE', 'DISTRICT', 'HOSPITAL')",
            name="chk_reg_app_applicant_type",
        ),
        CheckConstraint(
            "current_stage IN ('DRAFT', 'SUBMITTED', 'DISTRICT_REVIEW', 'STATE_REVIEW', 'CENTRAL_REVIEW', 'APPROVED', 'REJECTED', 'CORRECTION_REQUIRED')",
            name="chk_reg_app_current_stage",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'REJECTED', 'SUSPENDED')",
            name="chk_reg_app_status",
        ),
        CheckConstraint(
            "resubmission_version >= 1",
            name="chk_reg_app_resubmission_version",
        ),
        Index("idx_reg_app_status", "status", "current_stage"),
        Index("idx_reg_app_geo", "state", "district"),
        Index("idx_reg_app_email", "applicant_email"),
        Index("idx_reg_app_type", "applicant_type"),
        Index(
            "uq_reg_app_active_state",
            func.lower(func.trim(text("state"))),
            unique=True,
            postgresql_where=text("applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
        Index(
            "uq_reg_app_active_district",
            func.lower(func.trim(text("state"))),
            func.lower(func.trim(text("district"))),
            unique=True,
            postgresql_where=text("applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
        Index(
            "uq_reg_app_active_hospital_email",
            func.lower(func.trim(text("applicant_email"))),
            unique=True,
            postgresql_where=text("applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
    )

    documents = relationship("RegistrationDocument", back_populates="application", cascade="all, delete-orphan")
    history = relationship("ApprovalHistory", back_populates="application", order_by="ApprovalHistory.id")
    tracking_tokens = relationship("ApplicationTrackingToken", back_populates="application", cascade="all, delete-orphan")
    activation_tokens = relationship("AccountActivationToken", back_populates="application")
    verification_tokens = relationship("VerificationToken", back_populates="application", cascade="all, delete-orphan")
    provisioned_hospital = relationship("Hospital", back_populates="registration_application", uselist=False, foreign_keys="[Hospital.application_id]")
    provisioned_user = relationship("User", back_populates="registration_application", uselist=False, foreign_keys="[User.application_id]")


@event.listens_for(RegistrationApplication, "before_insert")
def _handle_registration_application_before_insert(mapper, connection, target):
    """Enforce submitted_at lifecycle on INSERT: NULL for DRAFT, auto-populate for SUBMITTED."""
    if target.status in ("SUBMITTED", "UNDER_REVIEW") or target.current_stage in (
        "SUBMITTED", "DISTRICT_REVIEW", "STATE_REVIEW", "CENTRAL_REVIEW"
    ):
        if target.submitted_at is None:
            target.submitted_at = datetime.now(timezone.utc)
    else:
        target.submitted_at = None


@event.listens_for(RegistrationApplication, "before_update")
def _handle_registration_application_before_update(mapper, connection, target):
    """
    Enforce submitted_at and resubmitted_at lifecycle on UPDATE:
    1. Preserve original persisted submitted_at whenever it was already non-NULL.
       Prevent application code or callers from overwriting the original submission timestamp.
    2. First transition from DRAFT to SUBMITTED: automatically populate submitted_at if not yet set.
    3. Resubmission after CORRECTION_REQUIRED: preserve original submitted_at,
       populate resubmitted_at with current timestamp, and increment resubmission_version exactly once.
    4. Repeated updates while SUBMITTED do not increment resubmission_version again.
    """
    state = inspect(target)
    sub_hist = state.attrs.submitted_at.history
    status_hist = state.attrs.status.history

    # Resolve original persisted submitted_at safely across all inspection modes
    original_submitted_at = None
    if sub_hist.deleted and sub_hist.deleted[0] is not NO_VALUE:
        original_submitted_at = sub_hist.deleted[0]
    elif "submitted_at" in state.committed_state and state.committed_state["submitted_at"] is not NO_VALUE:
        original_submitted_at = state.committed_state["submitted_at"]
    elif sub_hist.unchanged and sub_hist.unchanged[0] is not NO_VALUE:
        original_submitted_at = sub_hist.unchanged[0]
    elif connection is not None and getattr(target, "application_id", None):
        row = connection.execute(
            select(RegistrationApplication.submitted_at).where(
                RegistrationApplication.application_id == target.application_id
            )
        ).first()
        if row and row[0] is not None:
            original_submitted_at = row[0]

    # Rule 1 & 2: Preserve original persisted submitted_at if it was already set
    if original_submitted_at is not None:
        target.submitted_at = original_submitted_at
    else:
        # Initial submission: transition to SUBMITTED while submitted_at was None
        if target.status in ("SUBMITTED", "UNDER_REVIEW") or target.current_stage in (
            "SUBMITTED", "DISTRICT_REVIEW", "STATE_REVIEW", "CENTRAL_REVIEW"
        ):
            if target.submitted_at is None:
                target.submitted_at = datetime.now(timezone.utc)

    # Resolve original persisted status safely
    old_status = None
    if status_hist.deleted and status_hist.deleted[0] is not NO_VALUE:
        old_status = status_hist.deleted[0]
    elif "status" in state.committed_state and state.committed_state["status"] is not NO_VALUE:
        old_status = state.committed_state["status"]
    elif status_hist.unchanged and status_hist.unchanged[0] is not NO_VALUE:
        old_status = status_hist.unchanged[0]
    elif connection is not None and getattr(target, "application_id", None):
        row = connection.execute(
            select(RegistrationApplication.status).where(
                RegistrationApplication.application_id == target.application_id
            )
        ).first()
        if row:
            old_status = row[0]

    # Rule 3 & 4: Resubmission after CORRECTION_REQUIRED
    if old_status == "CORRECTION_REQUIRED" and target.status in ("SUBMITTED", "UNDER_REVIEW"):
        target.resubmitted_at = datetime.now(timezone.utc)
        target.resubmission_version = (target.resubmission_version or 1) + 1

    target.last_updated_at = datetime.now(timezone.utc)


class RegistrationDocument(PgBase):
    __tablename__ = "registration_documents"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    document_id = Column(String(64), unique=True, nullable=False)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="CASCADE"), nullable=False)
    document_type = Column(String(50), nullable=False)
    storage_key = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    verification_status = Column(String(30), default="PENDING", nullable=False)
    reviewer_id = Column(String(32), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    reviewer_remarks = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "document_type IN ('CLINICAL_LICENSE', 'FIRE_SAFETY_NOC', 'POLLUTION_CONTROL_NOC', 'MEDICAL_COUNCIL_AFFILIATION', 'GOVERNMENT_ORDER', 'IDENTITY_PROOF', 'OTHER')",
            name="chk_reg_doc_type",
        ),
        CheckConstraint("file_size_bytes > 0", name="chk_reg_doc_file_size"),
        CheckConstraint(
            "verification_status IN ('PENDING', 'VERIFIED', 'REJECTED')",
            name="chk_reg_doc_verification_status",
        ),
        Index("idx_reg_doc_app_id", "application_id"),
        Index("idx_reg_doc_status", "verification_status"),
    )

    application = relationship("RegistrationApplication", back_populates="documents")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class ApprovalHistory(PgBase):
    __tablename__ = "approval_history"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="RESTRICT"), nullable=False)
    reviewer_user_id = Column(String(32), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    reviewer_role = Column(String(32), nullable=False)
    action = Column(String(50), nullable=False)
    review_tier = Column(String(30), nullable=False)
    previous_status = Column(String(30), nullable=False)
    new_status = Column(String(30), nullable=False)
    remarks = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "action IN ('SUBMIT', 'FORWARD', 'APPROVE', 'REJECT', 'REQUEST_CORRECTION', 'RESUBMIT', 'SUSPEND', 'REACTIVATE')",
            name="chk_approval_history_action",
        ),
        CheckConstraint(
            "review_tier IN ('APPLICANT', 'DISTRICT', 'STATE', 'CENTRAL')",
            name="chk_approval_history_tier",
        ),
        Index("idx_approval_history_app_id", "application_id", desc("created_at")),
    )

    application = relationship("RegistrationApplication", back_populates="history")
    reviewer = relationship("User", foreign_keys=[reviewer_user_id])


class VerificationToken(PgBase):
    __tablename__ = "verification_tokens"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    token_id = Column(String(64), unique=True, nullable=False)
    contact_target = Column(String(255), nullable=False)
    token_channel = Column(String(20), nullable=False)  # EMAIL, SMS
    token_purpose = Column(String(30), nullable=False)  # REGISTRATION_OTP, LOGIN_OTP, PASSWORD_RESET_OTP, PORTAL_ACCESS_OTP
    token_hash = Column(String(255), nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    resend_available_at = Column(DateTime(timezone=True), nullable=False)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("token_channel IN ('EMAIL', 'SMS')", name="chk_verification_tokens_channel"),
        CheckConstraint(
            "token_purpose IN ('REGISTRATION_OTP', 'LOGIN_OTP', 'PASSWORD_RESET_OTP', 'PORTAL_ACCESS_OTP')",
            name="chk_verification_tokens_purpose",
        ),
        CheckConstraint("attempt_count >= 0", name="chk_verification_tokens_attempt_count"),
        CheckConstraint("max_attempts > 0", name="chk_verification_tokens_max_attempts"),
        Index("idx_verification_tokens_target", "contact_target", "token_purpose", "is_verified"),
        Index("idx_verification_tokens_expiry", "expires_at", postgresql_where=Column("is_verified") == False),
        Index("idx_verification_tokens_app_id", "application_id"),
    )

    application = relationship("RegistrationApplication", back_populates="verification_tokens")


class ApplicationTrackingToken(PgBase):
    __tablename__ = "application_tracking_tokens"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tracking_token_id = Column(String(64), unique=True, nullable=False)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    access_count = Column(Integer, default=0, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("access_count >= 0", name="chk_tracking_tokens_access_count"),
        Index("idx_tracking_tokens_app_id", "application_id"),
        Index("idx_tracking_tokens_hash", "token_hash"),
    )

    application = relationship("RegistrationApplication", back_populates="tracking_tokens")


class AccountActivationToken(PgBase):
    __tablename__ = "account_activation_tokens"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    activation_token_id = Column(String(64), unique=True, nullable=False)
    application_id = Column(String(64), ForeignKey("registration_applications.application_id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String(32), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False)
    is_consumed = Column(Boolean, default=False, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_activation_tokens_user", "user_id"),
        Index("idx_activation_tokens_hash", "token_hash"),
    )

    application = relationship("RegistrationApplication", back_populates="activation_tokens")
    user = relationship("User", foreign_keys=[user_id])


class RegistrationEmailOutbox(PgBase):
    __tablename__ = "registration_email_outbox"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    outbox_id = Column(String(64), unique=True, nullable=False)
    event_type = Column(String(50), nullable=False)  # ACCOUNT_ACTIVATION, PASSWORD_RESET
    recipient_email = Column(String(255), nullable=False)
    recipient_name = Column(String(255), nullable=True)
    subject = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(32), default="PENDING", nullable=False)  # PENDING, PROCESSING, SENT, FAILED
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')", name="chk_email_outbox_status"),
        CheckConstraint("retry_count >= 0", name="chk_email_outbox_retry_count"),
        CheckConstraint("max_retries > 0", name="chk_email_outbox_max_retries"),
        Index("idx_email_outbox_queue", "status", "next_retry_at"),
    )


class PasswordResetToken(PgBase):
    __tablename__ = "password_reset_tokens"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    reset_token_id = Column(String(64), unique=True, nullable=False)
    user_id = Column(String(32), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False)
    is_consumed = Column(Boolean, default=False, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_password_reset_user", "user_id"),
        Index("idx_password_reset_hash", "token_hash"),
    )

    user = relationship("User", foreign_keys=[user_id])


class WorkerHeartbeat(PgBase):
    __tablename__ = "worker_heartbeats"

    worker_name = Column(String(64), primary_key=True)
    worker_id = Column(String(64), nullable=False)
    status = Column(String(20), default="RUNNING", nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    processed_total = Column(BigInteger().with_variant(Integer, "sqlite"), default=0, nullable=False)
    failed_total = Column(BigInteger().with_variant(Integer, "sqlite"), default=0, nullable=False)
    batch_size = Column(Integer, default=100, nullable=False)
    duration_seconds = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'STOPPED', 'FAILED', 'IDLE')", name="chk_worker_status"),
        Index("idx_worker_heartbeat_status", "status", "last_heartbeat"),
    )



