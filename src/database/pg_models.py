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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


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
    emergency_beds = Column(Integer, default=0, nullable=False)
    available_emergency_beds = Column(Integer, default=0, nullable=False)

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

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    beds = relationship("Bed", back_populates="hospital", cascade="all, delete-orphan")
    users = relationship("User", back_populates="hospital")


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

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    role = relationship("Role", back_populates="users")
    hospital = relationship("Hospital", back_populates="users")


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
    hospital_id = Column(String(32), ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True)
    referral_id = Column(String(64), ForeignKey("referrals.referral_id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(String(20), default="NORMAL", nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    hospital = relationship("Hospital")
    referral = relationship("Referral")

