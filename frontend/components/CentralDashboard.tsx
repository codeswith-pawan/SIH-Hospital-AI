"use client";

import React, { useEffect, useState } from "react";
import { User, CentralMetrics, StateSummary, NotificationItem } from "@/lib/types";
import {
  apiGetCentralOverview,
  apiGetReviewerNotifications,
  apiMarkReviewerNotificationRead,
  apiMarkAllReviewerNotificationsRead,
} from "@/lib/api";
import { formatPercent } from "@/lib/formatters";
import { DashboardLayout } from "./shared/DashboardLayout";
import { StatCard } from "./shared/StatCard";
import { DataTable, Column } from "./shared/DataTable";
import { ErrorState } from "./shared/LoadingAndErrorStates";
import { ReviewerPortal } from "./reviewer/ReviewerPortal";

interface CentralDashboardProps {
  user: User;
}

export default function CentralDashboard({ user }: CentralDashboardProps) {
  const [activeTab, setActiveTab] = useState("national");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [metrics, setMetrics] = useState<CentralMetrics | null>(null);
  const [states, setStates] = useState<StateSummary[]>([]);

  // Notifications State (Phase 4D-2)
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifLoading, setNotifLoading] = useState(false);

  const loadNotifications = async () => {
    setNotifLoading(true);
    try {
      const data = await apiGetReviewerNotifications();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // Background poll failure
    } finally {
      setNotifLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    setError("");

    try {
      const data = await apiGetCentralOverview();
      setMetrics(data.metrics);
      setStates(data.states || []);

      // Load Central Notifications
      loadNotifications();
    } catch (err: any) {
      setError(err.message || "Failed to load national health coordination overview.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    loadNotifications();
  }, []);

  // State Summary Columns
  const stateColumns: Column<StateSummary>[] = [
    {
      key: "state",
      header: "State / Union Territory",
      render: (s) => (
        <div>
          <span className="font-bold text-white">{s.state}</span>
          <p className="text-[10px] text-slate-400">Participating Tier</p>
        </div>
      ),
    },
    {
      key: "hospitals",
      header: "Empanelled Hospitals",
      render: (s) => <span className="font-semibold text-slate-200">{s.hospitals}</span>,
    },
    {
      key: "beds",
      header: "Total Capacity (Available / Total)",
      render: (s) => (
        <div>
          <span className="font-bold text-slate-200">
            {s.available_beds} / {s.total_beds}
          </span>
          <p className="text-[10px] text-slate-400">General Beds</p>
        </div>
      ),
    },
    {
      key: "icu",
      header: "Critical Care (Available / Total ICU)",
      render: (s) => (
        <div>
          <span
            className={`font-bold ${
              s.available_icu > 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {s.available_icu} / {s.total_icu}
          </span>
          <p className="text-[10px] text-slate-400">ICU Units</p>
        </div>
      ),
    },
    {
      key: "occupancy",
      header: "Aggregate Occupancy",
      render: (s) => {
        const occ = s.occupancy_rate;
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
  ];

  return (
    <DashboardLayout
      user={user}
      tierBadge={{ label: "Central Government Tier", color: "purple" }}
      title="National Hospital Coordination & Capacity Overview"
      subtitle={`Administrator: ${user.name} • Privacy-Preserving Aggregate Macro-Health Surveillance`}
      tabs={[
        { id: "national", label: "National Command", icon: "🌐" },
        { id: "states", label: "State Capacity Matrix", icon: "📊", badge: states.length },
        { id: "registration", label: "National Registration & Approvals", icon: "📋" },
      ]}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onRefresh={loadData}
      refreshLoading={loading}
      notifications={notifications}
      unreadCount={unreadCount}
      notifLoading={notifLoading}
      onMarkNotifRead={(nid) => {
        apiMarkReviewerNotificationRead(nid).then(loadNotifications);
      }}
      onMarkAllNotifsRead={() => {
        apiMarkAllReviewerNotificationsRead().then(loadNotifications);
      }}
    >
      {error && (
        <ErrorState
          title="National Surveillance Notice"
          message={error}
          onRetry={loadData}
          className="mb-6"
        />
      )}

      {/* ============================================================ */}
      {/* TAB 1: NATIONAL OVERVIEW */}
      {/* ============================================================ */}
      {activeTab === "national" && metrics && (
        <div className="space-y-6">
          {/* Top KPI Metrics */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              title="Participating States"
              value={metrics.participating_states}
              subtitle={`${metrics.total_hospitals} reporting hospitals`}
              icon="🇮🇳"
              variant="purple"
            />
            <StatCard
              title="National Bed Occupancy"
              value={formatPercent(metrics.bed_occupancy_rate)}
              subtitle={`${metrics.available_beds} of ${metrics.total_beds} total beds free`}
              icon="🛏️"
              variant={metrics.bed_occupancy_rate > 80 ? "warning" : "default"}
            />
            <StatCard
              title="National ICU Occupancy"
              value={formatPercent(metrics.icu_occupancy_rate)}
              subtitle={`${metrics.available_icu_beds} of ${metrics.total_icu_beds} ICU beds free`}
              icon="⚡"
              variant={metrics.icu_occupancy_rate > 85 ? "danger" : "purple"}
            />
            <StatCard
              title="Nationwide Referrals"
              value={metrics.total_referrals}
              subtitle={`${metrics.interstate_referrals} interstate transfers`}
              icon="🔄"
              variant="primary"
            />
          </div>

          {/* Secondary Registration & Capacity Stats */}
          {metrics.approved_hospitals !== undefined && (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard
                title="Approved Facilities"
                value={metrics.approved_hospitals}
                subtitle="Empanelled & active in system"
                icon="✅"
                variant="default"
              />
              <StatCard
                title="Pending Registrations"
                value={metrics.pending_applications ?? 0}
                subtitle="Awaiting administrative review"
                icon="⏳"
                variant={(metrics.pending_applications ?? 0) > 0 ? "warning" : "default"}
              />
              <StatCard
                title="Active Bed Reservations"
                value={metrics.total_reserved_beds ?? 0}
                subtitle="Reserved / confirmed in transit"
                icon="🔒"
                variant="purple"
              />
              <StatCard
                title="Application Approvals"
                value={metrics.approved_applications ?? 0}
                subtitle="Processed onboarding requests"
                icon="📋"
                variant="primary"
              />
            </div>
          )}

          {/* Privacy Architecture Notice */}
          <div className="rounded-xl border border-purple-500/20 bg-purple-950/20 p-4 text-xs text-purple-200">
            <p className="font-semibold text-purple-300">
              🔒 Privacy-Preserving Aggregate Architecture:
            </p>
            <p className="mt-1 text-slate-300 leading-relaxed">
              In accordance with national healthcare privacy standards and DISHA guidelines, the Central Administrator role views only privacy-safe statistical aggregates, capacity metrics, and anonymized interstate transfer trends. Individual patient identities and detailed clinical notes remain strictly isolated within hospital and district jurisdictions.
            </p>
          </div>

          {/* State Capacity Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">
                  State-Level Capacity & Resource Distribution
                </h3>
                <p className="text-xs text-slate-400">
                  Real-time bed availability and critical care metrics across states
                </p>
              </div>
              <button
                onClick={() => setActiveTab("states")}
                className="text-xs font-semibold text-purple-400 hover:text-purple-300"
              >
                View Full Table →
              </button>
            </div>
            <div className="mt-4">
              <DataTable
                columns={stateColumns}
                data={states}
                keyExtractor={(s) => s.state}
                loading={loading}
                emptyTitle="No State Data Available"
                pageSize={5}
              />
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 2: STATES MATRIX */}
      {/* ============================================================ */}
      {activeTab === "states" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">All State & UT Capacity Matrix</h3>
              <p className="text-xs text-slate-400">
                Hospital counts, total beds, available ICU capacity, and occupancy rates
              </p>
            </div>
          </div>

          <DataTable
            columns={stateColumns}
            data={states}
            keyExtractor={(s) => s.state}
            loading={loading}
            searchPlaceholder="Search state or union territory..."
            searchFilterKeys={["state"]}
            emptyTitle="No State Records Found"
            pageSize={10}
          />
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 3: NATIONAL REGISTRATION & APPROVALS (Reviewer Portal)  */}
      {/* ============================================================ */}
      {activeTab === "registration" && (
        <ReviewerPortal user={user} />
      )}
    </DashboardLayout>
  );
}
