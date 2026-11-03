"use client";

import React, { useEffect, useState } from "react";
import {
  User,
  BedInventory,
  Referral,
  NotificationItem,
  Patient,
  HospitalRecommendation,
} from "@/lib/types";
import {
  apiGetInventory,
  apiGetHospitalReferrals,
  apiUpdateReferralStatus,
  apiGetNotifications,
  apiMarkNotificationRead,
  apiMarkAllNotificationsRead,
  apiGetRecommendations,
  apiCreateReferral,
  apiGetHospitalPatients,
  apiGetPatientReferrals,
} from "@/lib/api";
import { formatDateTime, formatDistance, formatModelFitScore } from "@/lib/formatters";
import { DashboardLayout } from "./shared/DashboardLayout";
import { StatCard } from "./shared/StatCard";
import { StatusBadge, PriorityBadge } from "./shared/StatusBadge";
import { DataTable, Column } from "./shared/DataTable";
import { ReferralTimeline } from "./shared/ReferralTimeline";
import { ConfirmationModal } from "./shared/ConfirmationModal";
import { EmptyState } from "./shared/EmptyState";
import { LoadingState, ErrorState } from "./shared/LoadingAndErrorStates";

interface HospitalDashboardProps {
  user: User;
}

export default function HospitalDashboard({ user }: HospitalDashboardProps) {
  const [activeTab, setActiveTab] = useState("overview");

  // Inventory State
  const [inventory, setInventory] = useState<BedInventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState("");

  // Referrals State
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [referralScope, setReferralScope] = useState<"incoming" | "outgoing" | "all">("incoming");
  const [referralLoading, setReferralLoading] = useState(false);
  const [referralError, setReferralError] = useState("");
  const [selectedReferralForTimeline, setSelectedReferralForTimeline] = useState<Referral | null>(null);
  const [reservationNotice, setReservationNotice] = useState<{
    referralId: string;
    message: string;
  } | null>(null);

  // Status Action Loading & Modals
  const [statusLoading, setStatusLoading] = useState(false);
  const [acceptingId, setAcceptingId] = useState<string | null>(null);

  // Dispatch Ambulance Modal
  const [dispatchModalReferral, setDispatchModalReferral] = useState<Referral | null>(null);
  const [dispatchAmbulanceId, setDispatchAmbulanceId] = useState("AMB-108-ADVANCED");
  const [dispatchEtaMinutes, setDispatchEtaMinutes] = useState(20);
  const [dispatchNotes, setDispatchNotes] = useState("");

  // Reject Referral Modal
  const [rejectModalReferral, setRejectModalReferral] = useState<Referral | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Notifications State
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifLoading, setNotifLoading] = useState(false);

  // Patients State
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientLoading, setPatientLoading] = useState(false);
  const [patientError, setPatientError] = useState("");
  const [selectedPatientForHistory, setSelectedPatientForHistory] = useState<Patient | null>(null);
  const [patientReferrals, setPatientReferrals] = useState<Referral[]>([]);
  const [patientReferralLoading, setPatientReferralLoading] = useState(false);

  // Referral Creation & AI Recommendations Modal
  const [referralModalPatient, setReferralModalPatient] = useState<Patient | null>(null);
  const [referralTargetHospitalId, setReferralTargetHospitalId] = useState("");
  const [referralPriority, setReferralPriority] = useState("Urgent");
  const [referralBedType, setReferralBedType] = useState<"ICU" | "GENERAL" | "EMERGENCY">("GENERAL");
  const [referralReason, setReferralReason] = useState("");
  const [recommendations, setRecommendations] = useState<HospitalRecommendation[]>([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState("");
  const [createReferralLoading, setCreateReferralLoading] = useState(false);
  const [createReferralError, setCreateReferralError] = useState("");
  const [createReferralSuccess, setCreateReferralSuccess] = useState("");

  const hospitalId = user.hospital_id || "GH00046";

  // Data Loaders
  const loadInventory = async () => {
    setInventoryLoading(true);
    setInventoryError("");
    try {
      const data = await apiGetInventory(hospitalId);
      const invData = data.inventory || data;
      setInventory({
        hospital_id: invData.hospital_id || hospitalId,
        available_beds: Number(invData.available_beds ?? 0),
        available_icu_beds: Number(invData.available_icu_beds ?? 0),
        reserved_beds: Number(invData.reserved_beds ?? 0),
        reserved_icu_beds: Number(invData.reserved_icu_beds ?? 0),
      });
    } catch (err: any) {
      setInventoryError(err.message || "Failed to load hospital bed inventory.");
    } finally {
      setInventoryLoading(false);
    }
  };

  const loadReferrals = async (scope: "incoming" | "outgoing" | "all" = referralScope) => {
    setReferralLoading(true);
    setReferralError("");
    try {
      const data = await apiGetHospitalReferrals(hospitalId, scope);
      setReferrals(data.referrals || []);
    } catch (err: any) {
      setReferralError(err.message || "Failed to load hospital referral roster.");
    } finally {
      setReferralLoading(false);
    }
  };

  const loadNotifications = async () => {
    setNotifLoading(true);
    try {
      const data = await apiGetNotifications(hospitalId);
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // Background poll failure
    } finally {
      setNotifLoading(false);
    }
  };

  const loadPatients = async () => {
    setPatientLoading(true);
    setPatientError("");
    try {
      const data = await apiGetHospitalPatients(hospitalId);
      setPatients(data.patients || []);
    } catch (err: any) {
      setPatientError(err.message || "Failed to load admitted hospital patient list.");
    } finally {
      setPatientLoading(false);
    }
  };

  const refreshAll = () => {
    loadInventory();
    loadReferrals(referralScope);
    loadNotifications();
    loadPatients();
  };

  useEffect(() => {
    refreshAll();
  }, [hospitalId]);

  // Status Transitions
  const handleUpdateStatus = async (
    referralId: string,
    newStatus: string,
    payload?: { ambulance_id?: string; eta_minutes?: number; notes?: string; reason?: string }
  ) => {
    setStatusLoading(true);
    setReferralError("");
    setReservationNotice(null);
    if (newStatus === "ACCEPTED") setAcceptingId(referralId);

    try {
      const res = await apiUpdateReferralStatus(referralId, newStatus, payload);

      if (newStatus === "ACCEPTED" && res.reservation) {
        const r = res.reservation;
        setReservationNotice({
          referralId,
          message: r.bed_id
            ? `Bed ${r.bed_id} (${r.bed_type || "ICU"}) reserved automatically.`
            : "Bed reservation confirmed in inventory.",
        });
      }

      await loadReferrals(referralScope);
      await loadInventory();
      await loadNotifications();
    } catch (err: any) {
      setReferralError(err.message || "Failed to execute referral status transition.");
    } finally {
      setStatusLoading(false);
      setAcceptingId(null);
    }
  };

  // Ambulance Dispatch Action
  const confirmDispatch = async () => {
    if (!dispatchModalReferral) return;
    await handleUpdateStatus(dispatchModalReferral.referral_id, "IN_TRANSIT", {
      ambulance_id: dispatchAmbulanceId.trim(),
      eta_minutes: Number(dispatchEtaMinutes) || 15,
      notes: dispatchNotes.trim(),
    });
    setDispatchModalReferral(null);
  };

  // Rejection Action
  const confirmReject = async () => {
    if (!rejectModalReferral) return;
    await handleUpdateStatus(rejectModalReferral.referral_id, "REJECTED", {
      reason: rejectReason.trim() || "Clinical capacity or specialty mismatch.",
    });
    setRejectModalReferral(null);
    setRejectReason("");
  };

  // Referral Creation & AI Recommendations
  const openReferralModal = (patient: Patient) => {
    setReferralModalPatient(patient);
    setReferralTargetHospitalId("");
    setReferralPriority(patient.priority || "Urgent");
    setReferralBedType(patient.icu_required === "Yes" ? "ICU" : "GENERAL");
    setReferralReason(`Transfer required for ${patient.disease || "specialized treatment"}. Patient: ${patient.name}`);
    setRecommendations([]);
    setRecError("");
    setCreateReferralError("");
    setCreateReferralSuccess("");
    fetchRecommendations(patient.patient_id);
  };

  const fetchRecommendations = async (pid: string) => {
    setRecLoading(true);
    setRecError("");
    try {
      const data = await apiGetRecommendations(pid);
      setRecommendations(data.hospitals || []);
    } catch (err: any) {
      setRecError(err.message || "Failed to retrieve AI-ranked hospital recommendations.");
    } finally {
      setRecLoading(false);
    }
  };

  const submitCreateReferral = async () => {
    if (!referralModalPatient) return;
    if (!referralTargetHospitalId.trim()) {
      setCreateReferralError("Please select or specify a destination hospital ID.");
      return;
    }
    setCreateReferralLoading(true);
    setCreateReferralError("");
    setCreateReferralSuccess("");

    try {
      const res = await apiCreateReferral({
        patient_id: referralModalPatient.patient_id,
        from_hospital_id: hospitalId,
        to_hospital_id: referralTargetHospitalId.trim().toUpperCase(),
        priority: referralPriority,
        bed_type: referralBedType,
        reason: referralReason.trim() || `Clinical referral for ${referralModalPatient.disease}`,
      });

      setCreateReferralSuccess(
        `Referral ${res.referral?.referral_id || ""} submitted successfully! Awaiting destination facility acceptance.`
      );
      setTimeout(() => {
        setReferralModalPatient(null);
        setActiveTab("referrals");
        setReferralScope("outgoing");
        loadReferrals("outgoing");
        loadNotifications();
      }, 1200);
    } catch (err: any) {
      setCreateReferralError(err.message || "Failed to submit patient referral.");
    } finally {
      setCreateReferralLoading(false);
    }
  };

  // Patient Referral History Drawer
  const openPatientHistory = async (patient: Patient) => {
    setSelectedPatientForHistory(patient);
    setPatientReferralLoading(true);
    try {
      const data = await apiGetPatientReferrals(patient.patient_id);
      setPatientReferrals(data.referrals || []);
    } catch {
      setPatientReferrals([]);
    } finally {
      setPatientReferralLoading(false);
    }
  };

  // Computed Metrics
  const activeReferralsCount = referrals.filter(
    (r) => !["COMPLETED", "REJECTED", "DIED", "CLOSED"].includes(r.status)
  ).length;

  const pendingIncomingCount = referrals.filter(
    (r) => r.to_hospital_id === hospitalId && r.status === "PENDING"
  ).length;

  const inTransitCount = referrals.filter((r) => r.status === "IN_TRANSIT").length;

  // Referral Columns Definition for DataTable
  const referralColumns: Column<Referral>[] = [
    {
      key: "referral_id",
      header: "Case ID",
      render: (r) => (
        <div>
          <span className="font-mono font-bold text-blue-400">{r.referral_id}</span>
          <p className="text-[10px] text-slate-400">{r.patient_id}</p>
        </div>
      ),
    },
    {
      key: "direction",
      header: "Route",
      render: (r) => {
        const isIncoming = r.to_hospital_id === hospitalId;
        return (
          <div className="space-y-0.5">
            <span
              className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${
                isIncoming
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
              }`}
            >
              {isIncoming ? "INBOUND" : "OUTBOUND"}
            </span>
            <p className="text-[11px] text-slate-300">
              {isIncoming ? `From: ${r.from_hospital_id}` : `To: ${r.to_hospital_id}`}
            </p>
          </div>
        );
      },
    },
    {
      key: "priority",
      header: "Priority",
      render: (r) => <PriorityBadge priority={r.priority} size="sm" />,
    },
    {
      key: "bed_type",
      header: "Bed Reqd",
      render: (r) => (
        <span className="font-semibold text-slate-200">
          {r.bed_type || (r.reason?.toLowerCase().includes("icu") ? "ICU" : "GENERAL")}
        </span>
      ),
    },
    {
      key: "status",
      header: "Current Stage",
      render: (r) => <StatusBadge status={r.status} size="sm" />,
    },
    {
      key: "created_at",
      header: "Initiated",
      render: (r) => (
        <span className="font-mono text-[11px] text-slate-400">
          {formatDateTime(r.created_at)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Operational Actions",
      align: "right",
      render: (r) => {
        const isDestination = r.to_hospital_id === hospitalId;
        const isSource = r.from_hospital_id === hospitalId;
        const isBusy = statusLoading;

        return (
          <div className="flex items-center justify-end gap-1.5 flex-wrap">
            {/* INCOMING PENDING -> ACCEPT / REJECT */}
            {isDestination && r.status === "PENDING" && (
              <>
                <button
                  onClick={() => handleUpdateStatus(r.referral_id, "ACCEPTED")}
                  disabled={isBusy}
                  className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                  title="Accept referral and reserve bed automatically"
                >
                  {acceptingId === r.referral_id ? "Reserving..." : "Accept & Reserve"}
                </button>
                <button
                  onClick={() => setRejectModalReferral(r)}
                  disabled={isBusy}
                  className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50 transition"
                  title="Decline referral"
                >
                  Reject
                </button>
              </>
            )}

            {/* OUTGOING ACCEPTED -> DISPATCH AMBULANCE */}
            {isSource && r.status === "ACCEPTED" && (
              <button
                onClick={() => setDispatchModalReferral(r)}
                disabled={isBusy}
                className="rounded-lg bg-blue-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-blue-500 disabled:opacity-50 transition"
                title="Dispatch ambulance and enter ETA"
              >
                Dispatch Ambulance
              </button>
            )}

            {/* INCOMING IN_TRANSIT -> CONFIRM ARRIVAL */}
            {isDestination && r.status === "IN_TRANSIT" && (
              <button
                onClick={() => handleUpdateStatus(r.referral_id, "ARRIVED")}
                disabled={isBusy}
                className="rounded-lg bg-cyan-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-cyan-500 disabled:opacity-50 transition"
                title="Confirm patient arrived at emergency bay"
              >
                Mark Arrived
              </button>
            )}

            {/* INCOMING ARRIVED -> COMMENCE TREATMENT */}
            {isDestination && r.status === "ARRIVED" && (
              <button
                onClick={() => handleUpdateStatus(r.referral_id, "TREATMENT_ACTIVE")}
                disabled={isBusy}
                className="rounded-lg bg-purple-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-purple-500 disabled:opacity-50 transition"
                title="Admit to bed and start treatment"
              >
                Start Treatment
              </button>
            )}

            {/* INCOMING TREATMENT_ACTIVE -> COMPLETE & RELEASE BED */}
            {isDestination && r.status === "TREATMENT_ACTIVE" && (
              <button
                onClick={() => handleUpdateStatus(r.referral_id, "COMPLETED")}
                disabled={isBusy}
                className="rounded-lg bg-emerald-700 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-emerald-600 disabled:opacity-50 transition"
                title="Complete care and return reserved bed to inventory"
              >
                Complete & Release Bed
              </button>
            )}

            {/* VIEW TIMELINE BUTTON */}
            <button
              onClick={() => setSelectedReferralForTimeline(r)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700 transition"
              title="Inspect lifecycle audit timeline"
            >
              Timeline
            </button>
          </div>
        );
      },
    },
  ];

  // Patients Columns Definition
  const patientColumns: Column<Patient>[] = [
    {
      key: "patient_id",
      header: "Patient ID",
      render: (p) => <span className="font-mono font-bold text-slate-200">{p.patient_id}</span>,
    },
    {
      key: "name",
      header: "Patient Name",
      render: (p) => (
        <div>
          <p className="font-semibold text-white">{p.name}</p>
          <p className="text-[11px] text-slate-400">
            {p.age}y • {p.gender}
          </p>
        </div>
      ),
    },
    {
      key: "disease",
      header: "Diagnosis / Condition",
      render: (p) => <span className="text-slate-300">{p.disease}</span>,
    },
    {
      key: "priority",
      header: "Priority",
      render: (p) => <PriorityBadge priority={p.priority} size="sm" />,
    },
    {
      key: "icu_required",
      header: "ICU Need",
      render: (p) => (
        <span
          className={`font-semibold text-[11px] px-2 py-0.5 rounded-full ${
            p.icu_required === "Yes"
              ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
              : "bg-slate-800 text-slate-400"
          }`}
        >
          {p.icu_required === "Yes" ? "Required" : "Standard"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Clinical Workflow",
      align: "right",
      render: (p) => (
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => openReferralModal(p)}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 transition"
            title="Launch AI-assisted destination hospital recommendations"
          >
            Create Referral
          </button>
          <button
            onClick={() => openPatientHistory(p)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition"
            title="View referral history across network"
          >
            History
          </button>
        </div>
      ),
    },
  ];

  return (
    <DashboardLayout
      user={user}
      tierBadge={{ label: "Hospital Clinical Command", color: "blue" }}
      title={user.name || `Hospital Facility ${hospitalId}`}
      subtitle={`Facility ID: ${hospitalId} • Jurisdiction: ${user.district || "Amritsar"}, ${user.state || "Punjab"}`}
      tabs={[
        { id: "overview", label: "Operations Overview", icon: "📊" },
        { id: "referrals", label: "Referrals Command", icon: "🔄", badge: activeReferralsCount },
        { id: "inventory", label: "Bed & Resource Inventory", icon: "🛏️" },
        { id: "patients", label: "Admitted Inpatients", icon: "👥", badge: patients.length },
      ]}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onRefresh={refreshAll}
      refreshLoading={inventoryLoading || referralLoading}
      notifications={notifications}
      unreadCount={unreadCount}
      notifLoading={notifLoading}
      onMarkNotifRead={(nid) => {
        apiMarkNotificationRead(hospitalId, nid).then(loadNotifications);
      }}
      onMarkAllNotifsRead={() => {
        apiMarkAllNotificationsRead(hospitalId).then(loadNotifications);
      }}
    >
      {/* Notice Banner */}
      {reservationNotice && (
        <div className="mb-6 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-base">✓</span>
            <span className="font-semibold">{reservationNotice.message}</span>
          </div>
          <button
            onClick={() => setReservationNotice(null)}
            className="text-emerald-400 hover:text-white"
          >
            ✕
          </button>
        </div>
      )}

      {referralError && (
        <ErrorState
          title="Referral Operations Notice"
          message={referralError}
          onRetry={() => loadReferrals(referralScope)}
          className="mb-6"
        />
      )}

      {/* ============================================================ */}
      {/* TAB 1: OPERATIONS OVERVIEW */}
      {/* ============================================================ */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Top KPI Metrics Grid */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              title="Available General Beds"
              value={inventory?.available_beds ?? "—"}
              subtitle={`Reserved: ${inventory?.reserved_beds ?? 0}`}
              icon="🛏️"
              variant="primary"
            />
            <StatCard
              title="Available ICU Beds"
              value={inventory?.available_icu_beds ?? "—"}
              subtitle={`Reserved: ${inventory?.reserved_icu_beds ?? 0}`}
              icon="⚡"
              variant={Number(inventory?.available_icu_beds) > 0 ? "success" : "danger"}
            />
            <StatCard
              title="Pending Inbound Referrals"
              value={pendingIncomingCount}
              subtitle="Requires destination clinical triage"
              icon="⏳"
              variant={pendingIncomingCount > 0 ? "warning" : "default"}
            />
            <StatCard
              title="Ambulances En Route"
              value={inTransitCount}
              subtitle="Active emergency transit"
              icon="🚑"
              variant="primary"
            />
          </div>

          {/* Quick Inbound Triage Queue */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white">
                  Active Clinical Inbound Queue
                </h3>
                <p className="text-xs text-slate-400">
                  Referrals transferred to this hospital awaiting admission or arrival confirmation
                </p>
              </div>
              <button
                onClick={() => {
                  setReferralScope("incoming");
                  setActiveTab("referrals");
                }}
                className="text-xs font-semibold text-blue-400 hover:text-blue-300 transition"
              >
                View Full Roster →
              </button>
            </div>

            <DataTable
              columns={referralColumns}
              data={referrals.filter((r) => r.to_hospital_id === hospitalId && r.status === "PENDING")}
              keyExtractor={(r) => r.referral_id}
              loading={referralLoading}
              emptyTitle="Inbound Queue Clear"
              emptyDescription="No incoming transfer requests currently awaiting review."
              pageSize={5}
            />
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 2: REFERRALS COMMAND */}
      {/* ============================================================ */}
      {activeTab === "referrals" && (
        <div className="space-y-6">
          {/* Scope Selector Tabs */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              {(["incoming", "outgoing", "all"] as const).map((scope) => (
                <button
                  key={scope}
                  onClick={() => {
                    setReferralScope(scope);
                    loadReferrals(scope);
                  }}
                  className={`rounded-xl px-4 py-2 text-xs font-bold uppercase tracking-wider transition ${
                    referralScope === scope
                      ? "bg-blue-600 text-white shadow-sm"
                      : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                  }`}
                >
                  {scope === "incoming"
                    ? "Inbound Requests"
                    : scope === "outgoing"
                    ? "Outbound Referrals"
                    : "All Hospital Cases"}
                </button>
              ))}
            </div>

            <p className="text-xs text-slate-400">
              Showing <span className="font-bold text-slate-200">{referrals.length}</span> total cases
            </p>
          </div>

          {/* Full Referrals Table */}
          <DataTable
            columns={referralColumns}
            data={referrals}
            keyExtractor={(r) => r.referral_id}
            loading={referralLoading}
            searchPlaceholder="Search Case ID, Patient ID, or Hospital..."
            searchFilterKeys={["referral_id", "patient_id", "from_hospital_id", "to_hospital_id", "reason"]}
            statusFilterKey="status"
            statusFilterOptions={[
              { label: "Pending Review", value: "PENDING" },
              { label: "Accepted & Reserved", value: "ACCEPTED" },
              { label: "In Transit", value: "IN_TRANSIT" },
              { label: "Patient Arrived", value: "ARRIVED" },
              { label: "Treatment Active", value: "TREATMENT_ACTIVE" },
              { label: "Completed", value: "COMPLETED" },
              { label: "Rejected", value: "REJECTED" },
            ]}
            emptyTitle="No Referrals Found"
            emptyDescription="There are no hospital transfer records matching the selected scope or filter."
            pageSize={10}
          />
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 3: BED INVENTORY */}
      {/* ============================================================ */}
      {activeTab === "inventory" && (
        <div className="space-y-6">
          {inventoryError && (
            <ErrorState title="Bed Inventory Alert" message={inventoryError} onRetry={loadInventory} />
          )}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-base font-bold text-white">
                  Real-Time Bed Availability & Allocation Matrix
                </h3>
                <p className="text-xs text-slate-400">
                  Backed by transactional PostgreSQL locking and atomic reservation rollback
                </p>
              </div>
              <button
                onClick={loadInventory}
                disabled={inventoryLoading}
                className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition"
              >
                {inventoryLoading ? "Refreshing..." : "Refresh Inventory"}
              </button>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
              {/* General Ward Capacity */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-white">General Inpatient Ward</span>
                  <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-semibold text-blue-400 border border-blue-500/20">
                    Standard Care
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-slate-900 p-3.5">
                    <p className="text-[11px] text-slate-400 uppercase">Available Beds</p>
                    <p className="mt-1 text-2xl font-bold text-emerald-400">
                      {inventory?.available_beds ?? 0}
                    </p>
                  </div>
                  <div className="rounded-lg bg-slate-900 p-3.5">
                    <p className="text-[11px] text-slate-400 uppercase">Reserved In Transit</p>
                    <p className="mt-1 text-2xl font-bold text-amber-400">
                      {inventory?.reserved_beds ?? 0}
                    </p>
                  </div>
                </div>

                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Beds in the reserved state are held during active patient transfer and automatically released back to available inventory upon referral completion.
                </p>
              </div>

              {/* ICU Ward Capacity */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-white">Intensive Care Unit (ICU)</span>
                  <span className="rounded-full bg-rose-500/10 px-2.5 py-0.5 text-xs font-semibold text-rose-400 border border-rose-500/20">
                    Critical Care
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-slate-900 p-3.5">
                    <p className="text-[11px] text-slate-400 uppercase">Available ICU</p>
                    <p className="mt-1 text-2xl font-bold text-emerald-400">
                      {inventory?.available_icu_beds ?? 0}
                    </p>
                  </div>
                  <div className="rounded-lg bg-slate-900 p-3.5">
                    <p className="text-[11px] text-slate-400 uppercase">Reserved ICU</p>
                    <p className="mt-1 text-2xl font-bold text-amber-400">
                      {inventory?.reserved_icu_beds ?? 0}
                    </p>
                  </div>
                </div>

                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Zero double-booking guarantee: ICU beds are acquired atomically via SQL transactions (<code className="text-blue-300">SELECT FOR UPDATE</code>) when an inbound referral is accepted.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 4: ADMITTED PATIENTS */}
      {/* ============================================================ */}
      {activeTab === "patients" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">Hospital Inpatient Registry</h3>
              <p className="text-xs text-slate-400">
                Patients admitted under local care available for network transfer
              </p>
            </div>
            <button
              onClick={loadPatients}
              disabled={patientLoading}
              className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
            >
              {patientLoading ? "Refreshing..." : "Refresh Patients"}
            </button>
          </div>

          {patientError && (
            <ErrorState title="Patient Directory Notice" message={patientError} onRetry={loadPatients} />
          )}

          <DataTable
            columns={patientColumns}
            data={patients}
            keyExtractor={(p) => p.patient_id}
            loading={patientLoading}
            searchPlaceholder="Search Patient ID, Name, or Disease..."
            searchFilterKeys={["patient_id", "name", "disease"]}
            emptyTitle="No Patients Found"
            emptyDescription="No inpatient records currently registered in this hospital's active admission database."
            pageSize={8}
          />
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: DISPATCH AMBULANCE */}
      {/* ============================================================ */}
      <ConfirmationModal
        isOpen={Boolean(dispatchModalReferral)}
        onClose={() => setDispatchModalReferral(null)}
        onConfirm={confirmDispatch}
        title="Dispatch Emergency Transport Ambulance"
        description={`Initiate ambulance transfer for Case ${dispatchModalReferral?.referral_id}. Sets status to IN_TRANSIT.`}
        confirmLabel="Confirm & Dispatch Ambulance"
        variant="primary"
        loading={statusLoading}
      >
        <div className="space-y-3.5">
          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Assigned Ambulance Vehicle ID
            </label>
            <input
              type="text"
              value={dispatchAmbulanceId}
              onChange={(e) => setDispatchAmbulanceId(e.target.value)}
              placeholder="e.g. AMB-108-ADVANCED"
              className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Estimated Transit Duration (Minutes)
            </label>
            <input
              type="number"
              min={1}
              value={dispatchEtaMinutes}
              onChange={(e) => setDispatchEtaMinutes(Number(e.target.value))}
              className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Paramedic / En-Route Clinical Notes
            </label>
            <textarea
              rows={2}
              value={dispatchNotes}
              onChange={(e) => setDispatchNotes(e.target.value)}
              placeholder="Oxygen supported, vitals stable, IV line active..."
              className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </ConfirmationModal>

      {/* ============================================================ */}
      {/* MODAL: REJECT REFERRAL */}
      {/* ============================================================ */}
      <ConfirmationModal
        isOpen={Boolean(rejectModalReferral)}
        onClose={() => setRejectModalReferral(null)}
        onConfirm={confirmReject}
        title="Decline Inbound Patient Referral"
        description={`Specify clinical justification for declining Case ${rejectModalReferral?.referral_id}.`}
        confirmLabel="Decline Referral"
        variant="danger"
        loading={statusLoading}
      >
        <div>
          <label className="block text-xs font-semibold text-slate-300">
            Rejection Clinical Reason / Capacity Constraint *
          </label>
          <textarea
            rows={3}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="e.g. No ventilator beds available; emergency surgery at capacity; redirect to regional tertiary center."
            className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-rose-500"
          />
        </div>
      </ConfirmationModal>

      {/* ============================================================ */}
      {/* MODAL: REFERRAL TIMELINE VIEW */}
      {/* ============================================================ */}
      {selectedReferralForTimeline && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <h3 className="text-base font-bold text-white">
                Detailed Referral Audit Trail
              </h3>
              <button
                onClick={() => setSelectedReferralForTimeline(null)}
                className="rounded-lg p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="mt-4">
              <ReferralTimeline referral={selectedReferralForTimeline} />
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedReferralForTimeline(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
              >
                Close Audit View
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* MODAL: CREATE REFERRAL WITH AI RECOMMENDATIONS */}
      {/* ============================================================ */}
      {referralModalPatient && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-5">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white">
                  Initiate Network Patient Referral
                </h3>
                <p className="text-xs text-slate-400">
                  Patient: <span className="text-white font-semibold">{referralModalPatient.name}</span> (
                  {referralModalPatient.patient_id}) • {referralModalPatient.age}y {referralModalPatient.gender}
                </p>
              </div>
              <button
                onClick={() => setReferralModalPatient(null)}
                className="rounded-lg p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Clinical Decision Support Disclaimer */}
            <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-3 text-xs text-blue-200 flex items-start gap-2.5">
              <span className="text-sm">ℹ️</span>
              <div>
                <span className="font-bold">Clinical Decision Support (CDS) Notice: </span>
                AI rankings estimate historical capability and bed capacity. Attending physician clinical verification and destination acceptance are required before patient dispatch.
              </div>
            </div>

            {/* AI Hospital Recommendations Section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  AI-Ranked Eligible Facilities
                </h4>
                {recLoading && (
                  <span className="text-xs text-blue-400 flex items-center gap-1">
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
                    Calculating rankings...
                  </span>
                )}
              </div>

              {recError && <p className="text-xs text-rose-400">{recError}</p>}

              {recommendations.length > 0 ? (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {recommendations.slice(0, 5).map((h, i) => {
                    const isSelected = referralTargetHospitalId === h.hospital_id;
                    return (
                      <div
                        key={h.hospital_id || i}
                        onClick={() => setReferralTargetHospitalId(h.hospital_id)}
                        className={`cursor-pointer rounded-xl border p-3 transition ${
                          isSelected
                            ? "border-blue-500 bg-blue-950/40 ring-1 ring-blue-500"
                            : "border-slate-800 bg-slate-950 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[10px] font-bold text-blue-400">
                              #{i + 1}
                            </span>
                            <span className="text-xs font-bold text-white">
                              {h.hospital_name || h.name || h.hospital_id}
                            </span>
                            <span className="text-[10px] font-mono text-slate-400">
                              ({h.hospital_id})
                            </span>
                          </div>

                          <div className="flex items-center gap-3 text-xs">
                            <span className="text-slate-400">
                              {formatDistance(h.distance_km)}
                            </span>
                            <span className="text-emerald-400 font-semibold">
                              {h.available_icu_beds} ICU Beds
                            </span>
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-blue-300 font-mono">
                              Fit: {formatModelFitScore(h.success_probability)}
                            </span>
                          </div>
                        </div>

                        {h.reasons && h.reasons.length > 0 && (
                          <p className="mt-1.5 text-[11px] text-slate-400 line-clamp-1">
                            ✓ {h.reasons.join(" • ")}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                !recLoading && (
                  <p className="text-xs text-slate-500 italic">
                    Enter hospital ID manually or reload AI rankings.
                  </p>
                )
              )}
            </div>

            {/* Referral Form Fields */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 pt-2 border-t border-slate-800">
              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Target Destination Hospital ID *
                </label>
                <input
                  type="text"
                  value={referralTargetHospitalId}
                  onChange={(e) => setReferralTargetHospitalId(e.target.value.toUpperCase())}
                  placeholder="e.g. GH00119"
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white font-mono outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Required Bed Type
                </label>
                <select
                  value={referralBedType}
                  onChange={(e) => setReferralBedType(e.target.value as any)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
                >
                  <option value="GENERAL">General Inpatient Bed</option>
                  <option value="ICU">Intensive Care Unit (ICU)</option>
                  <option value="EMERGENCY">Emergency / Trauma Bed</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Clinical Priority
                </label>
                <select
                  value={referralPriority}
                  onChange={(e) => setReferralPriority(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
                >
                  <option value="Critical">Critical (Immediate Transfer)</option>
                  <option value="Urgent">Urgent (&lt; 2 Hours)</option>
                  <option value="Stable">Stable Elective Transfer</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Clinical Referral Indication & Reason
              </label>
              <textarea
                rows={2}
                value={referralReason}
                onChange={(e) => setReferralReason(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
              />
            </div>

            {createReferralError && (
              <p className="text-xs text-rose-400 font-semibold">{createReferralError}</p>
            )}

            {createReferralSuccess && (
              <p className="text-xs text-emerald-400 font-semibold">{createReferralSuccess}</p>
            )}

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setReferralModalPatient(null)}
                disabled={createReferralLoading}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitCreateReferral}
                disabled={createReferralLoading || !referralTargetHospitalId.trim()}
                className="rounded-xl bg-blue-600 px-5 py-2 text-xs font-semibold text-white hover:bg-blue-500 transition disabled:opacity-50 flex items-center gap-2"
              >
                {createReferralLoading && (
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                )}
                <span>{createReferralLoading ? "Submitting..." : "Submit Referral"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* DRAWER: PATIENT REFERRAL HISTORY */}
      {/* ============================================================ */}
      {selectedPatientForHistory && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/75 backdrop-blur-sm animate-fade-in">
          <div className="h-full w-full max-w-xl overflow-y-auto border-l border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white">
                  Patient Network Referral History
                </h3>
                <p className="text-xs text-slate-400">
                  {selectedPatientForHistory.name} ({selectedPatientForHistory.patient_id})
                </p>
              </div>
              <button
                onClick={() => setSelectedPatientForHistory(null)}
                className="rounded-lg p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {patientReferralLoading ? (
              <LoadingState message="Fetching patient referral history..." />
            ) : patientReferrals.length === 0 ? (
              <EmptyState
                title="No Network Transfer Records"
                description="This patient has no recorded referral transfers between network facilities."
              />
            ) : (
              <div className="space-y-4">
                {patientReferrals.map((ref) => (
                  <div key={ref.referral_id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-blue-400">
                        {ref.referral_id}
                      </span>
                      <StatusBadge status={ref.status} size="sm" />
                    </div>
                    <div className="mt-2 text-xs text-slate-400 space-y-1">
                      <p>
                        From: <span className="text-slate-200">{ref.from_hospital_id}</span> → To:{" "}
                        <span className="text-slate-200">{ref.to_hospital_id}</span>
                      </p>
                      <p>Priority: {ref.priority} • Bed: {ref.bed_type || "ICU"}</p>
                      <p>Reason: {ref.reason}</p>
                      <p className="text-[10px] text-slate-400 pt-1">
                        Initiated: {formatDateTime(ref.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
