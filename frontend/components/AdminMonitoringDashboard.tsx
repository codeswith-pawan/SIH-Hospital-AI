"use client";

import React, { useEffect, useState, useCallback } from "react";
import { User } from "@/lib/types";
import { apiFetch, getStoredUser } from "@/lib/api";
import { LoadingState, ErrorState } from "./shared/LoadingAndErrorStates";
import { StatCard } from "./shared/StatCard";

// ----------------------------------------------------------------------
// TypeScript Interfaces for Telemetry & Alerting Payloads
// ----------------------------------------------------------------------

export interface ActiveAlert {
  key: string;
  condition: string;
  severity: "WARNING" | "CRITICAL" | string;
  value?: unknown;
  threshold?: unknown;
  triggered_at?: string;
  message?: string;
}

export interface AlertSummary {
  total_active: number;
  critical_count: number;
  warning_count: number;
  status: "HEALTHY" | "WARNING" | "CRITICAL" | string;
  alerts: ActiveAlert[];
  evaluated_at?: string;
}

export interface ServerMetrics {
  uptime_since?: string;
  total_requests: number;
  status_2xx: number;
  status_3xx: number;
  status_4xx: number;
  status_5xx: number;
  total_errors: number;
  average_latency_ms: number;
}

export interface EmailOutboxQueueMetrics {
  pending: number;
  sent: number;
  failed: number;
  processing: number;
  oldest_pending_age_seconds?: number;
  unread_notifications_by_type?: Record<string, number>;
}

export interface WorkerDetails {
  reservation_expiry_worker_running?: boolean;
  status?: string;
  heartbeat_age_seconds?: number | null;
  reservation_expiry_processed_total?: number;
  reservation_expiry_failed_total?: number;
  reservation_expiry_batch_size?: number;
  reservation_expiry_processing_duration_seconds?: number;
  reservation_expiry_last_error_timestamp?: string | null;
  reservation_expiry_last_success_timestamp?: string | null;
  worker_id?: string;
}

export interface PoolStats {
  pool_type?: string;
  utilization_pct?: number;
  checked_out?: number;
  pool_size?: number;
  overflow?: number;
  checked_in?: number;
}

export interface PerRouteMetric {
  count: number;
  status_2xx?: number;
  status_4xx?: number;
  status_5xx?: number;
  total_duration_ms?: number;
}

export interface SystemMetrics {
  server: ServerMetrics;
  email_outbox_queue: EmailOutboxQueueMetrics;
  reservation_expiry_worker: WorkerDetails;
  reservation_expiry_worker_running: boolean;
  outbox_worker_running: boolean;
  outbox_worker_status: string;
  outbox_worker_heartbeat_age_seconds: number | null;
  pool_stats: PoolStats;
  per_route_metrics: Record<string, PerRouteMetric>;
  latency_histogram_seconds: Record<string, number>;
  in_flight_requests: number;
  timestamp: string;
}

export interface AdminMonitoringResponse {
  system_metrics: SystemMetrics;
  alerts: AlertSummary;
  dashboard_version: string;
  generated_at: string;
}

export interface AdminMonitoringDashboardProps {
  user?: User | null;
  onRefresh?: () => void;
}

// ----------------------------------------------------------------------
// Main AdminMonitoringDashboard Component
// ----------------------------------------------------------------------

