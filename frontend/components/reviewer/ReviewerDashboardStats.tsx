"use client";

import React from "react";
import { ReviewerApplicationSummary, Role } from "@/lib/types";

interface ReviewerDashboardStatsProps {
  applications: ReviewerApplicationSummary[];
  totalCount: number;
  role: Role;
}

export const ReviewerDashboardStats: React.FC<ReviewerDashboardStatsProps> = ({
  applications,
  totalCount,
  role,
}) => {
  // Determine relevant action stage based on reviewer role
  const myActionStage =
    role === "DISTRICT_ADMIN"
      ? "DISTRICT_REVIEW"
      : role === "STATE_ADMIN"
      ? "STATE_REVIEW"
      : "CENTRAL_REVIEW";

  const pendingCount = applications.filter(
    (a) => a.status === "SUBMITTED" || a.status === "UNDER_REVIEW"
  ).length;

  const awaitingMyAction = applications.filter(
    (a) => a.current_stage === myActionStage && a.status !== "APPROVED" && a.status !== "REJECTED"
  ).length;

  const correctionCount = applications.filter(
    (a) => a.status === "CORRECTION_REQUIRED"
  ).length;

  const approvedCount = applications.filter(
    (a) => a.status === "APPROVED" || a.status === "PROVISIONED"
  ).length;

  const rejectedCount = applications.filter(
    (a) => a.status === "REJECTED"
  ).length;

  const stats = [
    {
      label: "Total Applications",
      value: totalCount,
      icon: "📋",
      color: "border-slate-800 bg-slate-900/60 text-white",
      sub: "In reviewer jurisdiction",
    },
    {
      label: "Awaiting My Action",
      value: awaitingMyAction,
      icon: "⚡",
      color: "border-amber-500/40 bg-amber-950/20 text-amber-300",
      sub: `Pending at ${myActionStage.replace(/_/g, " ")}`,
      highlight: true,
    },
    {
      label: "Under Active Review",
      value: pendingCount,
      icon: "⏳",
      color: "border-blue-500/30 bg-blue-950/20 text-blue-300",
      sub: "Processing through workflow",
    },
    {
      label: "Correction Required",
      value: correctionCount,
      icon: "⚠️",
      color: "border-yellow-500/30 bg-yellow-950/20 text-yellow-300",
      sub: "Awaiting applicant resubmission",
    },
    {
      label: "Approved & Cleared",
      value: approvedCount,
      icon: "✓",
      color: "border-emerald-500/30 bg-emerald-950/20 text-emerald-300",
      sub: "Provisioned or forwarded",
    },
    {
      label: "Rejected",
      value: rejectedCount,
      icon: "✕",
      color: "border-rose-500/30 bg-rose-950/20 text-rose-300",
      sub: "Declined with remarks",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
      {stats.map((s, idx) => (
        <div
          key={idx}
          className={`rounded-2xl border p-4 flex flex-col justify-between transition ${s.color} ${
            s.highlight ? "ring-1 ring-amber-500/30 shadow-lg shadow-amber-900/10" : ""
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">{s.label}</span>
            <span className="text-lg">{s.icon}</span>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold tracking-tight">{s.value}</span>
            <p className="mt-1 text-[10px] text-slate-400 truncate">{s.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
};
