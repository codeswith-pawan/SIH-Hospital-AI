"use client";

import React, { useState } from "react";
import { ReviewerApplicationSummary, Role } from "@/lib/types";
import { formatDateTime } from "@/lib/formatters";

interface ReviewerInboxTableProps {
  applications: ReviewerApplicationSummary[];
  total: number;
  loading: boolean;
  onSelectApplication: (appId: string) => void;
  statusFilter: string;
  onStatusFilterChange: (val: string) => void;
  stageFilter: string;
  onStageFilterChange: (val: string) => void;
  typeFilter: string;
  onTypeFilterChange: (val: string) => void;
  onRefresh: () => void;
  role: Role;
}

export const ReviewerInboxTable: React.FC<ReviewerInboxTableProps> = ({
  applications,
  total,
  loading,
  onSelectApplication,
  statusFilter,
  onStatusFilterChange,
  stageFilter,
  onStageFilterChange,
  typeFilter,
  onTypeFilterChange,
  onRefresh,
  role,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Client-side search refinement on loaded batch
  const filtered = applications.filter((app) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      app.application_number.toLowerCase().includes(q) ||
      app.applicant_name.toLowerCase().includes(q) ||
      app.applicant_email.toLowerCase().includes(q) ||
      (app.district && app.district.toLowerCase().includes(q)) ||
      app.state.toLowerCase().includes(q)
    );
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pagedApps = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "APPROVED":
      case "PROVISIONED":
        return "bg-emerald-500/10 text-emerald-300 border-emerald-500/30";
      case "REJECTED":
        return "bg-rose-500/10 text-rose-300 border-rose-500/30";
      case "CORRECTION_REQUIRED":
        return "bg-amber-500/10 text-amber-300 border-amber-500/30";
      case "SUBMITTED":
      case "UNDER_REVIEW":
        return "bg-blue-500/10 text-blue-300 border-blue-500/30";
      case "DRAFT":
      default:
        return "bg-slate-700/20 text-slate-300 border-slate-600/30";
    }
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "HOSPITAL":
        return "bg-blue-500/10 text-blue-300 border-blue-500/20";
      case "DISTRICT":
        return "bg-indigo-500/10 text-indigo-300 border-indigo-500/20";
      case "STATE":
        return "bg-teal-500/10 text-teal-300 border-teal-500/20";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl overflow-hidden">
      {/* Top Controls Bar */}
      <div className="p-4 sm:p-5 border-b border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="Search by application #, name, or jurisdiction..."
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2 pl-9 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500"
          />
          <span className="absolute left-3 top-2.5 text-xs text-slate-500">🔍</span>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={statusFilter}
            onChange={(e) => {
              onStatusFilterChange(e.target.value);
              setCurrentPage(1);
            }}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
          >
            <option value="">All Statuses</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="CORRECTION_REQUIRED">Correction Required</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
          </select>

          <select
            value={stageFilter}
            onChange={(e) => {
              onStageFilterChange(e.target.value);
              setCurrentPage(1);
            }}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
          >
            <option value="">All Stages</option>
            <option value="DISTRICT_REVIEW">District Review</option>
            <option value="STATE_REVIEW">State Review</option>
            <option value="CENTRAL_REVIEW">Central Review</option>
          </select>

          <select
            value={typeFilter}
            onChange={(e) => {
              onTypeFilterChange(e.target.value);
              setCurrentPage(1);
            }}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
          >
            <option value="">All Types</option>
            <option value="HOSPITAL">Hospital</option>
            <option value="DISTRICT">District</option>
            <option value="STATE">State</option>
          </select>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition disabled:opacity-50"
            title="Refresh application queue"
          >
            {loading ? "⟳" : "↻ Refresh"}
          </button>
        </div>
      </div>

      {/* Table Area */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800/80 bg-slate-950/60 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              <th className="py-3 px-4">Application #</th>
              <th className="py-3 px-4">Applicant / Institution</th>
              <th className="py-3 px-4">Tier</th>
              <th className="py-3 px-4">Jurisdiction</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Current Stage</th>
              <th className="py-3 px-4 text-center">Docs</th>
              <th className="py-3 px-4">Submitted</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {loading ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                    <span>Loading reviewer queue...</span>
                  </div>
                </td>
              </tr>
            ) : pagedApps.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="text-3xl">📭</span>
                    <span className="font-semibold text-slate-300">No applications match the selected criteria.</span>
                    <p className="text-[11px] text-slate-500 max-w-sm">
                      Check your filters or refresh the queue to view newly submitted applications in your jurisdiction.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              pagedApps.map((app) => (
                <tr
                  key={app.application_id}
                  className="hover:bg-slate-800/40 transition group cursor-pointer"
                  onClick={() => onSelectApplication(app.application_id)}
                >
                  <td className="py-3 px-4 font-mono font-semibold text-blue-400">
                    {app.application_number}
                    {app.resubmission_version > 1 && (
                      <span className="ml-1 text-[10px] text-amber-400 font-normal">
                        (v{app.resubmission_version})
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <p className="font-semibold text-white group-hover:text-blue-300 transition">
                      {app.applicant_name}
                    </p>
                    <p className="text-[11px] text-slate-400 truncate max-w-xs">{app.applicant_email}</p>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getTypeBadge(
                        app.applicant_type
                      )}`}
                    >
                      {app.applicant_type}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-300">
                    {app.district ? `${app.district}, ` : ""}
                    <strong className="text-white">{app.state}</strong>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getStatusBadge(
                        app.status
                      )}`}
                    >
                      {app.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-medium text-slate-300">
                    {app.current_stage.replace(/_/g, " ")}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`font-semibold ${
                        app.pending_documents_count > 0 ? "text-amber-400" : "text-emerald-400"
                      }`}
                    >
                      {app.documents_count - app.pending_documents_count} / {app.documents_count}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                    {app.submitted_at ? formatDateTime(app.submitted_at) : "Draft"}
                  </td>
                  <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => onSelectApplication(app.application_id)}
                      className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-blue-600 hover:border-blue-500 hover:text-white transition shadow-sm"
                    >
                      Review Dossier →
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {!loading && filtered.length > 0 && (
        <div className="p-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing {(currentPage - 1) * pageSize + 1} to{" "}
            {Math.min(currentPage * pageSize, filtered.length)} of {filtered.length} entries
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition"
            >
              Previous
            </button>
            <span className="font-mono text-slate-300">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
