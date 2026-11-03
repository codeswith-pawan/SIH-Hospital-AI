from pydantic import BaseModel


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
