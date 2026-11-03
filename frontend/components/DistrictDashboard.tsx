"use client";

import React, { useEffect, useState } from "react";
import { User, DistrictMetrics, CriticalAlert, DistrictHospital, Referral } from "@/lib/types";
import { apiGetDistrictOverview, apiGetDistrictHospitals, apiGetDistrictReferrals } from "@/lib/api";
import { formatPercent, formatDateTime } from "@/lib/formatters";
import { DashboardLayout } from "./shared/DashboardLayout";
import { StatCard } from "./shared/StatCard";
import { StatusBadge, PriorityBadge } from "./shared/StatusBadge";
import { DataTable, Column } from "./shared/DataTable";
import { ReferralTimeline } from "./shared/ReferralTimeline";
import { ErrorState } from "./shared/LoadingAndErrorStates";

interface DistrictDashboardProps {
  user: User;
}

export default function DistrictDashboard({ user }: DistrictDashboardProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [metrics, setMetrics] = useState<DistrictMetrics | null>(null);
  const [alerts, setAlerts] = useState<CriticalAlert[]>([]);
  const [hospitals, setHospitals] = useState<DistrictHospital[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [selectedReferral, setSelectedReferral] = useState<Referral | null>(null);

  const districtName = user.district || "District";
  const stateName = user.state || "Punjab";

  const loadData = async () => {
    setLoading(true);
    setError("");

    try {
      // Load District Overview
      const overviewRes = await apiGetDistrictOverview();
      setMetrics(overviewRes.metrics);
      setAlerts(overviewRes.critical_alerts || []);

      // Load District Hospitals
      const hospRes = await apiGetDistrictHospitals();
      setHospitals(hospRes.hospitals || []);

      // Load District Referrals
      const refRes = await apiGetDistrictReferrals();
      setReferrals(refRes.referrals || []);
    } catch (err: any) {
      setError(err.message || "Failed to load district health operations data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Hospital Facility Columns
  const hospitalColumns: Column<DistrictHospital>[] = [
    {
      key: "hospital_id",
      header: "Hospital Facility",
      render: (h) => (
        <div>
          <span className="font-bold text-white">{h.name}</span>
          <p className="font-mono text-[11px] text-slate-400">
            ID: {h.hospital_id} • {h.city}
          </p>
        </div>
      ),
    },
    {
      key: "general_beds",
      header: "General Beds",
      render: (h) => (
        <div>
          <span className="font-bold text-slate-200">
            {h.available_beds} / {h.total_beds}
          </span>
          <p className="text-[10px] text-slate-400">Available / Total</p>
        </div>
      ),
    },
    {
      key: "icu_beds",
      header: "ICU Beds",
      render: (h) => (
        <div>
          <span
            className={`font-bold ${
              h.available_icu_beds > 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {h.available_icu_beds} / {h.icu_beds}
          </span>
          <p className="text-[10px] text-slate-400">Available / Total</p>
        </div>
      ),
    },
    {
      key: "capabilities",
      header: "Key Clinical Capabilities",
      render: (h) => (
        <div className="flex flex-wrap gap-1">
          {h.emergency_24x7 && (
            <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300 border border-rose-500/20">
              24x7 ER
            </span>
          )}
          {h.cardiology && (
            <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue-300 border border-blue-500/20">
              Cardiology
            </span>
          )}
          {h.neurology && (
            <span className="rounded bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-purple-300 border border-purple-500/20">
              Neurology
            </span>
          )}
          {h.ventilator && (
            <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/20">
              Ventilators
            </span>
          )}
          {h.ambulance && (
            <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-500/20">
              Ambulance
            </span>
          )}
          {h.ct_scan && (
            <span className="rounded bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300 border border-cyan-500/20">
              CT Scan
            </span>
          )}
        </div>
      ),
    },
  ];

  // Referral Columns
  const referralColumns: Column<Referral>[] = [
    {
      key: "referral_id",
      header: "Case ID",
      render: (r) => (
        <div>
          <span className="font-mono font-bold text-indigo-400">{r.referral_id}</span>
          <p className="text-[10px] text-slate-400">{r.patient_id}</p>
        </div>
      ),
    },
    {
      key: "route",
      header: "Jurisdiction Route",
      render: (r) => (
        <span className="font-medium text-slate-300">
          {r.from_hospital_id} → {r.to_hospital_id}
        </span>
      ),
    },
    {
      key: "priority",
      header: "Priority",
      render: (r) => <PriorityBadge priority={r.priority} size="sm" />,
    },
    {
      key: "bed_type",
      header: "Bed",
      render: (r) => <span className="font-semibold text-slate-200">{r.bed_type || "ICU"}</span>,
    },
    {
      key: "status",
      header: "Status",
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
      header: "Audit",
      align: "right",
      render: (r) => (
        <button
          onClick={() => setSelectedReferral(r)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition"
        >
          View Timeline
        </button>
      ),
    },
  ];

  return (
    <DashboardLayout
      user={user}
      tierBadge={{ label: "District Administration", color: "indigo" }}
      title={`${districtName} Health Operations`}
      subtitle={`State: ${stateName} • Administrator: ${user.name}`}
      tabs={[
        { id: "overview", label: "District Overview", icon: "📊" },
        { id: "hospitals", label: "Hospital Availability", icon: "🏥", badge: hospitals.length },
        { id: "referrals", label: "District Referrals", icon: "🔄", badge: referrals.length },
      ]}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onRefresh={loadData}
      refreshLoading={loading}
    >
      {error && (
        <ErrorState
          title="District Operational Alert"
          message={error}
          onRetry={loadData}
          className="mb-6"
        />
      )}

      {/* ============================================================ */}
      {/* TAB 1: OVERVIEW */}
      {/* ============================================================ */}
      {activeTab === "overview" && metrics && (
        <div className="space-y-6">
          {/* KPI Stat Cards */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              title="Participating Hospitals"
              value={metrics.total_hospitals}
              subtitle="Licensed clinical facilities"
              icon="🏥"
              variant="primary"
            />
            <StatCard
              title="District Bed Occupancy"
              value={formatPercent(metrics.bed_occupancy_rate)}
              subtitle={`${metrics.available_beds} of ${metrics.total_beds} beds free`}
              icon="🛏️"
              variant={metrics.bed_occupancy_rate > 85 ? "warning" : "default"}
            />
            <StatCard
              title="ICU Occupancy Rate"
              value={formatPercent(metrics.icu_occupancy_rate)}
              subtitle={`${metrics.available_icu_beds} of ${metrics.total_icu_beds} ICU free`}
              icon="⚡"
              variant={metrics.icu_occupancy_rate > 90 ? "danger" : "purple"}
            />
            <StatCard
              title="Active Patient Transfers"
              value={metrics.total_active_referrals}
              subtitle={`${metrics.in_transit_referrals} ambulances en route`}
              icon="🚑"
              variant="primary"
            />
          </div>

          {/* Critical Alerts */}
          {alerts && alerts.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300 flex items-center gap-2">
                <span>⚠️</span> Active District Health Alerts & Bottlenecks
              </h3>
              <div className="space-y-2">
                {alerts.map((alert, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-xs text-amber-200 bg-amber-950/40 p-2.5 rounded-lg border border-amber-500/20"
                  >
                    <span className="font-semibold text-amber-400">[{alert.severity}]</span>
                    <span>{alert.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick Hospital Snapshot */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white">
                Hospital Capacity & Emergency Status
              </h3>
              <button
                onClick={() => setActiveTab("hospitals")}
                className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
              >
                View All Facilities →
              </button>
            </div>
            <div className="mt-4">
              <DataTable
                columns={hospitalColumns}
                data={hospitals.slice(0, 5)}
                keyExtractor={(h) => h.hospital_id}
                loading={loading}
                emptyTitle="No Facilities Registered"
                pageSize={5}
              />
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 2: HOSPITALS */}
      {/* ============================================================ */}
      {activeTab === "hospitals" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">District Hospital Directory</h3>
              <p className="text-xs text-slate-400">
                All authorized public and empanelled facilities within {districtName} district
              </p>
            </div>
          </div>

          <DataTable
            columns={hospitalColumns}
            data={hospitals}
            keyExtractor={(h) => h.hospital_id}
            loading={loading}
            searchPlaceholder="Search facility name, ID, or city..."
            searchFilterKeys={["name", "hospital_id", "city"]}
            emptyTitle="No Hospitals Matching Search"
            emptyDescription="Try clearing your search query to view all district facilities."
            pageSize={10}
          />
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 3: REFERRALS */}
      {/* ============================================================ */}
      {activeTab === "referrals" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">District Transfer Roster</h3>
              <p className="text-xs text-slate-400">
                Inter-facility transfers originating from or received within {districtName}
              </p>
            </div>
          </div>

          <DataTable
            columns={referralColumns}
            data={referrals}
            keyExtractor={(r) => r.referral_id}
            loading={loading}
            searchPlaceholder="Search Case ID, Patient ID, or Hospital..."
            searchFilterKeys={["referral_id", "patient_id", "from_hospital_id", "to_hospital_id", "reason"]}
            statusFilterKey="status"
            statusFilterOptions={[
              { label: "Pending", value: "PENDING" },
              { label: "Accepted", value: "ACCEPTED" },
              { label: "In Transit", value: "IN_TRANSIT" },
              { label: "Arrived", value: "ARRIVED" },
              { label: "Treatment Active", value: "TREATMENT_ACTIVE" },
              { label: "Completed", value: "COMPLETED" },
              { label: "Rejected", value: "REJECTED" },
            ]}
            emptyTitle="No District Referrals Recorded"
            emptyDescription="There are no active or historical transfer requests in this district."
            pageSize={10}
          />
        </div>
      )}

      {/* TIMELINE MODAL */}
      {selectedReferral && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white">
                District Referral Case Audit
              </h3>
              <button
                onClick={() => setSelectedReferral(null)}
                className="rounded-lg p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="mt-4">
              <ReferralTimeline referral={selectedReferral} />
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedReferral(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
              >
                Close Audit View
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