export default function AdminMonitoringDashboard({
  user,
}: AdminMonitoringDashboardProps) {
  // Resolve current active user (from props or local session storage)
  const [currentUser, setCurrentUser] = useState<User | null>(user || null);

  useEffect(() => {
    if (!currentUser) {
      const stored = getStoredUser();
      if (stored) {
        setCurrentUser(stored);
      }
    }
  }, [currentUser]);

  const [data, setData] = useState<AdminMonitoringResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string>("");

  // Data Fetching Handler with Automatic Endpoint Fallback
  const fetchDashboardData = useCallback(async (isSilent = false) => {
    if (!isSilent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError("");

    try {
      let result: AdminMonitoringResponse;
      try {
        result = await apiFetch<AdminMonitoringResponse>("/api/admin/monitoring");
      } catch {
        // Fallback to direct path if proxy rewrite is not configured
        result = await apiFetch<AdminMonitoringResponse>("/admin/monitoring");
      }

      setData(result);
      setLastRefreshedAt(new Date().toLocaleTimeString());
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load admin monitoring telemetry.";
      setError(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Periodic Auto-refresh every 30 seconds
  useEffect(() => {
    // Check role before making telemetry requests
    const activeRole = user?.role || currentUser?.role;
    if (activeRole !== "CENTRAL_ADMIN") {
      setLoading(false);
      return;
    }

    fetchDashboardData(false);

    const intervalId = setInterval(() => {
      fetchDashboardData(true);
    }, 30000);

    return () => clearInterval(intervalId);
  }, [user, currentUser, fetchDashboardData]);

  // --------------------------------------------------------------------
  // Role Access Restriction Guard
  // --------------------------------------------------------------------
  const activeRole = user?.role || currentUser?.role;
  if (activeRole && activeRole !== "CENTRAL_ADMIN") {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-8 text-center text-rose-200">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-500/20 text-3xl">
          🛡️
        </div>
        <h2 className="mt-4 text-xl font-bold text-white">Access Restricted</h2>
        <p className="mt-2 text-sm text-rose-300/80">
          The Operational Monitoring Dashboard is reserved strictly for Central
          System Administrators (<code className="rounded bg-rose-900/40 px-1.5 py-0.5 text-xs font-mono text-rose-200">CENTRAL_ADMIN</code>).
        </p>
        <p className="mt-1 text-xs text-rose-400/60">
          Your current account role: {activeRole}
        </p>
      </div>
    );
  }

  // Loading State
  if (loading && !data) {
    return (
      <div className="flex min-h-[400px] items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/60 p-12">
        <LoadingState
          message="Querying system telemetry, worker heartbeats, and threshold evaluation engine..."
          size="lg"
        />
      </div>
    );
  }

  // Error State (Initial load failure)
  if (error && !data) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-8">
        <ErrorState
          title="Telemetry Connection Error"
          message={error}
          onRetry={() => fetchDashboardData(false)}
        />
      </div>
    );
  }

  // No Data State
  if (!data) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-12 text-center text-slate-400">
        <span className="text-4xl">📡</span>
        <h3 className="mt-3 text-lg font-semibold text-slate-200">
          No Monitoring Telemetry Received
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          The telemetry service has not returned metric samples yet.
        </p>
        <button
          onClick={() => fetchDashboardData(false)}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-blue-500"
        >
          Retry Telemetry Query
        </button>
      </div>
    );
  }

  const { system_metrics: metrics, alerts } = data;
  const server = metrics.server || {
    total_requests: 0,
    status_2xx: 0,
    status_3xx: 0,
    status_4xx: 0,
    status_5xx: 0,
    total_errors: 0,
    average_latency_ms: 0,
  };
  const queue = metrics.email_outbox_queue || {
    pending: 0,
    sent: 0,
    failed: 0,
    processing: 0,
    oldest_pending_age_seconds: 0,
  };
  const pool = metrics.pool_stats || {};
  const expiryWorker = metrics.reservation_expiry_worker || {};

  // Computed Values
  const totalReqs = server.total_requests || 0;
  const errorCount5xx = server.status_5xx || 0;
  const errorRatePct =
    totalReqs > 0 ? ((errorCount5xx / totalReqs) * 100).toFixed(2) : "0.00";
  const overallErrorRatePct =
    totalReqs > 0
      ? (((server.status_5xx + server.status_4xx) / totalReqs) * 100).toFixed(2)
      : "0.00";

  // Top 10 Routes Calculation
  const topRoutes = Object.entries(metrics.per_route_metrics || {})
    .map(([key, item]) => {
      const parts = key.split(" ");
      const method = parts.length > 1 ? parts[0] : "GET";
      const path = parts.length > 1 ? parts.slice(1).join(" ") : key;
      return {
        key,
        method,
        path,
        count: item.count || 0,
        status_5xx: item.status_5xx || 0,
        status_2xx: item.status_2xx || 0,
        status_4xx: item.status_4xx || 0,
        avgLatencyMs:
          item.count > 0 && item.total_duration_ms
            ? (item.total_duration_ms / item.count).toFixed(1)
            : "—",
      };
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  // Latency Histogram Buckets
  const latencyBuckets = Object.entries(metrics.latency_histogram_seconds || {})
    .map(([rawBucket, count]) => {
      const label = rawBucket === "+Inf" ? "> 10.0s" : `≤ ${rawBucket}s`;
      return {
        label,
        rawBucket,
        count: count || 0,
      };
    });
  const maxBucketCount = Math.max(1, ...latencyBuckets.map((b) => b.count));

  // Helper Badge Colors
  const getStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "HEALTHY" || s === "RUNNING") {
      return {
        bg: "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
        dot: "bg-emerald-400",
        label: s,
      };
    }
    if (s === "WARNING" || s === "STALE") {
      return {
        bg: "bg-amber-500/15 border-amber-500/30 text-amber-300",
        dot: "bg-amber-400",
        label: s,
      };
    }
    return {
      bg: "bg-rose-500/15 border-rose-500/30 text-rose-300",
      dot: "bg-rose-400",
      label: s || "STOPPED",
    };
  };

  const alertOverallBadge = getStatusBadge(alerts?.status || "HEALTHY");

  return (
    <div className="space-y-6">
      {/* Top Header / Action Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-slate-800 bg-slate-900/80 p-5 backdrop-blur-md">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
              System Observability & Monitoring
            </h2>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${alertOverallBadge.bg}`}
            >
              <span className={`h-2 w-2 rounded-full ${alertOverallBadge.dot} animate-pulse`} />
              {alertOverallBadge.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Real-time infrastructure health, background workers, connection pool, and threshold alerting (Phase 4D-4)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-ping" />
            <span>Auto-refresh: 30s</span>
          </div>
          <button
            onClick={() => fetchDashboardData(false)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700 hover:text-white disabled:opacity-50"
            title="Force immediate telemetry poll"
          >
            <span className={refreshing ? "animate-spin" : ""}>🔄</span>
            {refreshing ? "Refreshing..." : "Refresh Now"}
          </button>
        </div>
      </div>

      {error && (
        <ErrorState
          title="Telemetry Polling Issue"
          message={error}
          onRetry={() => fetchDashboardData(false)}
        />
      )}

      {/* ============================================================ */}
      {/* PANEL 1: ALERT SUMMARY */}
      {/* ============================================================ */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="text-lg">🔔</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
              Panel 1: Alert Summary
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">
              Active: <strong className="text-white">{alerts?.total_active ?? 0}</strong>
            </span>
            <span
              className={`rounded-md border px-2 py-0.5 text-xs font-bold ${alertOverallBadge.bg}`}
            >
              {alerts?.status || "HEALTHY"}
            </span>
          </div>
        </div>

        {(!alerts || alerts.alerts.length === 0) ? (
          <div className="mt-4 flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-emerald-300">
            <span className="text-2xl">✅</span>
            <div>
              <p className="text-sm font-semibold text-emerald-200">
                All Systems Nominal
              </p>
              <p className="text-xs text-emerald-300/80">
                No active threshold breaches. Error rates, worker heartbeats, and latency distributions are within normal production thresholds.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {alerts.alerts.map((alert, idx) => {
              const isCrit = alert.severity === "CRITICAL";
              return (
                <div
                  key={`${alert.key}-${idx}`}
                  className={`flex flex-col gap-2 rounded-xl border p-3.5 sm:flex-row sm:items-center sm:justify-between ${
                    isCrit
                      ? "border-rose-500/30 bg-rose-950/20 text-rose-200"
                      : "border-amber-500/30 bg-amber-950/20 text-amber-200"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-lg">{isCrit ? "🚨" : "⚠️"}</span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                            isCrit
                              ? "bg-rose-500/30 text-rose-200"
                              : "bg-amber-500/30 text-amber-200"
                          }`}
                        >
                          {alert.severity}
                        </span>
                        <code className="text-xs font-mono font-semibold text-white">
                          {alert.key}
                        </code>
                      </div>
                      <p className="mt-1 text-xs text-slate-300">
                        {alert.condition || alert.message || "Threshold breach detected"}
                      </p>
                    </div>
                  </div>

                  <div className="text-right text-[11px] text-slate-400 sm:text-xs">
                    {alert.triggered_at && (
                      <p>Triggered: {new Date(alert.triggered_at).toLocaleTimeString()}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ============================================================ */}
      {/* PANEL 2: API HEALTH */}
      {/* ============================================================ */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📈</span>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Panel 2: API Health & Throughput
          </h3>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard
            title="Total Requests"
            value={totalReqs.toLocaleString()}
            subtitle={`${server.status_2xx || 0} 2xx success`}
            icon="🌐"
            variant="primary"
          />
          <StatCard
            title="5xx Errors"
            value={errorCount5xx}
            subtitle={`${server.status_4xx || 0} client 4xx errors`}
            icon="💥"
            variant={errorCount5xx > 0 ? "danger" : "default"}
          />
          <StatCard
            title="5xx Error Rate"
            value={`${errorRatePct}%`}
            subtitle={`Overall: ${overallErrorRatePct}%`}
            icon="📊"
            variant={Number(errorRatePct) > 5 ? "danger" : Number(errorRatePct) > 1 ? "warning" : "success"}
          />
          <StatCard
            title="Average Latency"
            value={`${(server.average_latency_ms || 0).toFixed(1)} ms`}
            subtitle="Request lifecycle avg"
            icon="⏱️"
            variant={server.average_latency_ms > 1000 ? "danger" : "default"}
          />
          <StatCard
            title="In-Flight Requests"
            value={metrics.in_flight_requests ?? 0}
            subtitle="Active concurrent requests"
            icon="⚡"
            variant={metrics.in_flight_requests > 50 ? "warning" : "purple"}
          />
        </div>
      </section>

      {/* ============================================================ */}
      {/* PANEL 3 & 4: WORKER STATUS & EMAIL OUTBOX QUEUE */}
      {/* ============================================================ */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* PANEL 3: WORKER STATUS */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
            <span className="text-lg">⚙️</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
              Panel 3: Worker Status & Heartbeats
            </h3>
          </div>

          <div className="mt-4 space-y-4">
            {/* Outbox Worker */}
            {(() => {
              const outboxBadge = getStatusBadge(metrics.outbox_worker_status);
              const age = metrics.outbox_worker_heartbeat_age_seconds;
              return (
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-semibold text-white">
                        Outbox Dispatch Worker
                      </h4>
                      <p className="text-xs text-slate-400">
                        Transactional email & external dispatch pipeline
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${outboxBadge.bg}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${outboxBadge.dot}`} />
                      {outboxBadge.label}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-lg bg-slate-900 p-2.5">
                      <span className="text-slate-400">Heartbeat Age:</span>
                      <p className="mt-0.5 font-mono font-semibold text-slate-200">
                        {age !== null && age !== undefined ? `${age.toFixed(1)}s ago` : "No heartbeat recorded"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-2.5">
                      <span className="text-slate-400">Worker Status:</span>
                      <p className="mt-0.5 font-semibold text-slate-200">
                        {metrics.outbox_worker_running ? "Active Polling" : "Inactive / Idle"}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Reservation Expiry Worker */}
            {(() => {
              const expiryBadge = getStatusBadge(expiryWorker.status || "STOPPED");
              const age = expiryWorker.heartbeat_age_seconds;
              return (
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-semibold text-white">
                        Reservation Expiry Worker
                      </h4>
                      <p className="text-xs text-slate-400">
                        Automated bed hold release & referral expiration
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${expiryBadge.bg}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${expiryBadge.dot}`} />
                      {expiryBadge.label}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-lg bg-slate-900 p-2.5">
                      <span className="text-slate-400">Heartbeat Age:</span>
                      <p className="mt-0.5 font-mono font-semibold text-slate-200">
                        {age !== null && age !== undefined ? `${age.toFixed(1)}s ago` : "No heartbeat recorded"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-2.5">
                      <span className="text-slate-400">Processed / Failed:</span>
                      <p className="mt-0.5 font-mono font-semibold text-slate-200">
                        {expiryWorker.reservation_expiry_processed_total ?? 0} /{" "}
                        <span className={expiryWorker.reservation_expiry_failed_total ? "text-rose-400" : ""}>
                          {expiryWorker.reservation_expiry_failed_total ?? 0}
                        </span>
                      </p>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </section>

        {/* PANEL 4: EMAIL OUTBOX QUEUE */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">📬</span>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                Panel 4: Email Outbox Queue
              </h3>
            </div>
            <span className="text-xs text-slate-400">
              Oldest Pending:{" "}
              <strong
                className={
                  (queue.oldest_pending_age_seconds || 0) > 300
                    ? "text-rose-400"
                    : "text-slate-200"
                }
              >
                {queue.oldest_pending_age_seconds !== undefined
                  ? `${queue.oldest_pending_age_seconds}s`
                  : "0s"}
              </strong>
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-3 text-center">
              <span className="text-xs font-medium text-amber-300/80 uppercase">
                Pending
              </span>
              <p className="mt-1 text-2xl font-bold text-amber-200">
                {queue.pending}
              </p>
            </div>
            <div className="rounded-xl border border-blue-500/20 bg-blue-950/20 p-3 text-center">
              <span className="text-xs font-medium text-blue-300/80 uppercase">
                Processing
              </span>
              <p className="mt-1 text-2xl font-bold text-blue-200">
                {queue.processing}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3 text-center">
              <span className="text-xs font-medium text-emerald-300/80 uppercase">
                Sent
              </span>
              <p className="mt-1 text-2xl font-bold text-emerald-200">
                {queue.sent}
              </p>
            </div>
            <div
              className={`rounded-xl border p-3 text-center ${
                queue.failed > 0
                  ? "border-rose-500/30 bg-rose-950/30 text-rose-200"
                  : "border-slate-800 bg-slate-950/60 text-slate-400"
              }`}
            >
              <span className="text-xs font-medium uppercase">Failed</span>
              <p
                className={`mt-1 text-2xl font-bold ${
                  queue.failed > 0 ? "text-rose-400" : "text-slate-300"
                }`}
              >
                {queue.failed}
              </p>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">Queue Health Evaluation:</span>
              <span
                className={`font-semibold ${
                  queue.failed > 10
                    ? "text-rose-400"
                    : queue.pending > 50
                    ? "text-amber-400"
                    : "text-emerald-400"
                }`}
              >
                {queue.failed > 10
                  ? "Attention Required (High Failures)"
                  : queue.pending > 50
                  ? "Moderate Backlog"
                  : "Queue Flow Optimal"}
              </span>
            </div>
          </div>
        </section>
      </div>

      {/* ============================================================ */}
      {/* PANEL 5: DB POOL */}
      {/* ============================================================ */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">🗄️</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
              Panel 5: Database Connection Pool
            </h3>
          </div>
          <span className="rounded bg-slate-800 px-2 py-0.5 text-xs font-mono text-slate-300">
            Pool Type: {pool.pool_type || "Standard"}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-3">
          {/* Utilization Progress Bar */}
          <div className="md:col-span-2 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-300">
                Pool Utilization Rate
              </span>
              <span
                className={`text-sm font-bold ${
                  (pool.utilization_pct || 0) > 85
                    ? "text-rose-400"
                    : (pool.utilization_pct || 0) > 70
                    ? "text-amber-400"
                    : "text-emerald-400"
                }`}
              >
                {(pool.utilization_pct || 0).toFixed(1)}%
              </span>
            </div>

            <div className="mt-3 h-3 w-full rounded-full bg-slate-800 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 rounded-full ${
                  (pool.utilization_pct || 0) > 85
                    ? "bg-rose-500"
                    : (pool.utilization_pct || 0) > 70
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(100, Math.max(0, pool.utilization_pct || 0))}%` }}
              />
            </div>

            <p className="mt-2 text-[11px] text-slate-400">
              Safe operating threshold is &lt; 85%. Alerts fire automatically if connection saturation exceeds bounds.
            </p>
          </div>

          {/* Checked Out vs Capacity */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 flex flex-col justify-center">
            <span className="text-xs text-slate-400">Checked Out / Pool Size</span>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-white">
                {pool.checked_out ?? 0}
              </span>
              <span className="text-sm text-slate-400 font-mono">
                / {pool.pool_size ?? "N/A"}
              </span>
            </div>
            {pool.overflow !== undefined && (
              <p className="mt-1 text-[11px] text-slate-400">
                Overflow Connections: <strong className="text-slate-200">{pool.overflow}</strong>
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/* PANEL 6 & 7: LATENCY HISTOGRAM & TOP ROUTES */}
      {/* ============================================================ */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* PANEL 6: LATENCY HISTOGRAM */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
            <span className="text-lg">📊</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
              Panel 6: Latency Distribution Histogram
            </h3>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="pb-2 font-medium">Bucket Threshold</th>
                  <th className="pb-2 font-medium">Count</th>
                  <th className="pb-2 font-medium">Distribution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {latencyBuckets.map((item) => {
                  const pct = Math.round((item.count / maxBucketCount) * 100);
                  return (
                    <tr key={item.rawBucket} className="hover:bg-slate-800/30">
                      <td className="py-2 font-mono font-medium text-slate-200">
                        {item.label}
                      </td>
                      <td className="py-2 font-mono text-slate-300">
                        {item.count}
                      </td>
                      <td className="py-2 w-1/2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-full max-w-[140px] rounded-full bg-slate-800 overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {item.count}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* PANEL 7: TOP ROUTES */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">🛣️</span>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                Panel 7: Top Routes by Frequency
              </h3>
            </div>
            <span className="text-xs text-slate-400">Top 10 Endpoints</span>
          </div>

          {topRoutes.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              No per-route telemetry traffic recorded yet.
            </div>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="pb-2 font-medium">Method</th>
                    <th className="pb-2 font-medium">Path</th>
                    <th className="pb-2 font-medium text-right">Count</th>
                    <th className="pb-2 font-medium text-right">5xx Errors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {topRoutes.map((route, i) => {
                    const methodColor =
                      route.method === "GET"
                        ? "text-blue-400 bg-blue-500/10 border-blue-500/20"
                        : route.method === "POST"
                        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                        : route.method === "PUT"
                        ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                        : "text-rose-400 bg-rose-500/10 border-rose-500/20";

                    return (
                      <tr key={`${route.key}-${i}`} className="hover:bg-slate-800/30">
                        <td className="py-2.5">
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${methodColor}`}
                          >
                            {route.method}
                          </span>
                        </td>
                        <td className="py-2.5 text-slate-200 max-w-[200px] truncate" title={route.path}>
                          {route.path}
                        </td>
                        <td className="py-2.5 text-right text-slate-300 font-semibold">
                          {route.count}
                        </td>
                        <td className="py-2.5 text-right">
                          {route.status_5xx > 0 ? (
                            <span className="text-rose-400 font-bold">
                              {route.status_5xx}
                            </span>
                          ) : (
                            <span className="text-slate-500">0</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* ============================================================ */}
      {/* FOOTER */}
      {/* ============================================================ */}
      <footer className="flex flex-col sm:flex-row items-center justify-between rounded-xl border border-slate-800/80 bg-slate-900/60 px-5 py-3 text-xs text-slate-400">
        <div>
          <span>Last updated: </span>
          <strong className="text-slate-200">
            {lastRefreshedAt || data.generated_at || "Just now"}
          </strong>
        </div>
        <div className="mt-1 sm:mt-0 text-[11px] text-slate-500">
          Telemetry Dashboard v{data.dashboard_version || "4D-4"} • Zero-PII Aggregated Metrics
        </div>
      </footer>
    </div>
  );
}
