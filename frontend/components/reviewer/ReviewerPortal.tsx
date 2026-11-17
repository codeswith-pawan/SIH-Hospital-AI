"use client";

import React, { useState, useEffect } from "react";
import { User, ReviewerApplicationSummary, ReviewerApplicationDetail } from "@/lib/types";
import { apiGetReviewerApplications, apiGetReviewerApplicationDetail } from "@/lib/api";
import { ReviewerDashboardStats } from "./ReviewerDashboardStats";
import { ReviewerInboxTable } from "./ReviewerInboxTable";
import { ReviewerDossierView } from "./ReviewerDossierView";

interface ReviewerPortalProps {
  user: User;
  initialApplicationId?: string | null;
}

export const ReviewerPortal: React.FC<ReviewerPortalProps> = ({
  user,
  initialApplicationId = null,
}) => {
  const [applications, setApplications] = useState<ReviewerApplicationSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  // Selected Dossier
  const [selectedAppId, setSelectedAppId] = useState<string | null>(initialApplicationId);
  const [dossier, setDossier] = useState<ReviewerApplicationDetail | null>(null);
  const [dossierLoading, setDossierLoading] = useState(false);

  const loadApplications = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await apiGetReviewerApplications({
        status: statusFilter || undefined,
        stage: stageFilter || undefined,
        applicant_type: typeFilter || undefined,
        limit: 50,
      });
      setApplications(res.applications || []);
      setTotalCount(res.total || 0);
    } catch (err: any) {
      setError(err.message || "Failed to load assigned registration applications.");
    } finally {
      setLoading(false);
    }
  };

  const loadDossier = async (appId: string) => {
    setDossierLoading(true);
    setError("");

    try {
      const data = await apiGetReviewerApplicationDetail(appId);
      setDossier(data);
      setSelectedAppId(appId);
    } catch (err: any) {
      setError(err.message || "Failed to load application dossier.");
      setSelectedAppId(null);
      setDossier(null);
    } finally {
      setDossierLoading(false);
    }
  };

  useEffect(() => {
    loadApplications();
  }, [statusFilter, stageFilter, typeFilter]);

  useEffect(() => {
    if (initialApplicationId) {
      loadDossier(initialApplicationId);
    }
  }, [initialApplicationId]);

  const handleSelectApplication = (appId: string) => {
    loadDossier(appId);
  };

  const handleBackToInbox = () => {
    setSelectedAppId(null);
    setDossier(null);
    loadApplications();
  };

  return (
    <div className="space-y-6">
      {/* Global Notice */}
      {error && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
          <span className="text-base">⚠️</span>
          <div className="flex-1">{error}</div>
        </div>
      )}

      {/* VIEW A: APPLICATION DOSSIER */}
      {selectedAppId && dossier ? (
        <ReviewerDossierView
          application={dossier}
          role={user.role}
          onBack={handleBackToInbox}
          onApplicationUpdated={() => {
            loadDossier(selectedAppId);
            loadApplications();
          }}
        />
      ) : dossierLoading ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-12 text-center text-slate-400">
          <div className="flex flex-col items-center justify-center gap-3">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className="text-xs font-semibold text-slate-300">Loading complete application dossier...</span>
          </div>
        </div>
      ) : (
        /* VIEW B: REVIEWER DASHBOARD & INBOX */
        <div className="space-y-6">
          {/* Top Summary Stats */}
          <ReviewerDashboardStats
            applications={applications}
            totalCount={totalCount}
            role={user.role}
          />

          {/* Searchable Inbox Table */}
          <ReviewerInboxTable
            applications={applications}
            total={totalCount}
            loading={loading}
            onSelectApplication={handleSelectApplication}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            stageFilter={stageFilter}
            onStageFilterChange={setStageFilter}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            onRefresh={loadApplications}
            role={user.role}
          />
        </div>
      )}
    </div>
  );
};
