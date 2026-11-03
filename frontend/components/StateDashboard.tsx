"use client";

import React, { useEffect, useState } from "react";
import { User, StateMetrics, DistrictSummary, Referral } from "@/lib/types";
import { apiGetStateOverview, apiGetStateReferrals } from "@/lib/api";
import { formatPercent, formatDateTime } from "@/lib/formatters";
import { DashboardLayout } from "./shared/DashboardLayout";
import { StatCard } from "./shared/StatCard";
import { StatusBadge, PriorityBadge } from "./shared/StatusBadge";
import { DataTable, Column } from "./shared/DataTable";
import { ReferralTimeline } from "./shared/ReferralTimeline";
import { ErrorState } from "./shared/LoadingAndErrorStates";

interface StateDashboardProps {
  user: User;
}

export default function StateDashboard({ user }: StateDashboardProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [metrics, setMetrics] = useState<StateMetrics | null>(null);
  const [districts, setDistricts] = useState<DistrictSummary[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [selectedDistrict, setSelectedDistrict] = useState("ALL");
  const [selectedReferral, setSelectedReferral] = useState<Referral | null>(null);

  const stateName = user.state || "Punjab";

  const loadData = async () => {
    setLoading(true);
    setError("");

    try {
      // Load State Overview & Districts
      const overviewRes = await apiGetStateOverview();
      setMetrics(overviewRes.metrics);
      setDistricts(overviewRes.districts || []);

      // Load State Referrals
      const refRes = await apiGetStateReferrals();
      setReferrals(refRes.referrals || []);
    } catch (err: any) {
      setError(err.message || "Failed to load state health command data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // District Summary Columns
  const districtColumns: Column<DistrictSummary>[] = [
    {
      key: "district",
      header: "Administrative District",
      render: (d) => <span className="font-bold text-white">{d.district}</span>,
    },
    {
      key: "hospitals",
      header: "Hospitals",
      render: (d) => <span className="font-semibold text-slate-200">{d.hospitals}</span>,
    },
    {
      key: "beds",
      header: "General Beds (Free / Total)",
      render: (d) => (
        <div>
          <span className="font-bold text-slate-200">
            {d.available_beds} / {d.total_beds}
          </span>
        </div>
      ),
    },
    {
      key: "icu",
      header: "ICU Beds (Free / Total)",
      render: (d) => (
        <div>
          <span
            className={`font-bold ${
              d.available_icu > 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {d.available_icu} / {d.total_icu}
          </span>
        </div>
      ),
    },
    {
      key: "occupancy",
      header: "Bed Occupancy",
      render: (d) => {
        const occ = d.occupancy_rate;
        return (
          <div className="flex items-center gap-2">
            <span
              className={`font-bold text-xs ${
                occ > 85 ? "text-rose-400" : occ > 70 ? "text-amber-400" : "text-emerald-400"
              }`}
            >
              {formatPercent(occ)}
            </span>
            <div className="h-1.5 w-16 rounded-full bg-slate-800 overflow-hidden">
              <div
                className={`h-full ${
                  occ > 85 ? "bg-rose-500" : occ > 70 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(occ, 100)}%` }}
              />
            </div>
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "Drilldown",
      align: "right",
      render: (d) => (
        <button
          onClick={() => {
            setSelectedDistrict(d.district);
            setActiveTab("referrals");
          }}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-teal-300 hover:bg-slate-700 transition"
        >
          View Referrals →
        </button>
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
          <span className="font-mono font-bold text-teal-400">{r.referral_id}</span>
          <p className="text-[10px] text-slate-400">{r.patient_id}</p>
        </div>
      ),
    },
    {
      key: "origin_dest",
      header: "Inter-District Route",
      render: (r) => (
        <div className="space-y-0.5">
          <p className="text-xs text-white">
            {r.from_hospital_id} → {r.to_hospital_id}
          </p>
          {(r.from_district || r.to_district) && (
            <p className="text-[10px] text-slate-400">
              {r.from_district || "District"} → {r.to_district || "District"}
            </p>
          )}
        </div>
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
      header: "Stage",
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

  const filteredReferrals =
    selectedDistrict === "ALL"
      ? referrals
      : referrals.filter(
          (r) =>
            (r.from_district || "").toLowerCase() === selectedDistrict.toLowerCase() ||
            (r.to_district || "").toLowerCase() === selectedDistrict.toLowerCase()
        );

  return (
    <DashboardLayout
      user={user}
      tierBadge={{ label: "State Command Tier", color: "teal" }}
      title={`${stateName} Health Command & Capacity Dashboard`}
      subtitle={`State Health Authority: ${user.name} • Multi-District Coordination`}
      tabs={[
        { id: "overview", label: "State Overview", icon: "📊" },
        { id: "districts", label: "District Capacity Matrix", icon: "🏛️", badge: districts.length },
        { id: "referrals", label: "State Transfer Flows", icon: "🔄", badge: referrals.length },
      ]}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onRefresh={loadData}
      refreshLoading={loading}
    >
      {error && (
        <ErrorState
          title="State Health Dashboard Notice"
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
          {/* Top KPI Metrics */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              title="Monitored Districts"
              value={metrics.total_districts}
              subtitle={`${metrics.total_hospitals} reporting facilities`}
              icon="🏛️"
              variant="primary"
            />
            <StatCard
              title="State Bed Occupancy"
              value={formatPercent(metrics.bed_occupancy_rate)}
              subtitle={`${metrics.available_beds} of ${metrics.total_beds} beds free`}
              icon="🛏️"
              variant={metrics.bed_occupancy_rate > 80 ? "warning" : "default"}
            />
            <StatCard
              title="State ICU Occupancy"
              value={formatPercent(metrics.icu_occupancy_rate)}
              subtitle={`${metrics.available_icu_beds} of ${metrics.total_icu_beds} ICU free`}
              icon="⚡"
              variant={metrics.icu_occupancy_rate > 85 ? "danger" : "purple"}
            />
            <StatCard
              title="Statewide Transfers"
              value={metrics.total_referrals}
              subtitle="Coordinated patient journeys"
              icon="🔄"
              variant="primary"
            />
          </div>

          {/* District Capacity Preview Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">
                  District Bed & ICU Availability Matrix
                </h3>
                <p className="text-xs text-slate-400">
                  Real-time occupancy across all districts in {stateName}
                </p>
              </div>
              <button
                onClick={() => setActiveTab("districts")}
                className="text-xs font-semibold text-teal-400 hover:text-teal-300"
              >
                View Full Matrix →
              </button>
            </div>
            <div className="mt-4">
              <DataTable
                columns={districtColumns}
                data={districts}
                keyExtractor={(d) => d.district}
                loading={loading}
                emptyTitle="No District Records"
                pageSize={5}
              />
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 2: DISTRICTS */}
      {/* ============================================================ */}
      {activeTab === "districts" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">District-Wise Capacity Breakdown</h3>
              <p className="text-xs text-slate-400">
                Hospital bed inventory, ICU availability, and current occupancy across {stateName}
              </p>
            </div>
          </div>

          <DataTable
            columns={districtColumns}
            data={districts}
            keyExtractor={(d) => d.district}
            loading={loading}
            searchPlaceholder="Search district name..."
            searchFilterKeys={["district"]}
            emptyTitle="No Districts Found"
            pageSize={10}
          />
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 3: REFERRALS */}
      {/* ============================================================ */}
      {activeTab === "referrals" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">Statewide Transfer Logistics</h3>
              <p className="text-xs text-slate-400">
                Inter-district and intra-state hospital referrals
              </p>
            </div>

            {/* District Filter Dropdown */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Filter by District:</label>
              <select
                value={selectedDistrict}
                onChange={(e) => setSelectedDistrict(e.target.value)}
                className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white outline-none focus:border-teal-500"
              >
                <option value="ALL">All Districts ({referrals.length})</option>
                {districts.map((d) => (
                  <option key={d.district} value={d.district}>
                    {d.district}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <DataTable
            columns={referralColumns}
            data={filteredReferrals}
            keyExtractor={(r) => r.referral_id}
            loading={loading}
            searchPlaceholder="Search Case ID, Patient ID, or Hospital..."
            searchFilterKeys={["referral_id", "patient_id", "from_hospital_id", "to_hospital_id"]}
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
            emptyTitle="No Referrals Found"
            emptyDescription="There are no transfer records matching the selected district or status."
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
                State Referral Case Audit
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
