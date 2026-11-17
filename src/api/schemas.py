from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class PatientReferralRequest(BaseModel):
    patient_id: str
    hospital_id: str | None = None


class ReservationActionResponse(BaseModel):
    success: bool
    status: str
    message: str | None = None
    reservation: dict | None = None


class CreateReferralRequest(BaseModel):
    patient_id: str
    from_hospital_id: str
    to_hospital_id: str
    reason: str
    priority: str
    bed_type: str = "GENERAL"


class ReferralStatusUpdateRequest(BaseModel):
    notes: str | None = None
    reason: str | None = None
    ambulance_id: str | None = None
    eta_minutes: int | None = None


# ============================================================
# PHASE 4A: HOSPITAL INVENTORY & RESOURCES SCHEMAS
# ============================================================

class BedCapacityUpdateItem(BaseModel):
    bed_type: str = Field(..., description="GENERAL, ICU, or EMERGENCY")
    total_capacity: int = Field(..., ge=0, description="Target total capacity (must be >= occupied + reserved)")

    @field_validator("bed_type")
    def validate_type(cls, v):
        v_up = v.upper().strip()
        if v_up not in ["GENERAL", "ICU", "EMERGENCY"]:
            raise ValueError("bed_type must be GENERAL, ICU, or EMERGENCY")
        return v_up


class HospitalInventoryUpdateRequest(BaseModel):
    bed_type: Optional[str] = None
    total_capacity: Optional[int] = Field(None, ge=0)
    capacities: Optional[List[BedCapacityUpdateItem]] = None


class HospitalResourcesUpdateRequest(BaseModel):
    oxygen_support: Optional[str] = Field(None, pattern=r"^(?i:yes|no|true|false)$")
    ventilator: Optional[str] = Field(None, pattern=r"^(?i:yes|no|true|false)$")
    ambulance: Optional[str] = Field(None, pattern=r"^(?i:yes|no|true|false)$")
    blood_bank: Optional[str] = Field(None, pattern=r"^(?i:yes|no|true|false)$")
    emergency_24x7: Optional[str] = Field(None, pattern=r"^(?i:yes|no|true|false)$")
