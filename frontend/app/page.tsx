"use client";

import { useEffect, useState } from "react";
import HospitalDashboard from "@/components/HospitalDashboard";
import DistrictDashboard from "@/components/DistrictDashboard";
import StateDashboard from "@/components/StateDashboard";
import CentralDashboard from "@/components/CentralDashboard";
import { User, Referral } from "@/lib/types";
import {
  apiLogin,
  apiGetRecommendations,
  apiGetPatientReferrals,
  getStoredUser,
  setStoredSession,
  clearStoredSession,
} from "@/lib/api";
import {
  formatDistance,
  formatModelFitScore,
} from "@/lib/formatters";
import { StatusBadge, PriorityBadge } from "@/components/shared/StatusBadge";
import { ReferralTimeline } from "@/components/shared/ReferralTimeline";
import { LoadingState, ErrorState } from "@/components/shared/LoadingAndErrorStates";
import { EmptyState } from "@/components/shared/EmptyState";

const DEMO_ACCOUNTS = [
  {
    roleLabel: "Hospital Staff",
    username: "gh00046",
    password: "hospital123",
    desc: "Amritsar Medical College Hospital",
    badge: "Hospital Tier",
    color: "border-blue-500/30 text-blue-300",
  },
  {
    roleLabel: "District Admin",
    username: "amritsar_district_admin",
    password: "district123",
    desc: "Amritsar District Health Office",
    badge: "District Tier",
    color: "border-indigo-500/30 text-indigo-300",
  },
  {
    roleLabel: "State Admin",
    username: "punjab_admin",
    password: "admin123",
    desc: "Punjab State Health Directorate",
    badge: "State Tier",
    color: "border-teal-500/30 text-teal-300",
  },
  {
    roleLabel: "Central Admin",
    username: "central_admin",
    password: "central123",
    desc: "National Hospital Coordination",
    badge: "National Tier",
    color: "border-purple-500/30 text-purple-300",
  },
];

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [mounted, setMounted] = useState(false);

  // Login Form
  const [loginUsername, setLoginUsername] = useState("gh00046");
  const [loginPassword, setLoginPassword] = useState("hospital123");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  // Emergency Triage / Recommendation Engine
  const [patientId, setPatientId] = useState("PAT000002");
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Reservation from Triage
  const [reservationLoading, setReservationLoading] = useState(false);
  const [reservationHospitalId, setReservationHospitalId] = useState<string | null>(null);
  const [reservation, setReservation] = useState<any>(null);
  const [reservationError, setReservationError] = useState("");

  // Patient Referral History
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [referralLoading, setReferralLoading] = useState(false);
  const [referralError, setReferralError] = useState("");
  const [referralHistoryLoaded, setReferralHistoryLoaded] = useState(false);
  const [referralScopeRestricted, setReferralScopeRestricted] = useState(false);
  const [selectedReferral, setSelectedReferral] = useState<Referral | null>(null);

  // Restore authenticated session on page refresh
  useEffect(() => {
    setMounted(true);
    const stored = getStoredUser();
    if (stored) {
      setUser(stored);
    }
  }, []);

  const login = async (u = loginUsername, p = loginPassword) => {
    setLoginLoading(true);
    setLoginError("");

    try {
      const result = await apiLogin(u, p);
      setStoredSession(result.user, result.access_token);
      setUser(result.user);
    } catch (err: any) {
      setLoginError(err.message || "Invalid authentication credentials.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleSelectDemo = (acc: (typeof DEMO_ACCOUNTS)[0]) => {
    setLoginUsername(acc.username);
    setLoginPassword(acc.password);
    login(acc.username, acc.password);
  };

  const findHospitals = async () => {
    if (!patientId.trim()) {
      setError("Please enter a valid Patient ID.");
      return;
    }

    setLoading(true);
    setError("");
    setData(null);

    try {
      const result = await apiGetRecommendations(patientId.trim());
      setData(result);
    } catch (err: any) {
      setError(err.message || "Unable to connect to hospital recommendation service.");
    } finally {
      setLoading(false);
    }
  };

  const reserveHospital = async (hospitalId: string) => {
    setReservationHospitalId(hospitalId);
    setReservationLoading(true);
    setReservationError("");
    setReservation(null);

    try {
      const response = await fetch("http://127.0.0.1:8000/referral", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patientId,
          hospital_id: hospitalId,
        }),
      });

      const result = await response.json();
      if (!response.ok || !result.success) {
        throw new Error(result.message || "Hospital reservation failed");
      }
      setReservation(result);
    } catch (err: any) {
      setReservationError(err.message || "Reservation failed");
    } finally {
      setReservationLoading(false);
    }
  };

  const loadReferralHistory = async () => {
    if (!patientId.trim()) {
      setReferralError("Please enter a valid Patient ID.");
      return;
    }

    setReferralLoading(true);
    setReferralError("");
    setReferralScopeRestricted(false);

    try {
      const result = await apiGetPatientReferrals(patientId.trim());
      setReferrals(result.referrals || []);
      setReferralScopeRestricted(Boolean(result.scope_restricted));
      setReferralHistoryLoaded(true);
    } catch (err: any) {
      setReferralError(err.message || "Failed to load referral history.");
      setReferrals([]);
      setReferralHistoryLoaded(false);
    } finally {
      setReferralLoading(false);
    }
  };

  if (!mounted) {
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center">
        <LoadingState message="Initializing healthcare session..." />
      </main>
    );
  }

  // Route to Authorized Tier Dashboard
  if (user) {
    if (user.role === "HOSPITAL") {
      return <HospitalDashboard user={user} />;
    }
    if (user.role === "DISTRICT_ADMIN") {
      return <DistrictDashboard user={user} />;
    }
    if (user.role === "STATE_ADMIN") {
      return <StateDashboard user={user} />;
    }
    if (user.role === "CENTRAL_ADMIN") {
      return <CentralDashboard user={user} />;
    }

    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center max-w-md">
          <h1 className="text-xl font-bold">Unrecognized Healthcare Role</h1>
          <p className="mt-2 text-xs text-slate-400">
            Account {user.username} with role {user.role} does not have an active dashboard configuration.
          </p>
          <button
            onClick={() => {
              clearStoredSession();
              setUser(null);
            }}
            className="mt-5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500"
          >
            Return to Login
          </button>
        </div>
      </main>
    );
  }

  // Unauthenticated Portal: Login + Public Emergency Triage
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      {/* Top Banner */}
      <header className="border-b border-slate-800/80 bg-slate-900/90 backdrop-blur sticky top-0 z-30">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/30 text-xl shadow-inner">
              🏥
            </div>
            <div>
              <h1 className="text-base sm:text-lg font-bold tracking-tight text-white">
                SIH Hospital AI Command Platform
              </h1>
              <p className="text-[11px] text-slate-400">
                Multi-Tier Healthcare Referral, Bed Reservation & Critical Care Logistics
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium text-emerald-400 hidden sm:inline">
              PostgreSQL & Redis Online
            </span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-8 space-y-12">
        {/* Section 1: Staff Authentication & Quick Demo Selector */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left: Login Card */}
          <div className="lg:col-span-5 rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8 shadow-xl">
            <div className="text-left">
              <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
                Staff Authentication
              </span>
              <h2 className="mt-3 text-xl font-bold tracking-tight text-white">
                Sign in to Health Operations
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                Access your designated hospital or administrative jurisdiction dashboard.
              </p>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                login();
              }}
              className="mt-6 space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Username / Facility Handle
                </label>
                <input
                  type="text"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500 transition"
                  placeholder="e.g. gh00046"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Password
                </label>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500 transition"
                  placeholder="Password"
                  required
                />
              </div>

              {loginError && (
                <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                  ⚠️ {loginError}
                </div>
              )}

              <button
                type="submit"
                disabled={loginLoading}
                className="w-full rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-blue-500 disabled:opacity-50 flex items-center justify-center gap-2 shadow-sm"
              >
                {loginLoading && (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                )}
                <span>{loginLoading ? "Authenticating..." : "Sign In to Dashboard"}</span>
              </button>
            </form>
          </div>

          {/* Right: Quick Demo Role Switcher */}
          <div className="lg:col-span-7 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 space-y-4">
            <div>
              <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-bold text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                Evaluation & Testing Presets
              </span>
              <h2 className="mt-3 text-xl font-bold tracking-tight text-white">
                Multi-Role Demo Portals
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                Select an authorized account below to instantly evaluate role-based controls, data isolation, and live workflow capabilities:
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
              {DEMO_ACCOUNTS.map((acc) => (
                <div
                  key={acc.username}
                  onClick={() => handleSelectDemo(acc)}
                  className="cursor-pointer rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-blue-500 hover:bg-slate-900/80 group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white group-hover:text-blue-400 transition">
                      {acc.roleLabel}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${acc.color}`}
                    >
                      {acc.badge}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-300 font-medium">{acc.desc}</p>
                  <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-800/80">
                    <span className="font-mono text-slate-400">{acc.username}</span>
                    <span className="text-blue-400 font-semibold group-hover:translate-x-0.5 transition">
                      Launch Portal →
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-[11px] text-slate-400 flex items-start gap-2.5">
              <span>🛡️</span>
              <p>
                Strict Role-Based Access Control (RBAC): Hospital staff can only view and manage local facility patients; District admins monitor authorized district facilities; State and Central users access aggregate macro metrics.
              </p>
            </div>
          </div>
        </section>

        {/* Section 2: Clinical Triage & AI Recommendation Tool */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8 shadow-xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-[11px] font-bold text-indigo-400 border border-indigo-500/20 uppercase tracking-wider">
                Emergency Clinical Triage
              </span>
              <h2 className="mt-2 text-xl font-bold tracking-tight text-white">
                Find Eligible Hospitals & Clinical Recommendations
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                Execute AI-assisted destination hospital ranking based on clinical eligibility, ICU capacity, and distance.
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={patientId}
              onChange={(e) => {
                setPatientId(e.target.value);
                setReferralHistoryLoaded(false);
                setReferralScopeRestricted(false);
                setReferrals([]);
                setReferralError("");
              }}
              placeholder="Enter Patient ID (e.g. PAT000002)"
              className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500 transition font-mono"
            />
            <button
              onClick={findHospitals}
              disabled={loading}
              className="rounded-xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition flex items-center justify-center gap-2"
            >
              {loading && (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              )}
              <span>{loading ? "Ranking..." : "Find Hospitals"}</span>
            </button>
          </div>

          {error && <ErrorState title="Triage Query Error" message={error} />}

          {/* Triage Summary Cards */}
          {data && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 pt-2">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-[11px] text-slate-400 uppercase">Patient ID</p>
                <p className="mt-1 font-mono text-lg font-bold text-white">
                  {data.patient_id}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-[11px] text-slate-400 uppercase">Clinical Priority</p>
                <div className="mt-1">
                  <PriorityBadge priority={data.priority || "Stable"} size="sm" />
                </div>
              </div>

              <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-4">
                <p className="text-[11px] text-emerald-400 uppercase">Eligible Facilities</p>
                <p className="mt-1 text-lg font-bold text-emerald-300">
                  {data.total_hospitals ?? data.hospitals?.length ?? 0}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-[11px] text-slate-400 uppercase">Disqualified Facilities</p>
                <p className="mt-1 text-lg font-bold text-slate-400">
                  {data.disqualified_hospitals_count ?? 0}
                </p>
                <p className="text-[10px] text-slate-500">Excluded by Stage A safety</p>
              </div>
            </div>
          )}

          {/* Recommended Facilities List */}
          {data && data.hospitals && data.hospitals.length > 0 && (
            <div className="space-y-4 pt-4 border-t border-slate-800">
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 p-3.5 text-xs text-blue-200 flex items-start gap-2.5">
                <span className="text-base">ℹ️</span>
                <div>
                  <span className="font-bold text-white">Clinical Decision Support Notice: </span>
                  {data.ai_disclaimer ||
                    "AI recommendations are statistical estimates based on capability and capacity. Not an autonomous clinical decision; requires attending physician verification."}
                </div>
              </div>

              <div className="space-y-3">
                {data.hospitals.map((h: any, idx: number) => {
                  const hId = h.hospital_id || h.hospital?.hospital_id || `HOSP-${idx + 1}`;
                  const hName = h.hospital_name || h.name || h.hospital?.name || `Hospital ${hId}`;
                  const distanceKm = typeof h.distance_km === "number" ? h.distance_km : null;
                  const availBeds = typeof h.available_beds === "number" ? h.available_beds : 0;
                  const availIcu = typeof h.available_icu_beds === "number" ? h.available_icu_beds : 0;
                  const prob = h.success_probability;
                  const rank = h.rank ?? idx + 1;

                  return (
                    <div
                      key={hId}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-5 transition hover:border-slate-700 space-y-3"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div className="flex items-center gap-2.5">
                          <span className="rounded-full bg-blue-500/20 px-2.5 py-0.5 text-xs font-bold text-blue-400">
                            Rank #{rank}
                          </span>
                          <h4 className="text-sm font-bold text-white">{hName}</h4>
                          <span className="text-xs font-mono text-slate-400">({hId})</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs">
                          <span className="text-slate-400">Distance: {formatDistance(distanceKm)}</span>
                          <span className="text-slate-300">{availBeds} Beds</span>
                          <span className="text-emerald-400 font-semibold">{availIcu} ICU Free</span>
                          <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-blue-300 font-mono">
                            Model Fit: {formatModelFitScore(prob)}
                          </span>
                        </div>
                      </div>

                      {h.reasons && h.reasons.length > 0 && (
                        <p className="text-xs text-slate-400">
                          ✓ {h.reasons.join(" • ")}
                        </p>
                      )}

                      <div className="flex items-center justify-between pt-2 border-t border-slate-900">
                        <span className="text-[11px] text-slate-500">
                          {h.recommendation_type || "Eligible Regional Destination"}
                        </span>
                        <button
                          onClick={() => reserveHospital(hId)}
                          disabled={reservationLoading || availIcu <= 0}
                          className="rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40 transition"
                        >
                          {reservationLoading && reservationHospitalId === hId
                            ? "Reserving..."
                            : availIcu <= 0
                            ? "ICU Full"
                            : "Reserve ICU Bed"}
                        </button>
                      </div>

                      {reservationHospitalId === hId && reservation && (
                        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
                          ✓ Bed successfully reserved for patient {patientId}. Status: ACTIVE.
                        </div>
                      )}

                      {reservationHospitalId === hId && reservationError && (
                        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                          ⚠️ {reservationError}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Patient Referral History Lookup */}
          <div className="pt-6 border-t border-slate-800 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 className="text-base font-bold text-white">
                  Patient Network Transfer History
                </h3>
                <p className="text-xs text-slate-400">
                  Track full referral timeline for Patient {patientId}
                </p>
              </div>

              <button
                onClick={loadReferralHistory}
                disabled={referralLoading}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
              >
                {referralLoading ? "Loading..." : "Load Referral History"}
              </button>
            </div>

            {referralError && <ErrorState title="History Notice" message={referralError} />}

            {referralScopeRestricted && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-300">
                🔒 Access Scope Notice: Patient transfer records exist, but clinical details are restricted to originating or destination hospitals.
              </div>
            )}

            {referralHistoryLoaded && !referralScopeRestricted && referrals.length === 0 && (
              <EmptyState
                title="No Referral Records Found"
                description={`No prior hospital transfer records found for patient ${patientId}.`}
              />
            )}

            {referrals.length > 0 && (
              <div className="space-y-3">
                {referrals.map((r) => (
                  <div key={r.referral_id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-blue-400">
                          {r.referral_id}
                        </span>
                        <span className="text-xs text-slate-400">
                          {r.from_hospital_id} → {r.to_hospital_id}
                        </span>
                      </div>
                      <StatusBadge status={r.status} size="sm" />
                    </div>
                    <div className="mt-2 text-xs text-slate-400">
                      Reason: {r.reason} • Priority: {r.priority}
                    </div>
                    <div className="mt-3 flex justify-end">
                      <button
                        onClick={() =>
                          setSelectedReferral(
                            selectedReferral?.referral_id === r.referral_id ? null : r
                          )
                        }
                        className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
                      >
                        {selectedReferral?.referral_id === r.referral_id
                          ? "Hide Timeline"
                          : "View Timeline"}
                      </button>
                    </div>

                    {selectedReferral?.referral_id === r.referral_id && (
                      <div className="mt-4">
                        <ReferralTimeline referral={r} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/60 py-6 text-center text-xs text-slate-500">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 space-y-1">
          <p className="font-semibold text-slate-400">
            SIH Hospital AI • Smart Healthcare Referral & Bed Allocation Platform
          </p>
          <p className="text-[11px] text-slate-500">
            Developed under Smart India Hackathon guidelines. Certified for Clinical Decision Support.
          </p>
        </div>
      </footer>
    </main>
  );
}
