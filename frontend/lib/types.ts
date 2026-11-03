export type Role = "HOSPITAL" | "DISTRICT_ADMIN" | "STATE_ADMIN" | "CENTRAL_ADMIN";

export type User = {
  user_id: string;
  username: string;
  name: string;
  role: Role;
  hospital_id?: string | null;
  state?: string | null;
  district?: string | null;
};

export type ReferralStatus =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "IN_TRANSIT"
  | "ARRIVED"
  | "TREATMENT_ACTIVE"
  | "COMPLETED"
  | "TRANSFERRED"
  | "DIED"
  | "CLOSED";

export type Priority = "Critical" | "Urgent" | "Stable";

export type BedType = "ICU" | "GENERAL" | "EMERGENCY" | "VENTILATOR";

export type Referral = {
  referral_id: string;
  patient_id: string;
  from_hospital_id: string;
  to_hospital_id: string;
  from_hospital_name?: string;
  to_hospital_name?: string;
  from_district?: string;
  to_district?: string;
  from_state?: string;
  to_state?: string;
  reason: string;
  priority: Priority | string;
  status: ReferralStatus;
  bed_type?: BedType | string;
  bed_id?: string;
  bed_number?: string;
  reservation_status?: string;
  auto_reservation?: boolean;
  reservation_message?: string;
  reservation_release_status?: string;
  ambulance_id?: string | null;
  eta_minutes?: number | null;
  notes?: string | null;
  rejection_reason?: string | null;
  created_at: string;
  accepted_at?: string | null;
  rejected_at?: string | null;
  dispatched_at?: string | null;
  in_transit_at?: string | null;
  arrived_at?: string | null;
  treatment_started_at?: string | null;
  completed_at?: string | null;
  transferred_at?: string | null;
  died_at?: string | null;
  closed_at?: string | null;
};

export type BedInventory = {
  hospital_id: string;
  hospital_name?: string;
  total_beds?: number;
  available_beds: number;
  total_icu_beds?: number;
  available_icu_beds: number;
  reserved_beds: number;
  reserved_icu_beds: number;
  occupied_beds?: number;
  occupied_icu_beds?: number;
};

export type HospitalRecommendation = {
  hospital_id: string;
  hospital_name: string;
  name?: string;
  state?: string;
  district?: string;
  city?: string;
  distance_km?: number | null;
  available_beds: number;
  available_icu_beds: number;
  final_score?: number;
  success_probability?: number | null;
  specialty_match?: number;
  bed_match?: number;
  icu_match?: number;
  test_match?: number;
  recommendation_type?: string;
  reasons?: string[];
  disqualification_reasons?: string[];
  is_eligible?: boolean;
  rank?: number;
};

export type NotificationItem = {
  notification_id: string;
  referral_id?: string;
  hospital_id: string;
  event_type: string;
  title: string;
  message: string;
  priority: string;
  is_read: boolean;
  created_at: string;
};

export type Patient = {
  visit_id?: number | string;
  patient_id: string;
  name: string;
  age: number;
  gender: string;
  disease: string;
  priority: Priority | string;
  icu_required: string;
  status: string;
  admission_type?: string;
  admitted_at?: string;
  treatment_started_at?: string;
  completed_at?: string;
};

export type DistrictMetrics = {
  total_hospitals: number;
  total_beds: number;
  available_beds: number;
  occupied_beds: number;
  bed_occupancy_rate: number;
  total_icu_beds: number;
  available_icu_beds: number;
  occupied_icu_beds: number;
  icu_occupancy_rate: number;
  total_active_referrals: number;
  pending_referrals: number;
  in_transit_referrals: number;
};

export type CriticalAlert = {
  severity: "CRITICAL" | "WARNING" | "INFO";
  type: string;
  hospital_id?: string;
  hospital_name?: string;
  message: string;
};

export type DistrictHospital = {
  hospital_id: string;
  name: string;
  state: string;
  district: string;
  city: string;
  total_beds: number;
  available_beds: number;
  icu_beds: number;
  available_icu_beds: number;
  emergency_24x7: boolean;
  cardiology: boolean;
  neurology: boolean;
  ventilator: boolean;
  ambulance: boolean;
  ct_scan: boolean;
};

export type StateMetrics = {
  total_districts: number;
  total_hospitals: number;
  total_beds: number;
  available_beds: number;
  bed_occupancy_rate: number;
  total_icu_beds: number;
  available_icu_beds: number;
  icu_occupancy_rate: number;
  total_referrals: number;
};

export type DistrictSummary = {
  district: string;
  hospitals: number;
  total_beds: number;
  available_beds: number;
  total_icu: number;
  available_icu: number;
  occupancy_rate: number;
};

export type CentralMetrics = {
  participating_states: number;
  total_hospitals: number;
  total_beds: number;
  available_beds: number;
  bed_occupancy_rate: number;
  total_icu_beds: number;
  available_icu_beds: number;
  icu_occupancy_rate: number;
  total_referrals: number;
  interstate_referrals: number;
};

export type StateSummary = {
  state: string;
  hospitals: number;
  total_beds: number;
  available_beds: number;
  total_icu: number;
  available_icu: number;
  occupancy_rate: number;
};
