import {
  User,
  Referral,
  NotificationItem,
  Patient,
  HospitalRecommendation,
  DistrictMetrics,
  DistrictHospital,
  CriticalAlert,
  StateMetrics,
  DistrictSummary,
  CentralMetrics,
  StateSummary,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "access_token";
const USER_KEY = "sih_auth_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setStoredSession(user: User, token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

interface ApiErrorPayload {
  detail?: string | { message?: string };
  message?: string;
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err) {
    throw new ApiError(
      "Unable to connect to healthcare backend service. Please check network connectivity.",
      0,
      err
    );
  }

  let data: unknown = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let message = "Request failed.";
    if (data && typeof data === "object") {
      const errObj = data as ApiErrorPayload;
      if (typeof errObj.detail === "string") {
        message = errObj.detail;
      } else if (errObj.detail && typeof errObj.detail.message === "string") {
        message = errObj.detail.message;
      } else if (typeof errObj.message === "string") {
        message = errObj.message;
      }
    }
    throw new ApiError(message, response.status, data);
  }

  return data as T;
}

// ----------------------------------------------------------------------
// Specific Typed API Callers
// ----------------------------------------------------------------------

export async function apiLogin(username: string, password: string) {
  return apiFetch<{
    success: boolean;
    message: string;
    access_token: string;
    token_type: string;
    user: User;
  }>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function apiLogout() {
  clearStoredSession();
}

export async function apiGetInventory(hospitalId: string) {
  return apiFetch<{
    success: boolean;
    hospital_id: string;
    inventory?: {
      hospital_id: string;
      available_beds: number;
      available_icu_beds: number;
      reserved_beds: number;
      reserved_icu_beds: number;
    };
    available_beds?: number;
    available_icu_beds?: number;
    reserved_beds?: number;
    reserved_icu_beds?: number;
  }>(`/hospitals/${hospitalId}/inventory`);
}

export async function apiGetHospitalReferrals(
  hospitalId: string,
  scope: "incoming" | "outgoing" | "all" = "incoming"
) {
  return apiFetch<{
    success: boolean;
    hospital_id: string;
    total_referrals: number;
    referrals: Referral[];
  }>(`/hospitals/${hospitalId}/referrals?scope=${scope}`);
}

export async function apiUpdateReferralStatus(
  referralId: string,
  newStatus: string,
  payload?: {
    ambulance_id?: string;
    eta_minutes?: number;
    notes?: string;
    reason?: string;
  }
) {
  return apiFetch<{
    success: boolean;
    referral: Referral;
    reservation?: {
      bed_id?: string;
      bed_type?: string;
      auto_reservation?: boolean;
    };
    message?: string;
  }>(`/referrals/${referralId}/status/${newStatus}`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function apiGetNotifications(hospitalId: string) {
  return apiFetch<{
    success: boolean;
    hospital_id: string;
    total: number;
    unread_count: number;
    notifications: NotificationItem[];
  }>(`/hospitals/${hospitalId}/notifications`);
}

export async function apiMarkNotificationRead(
  hospitalId: string,
  notifId: string
) {
  return apiFetch<{ success: boolean }>(
    `/hospitals/${hospitalId}/notifications/${notifId}/read`,
    { method: "POST" }
  );
}

export async function apiMarkAllNotificationsRead(hospitalId: string) {
  return apiFetch<{ success: boolean; marked_count: number }>(
    `/hospitals/${hospitalId}/notifications/read-all`,
    { method: "POST" }
  );
}

export async function apiGetRecommendations(patientId: string) {
  return apiFetch<{
    success: boolean;
    patient_id: string;
    priority?: string;
    total_hospitals?: number;
    disqualified_hospitals_count?: number;
    referral_required?: string;
    message?: string;
    reason?: string;
    ai_disclaimer?: string;
    hospitals: HospitalRecommendation[];
  }>(`/hospitals?patient_id=${encodeURIComponent(patientId)}`);
}

export async function apiCreateReferral(payload: {
  patient_id: string;
  from_hospital_id: string;
  to_hospital_id: string;
  reason: string;
  priority: string;
  bed_type: string;
}) {
  return apiFetch<{
    success: boolean;
    message?: string;
    referral: Referral;
    reservation?: {
      bed_id?: string;
      bed_type?: string;
      status?: string;
    };
  }>("/referrals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function apiGetHospitalPatients(hospitalId: string) {
  return apiFetch<{
    success: boolean;
    hospital_id: string;
    count: number;
    patients: Patient[];
  }>(`/patients/hospital/${hospitalId}`);
}

export async function apiGetPatientReferrals(patientId: string) {
  return apiFetch<{
    success: boolean;
    patient_id: string;
    total_referrals: number;
    total_system_referrals?: number;
    scope_restricted?: boolean;
    message?: string;
    referrals: Referral[];
  }>(`/patients/${encodeURIComponent(patientId)}/referrals`);
}

// Admin Routes
export async function apiGetDistrictOverview() {
  return apiFetch<{
    success: boolean;
    district: string;
    state: string;
    metrics: DistrictMetrics;
    critical_alerts?: CriticalAlert[];
  }>("/district/overview");
}

export async function apiGetDistrictHospitals() {
  return apiFetch<{
    success: boolean;
    district: string;
    count: number;
    hospitals: DistrictHospital[];
  }>("/district/hospitals");
}

export async function apiGetDistrictReferrals() {
  return apiFetch<{
    success: boolean;
    district: string;
    count: number;
    referrals: Referral[];
  }>("/district/referrals");
}

export async function apiGetStateOverview() {
  return apiFetch<{
    success: boolean;
    state: string;
    metrics: StateMetrics;
    districts: DistrictSummary[];
  }>("/state/overview");
}

export async function apiGetStateReferrals() {
  return apiFetch<{
    success: boolean;
    state: string;
    count: number;
    referrals: Referral[];
  }>("/state/referrals");
}

export async function apiGetCentralOverview() {
  return apiFetch<{
    success: boolean;
    metrics: CentralMetrics;
    states: StateSummary[];
  }>("/central/overview");
}
