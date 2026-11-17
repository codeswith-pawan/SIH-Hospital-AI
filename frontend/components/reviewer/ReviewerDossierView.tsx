"use client";

import React, { useState } from "react";
import { ReviewerApplicationDetail, Role, ReviewDecisionPayload } from "@/lib/types";
import {
  apiVerifyReviewerDocument,
  apiExecuteReviewDecision,
  apiReviewerRequestCorrection,
  apiDownloadDocumentBlob,
} from "@/lib/api";
import { ApplicationTimeline } from "@/components/registration/ApplicationTimeline";
import { formatDateTime } from "@/lib/formatters";

interface ReviewerDossierViewProps {
  application: ReviewerApplicationDetail;
  role: Role;
  onBack: () => void;
  onApplicationUpdated: () => void;
}

export const ReviewerDossierView: React.FC<ReviewerDossierViewProps> = ({
  application,
  role,
  onBack,
  onApplicationUpdated,
}) => {
  // Action Modals State
  const [activeModal, setActiveModal] = useState<
    "FORWARD" | "APPROVE" | "REJECT" | "CORRECTION" | "DOC_REJECT" | "DOC_PREVIEW" | null
  >(null);

  // Selected document for rejection / preview
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [docRejectRemarks, setDocRejectRemarks] = useState("");
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewFilename, setPreviewFilename] = useState("");
  const [previewContentType, setPreviewContentType] = useState("");

  // Decision inputs
  const [decisionRemarks, setDecisionRemarks] = useState("");
  const [correctionNotes, setCorrectionNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  // Determine permitted decision actions based on role and stage
  const isDistrictReviewer = role === "DISTRICT_ADMIN";
  const isStateReviewer = role === "STATE_ADMIN";
  const isCentralReviewer = role === "CENTRAL_ADMIN";

  const isCurrentStageDistrict = application.current_stage === "DISTRICT_REVIEW";
  const isCurrentStageState = application.current_stage === "STATE_REVIEW";
  const isCurrentStageCentral = application.current_stage === "CENTRAL_REVIEW";

  const canActOnCurrentStage =
    (isDistrictReviewer && isCurrentStageDistrict) ||
    (isStateReviewer && isCurrentStageState) ||
    (isCentralReviewer && isCurrentStageCentral);

  const isTerminal = application.status === "APPROVED" || application.status === "REJECTED";

  // Check if all documents are verified
  const allDocumentsVerified =
    application.documents.length > 0 &&
    application.documents.every((d) => d.verification_status === "VERIFIED");

  // Document Verification Handlers
  const handleVerifyDocument = async (docId: string) => {
    setLoading(true);
    setError("");
    setActionSuccess("");

    try {
      await apiVerifyReviewerDocument(docId, { verification_status: "VERIFIED" });
      setActionSuccess("Document marked as verified.");
      onApplicationUpdated();
    } catch (err: any) {
      setError(err.message || "Failed to verify document.");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDocRejectModal = (docId: string) => {
    setSelectedDocId(docId);
    setDocRejectRemarks("");
    setActiveModal("DOC_REJECT");
  };

  const handleConfirmDocReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocId || !docRejectRemarks.trim()) {
      setError("Please provide a reason for rejecting the document.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await apiVerifyReviewerDocument(selectedDocId, {
        verification_status: "REJECTED",
        reviewer_remarks: docRejectRemarks.trim(),
      });
      setActiveModal(null);
      setSelectedDocId(null);
      setActionSuccess("Document marked as rejected with comments.");
      onApplicationUpdated();
    } catch (err: any) {
      setError(err.message || "Failed to reject document.");
    } finally {
      setLoading(false);
    }
  };

  // Secure Document Download & Preview
  const handlePreviewDocument = async (docId: string) => {
    setLoading(true);
    setError("");

    try {
      const { blob, filename, contentType } = await apiDownloadDocumentBlob(docId);
      const url = URL.createObjectURL(blob);
      setPreviewBlobUrl(url);
      setPreviewFilename(filename);
      setPreviewContentType(contentType);
      setActiveModal("DOC_PREVIEW");
    } catch (err: any) {
      setError(err.message || "Unable to download document payload.");
    } finally {
      setLoading(false);
    }
  };

  // Decision Execution Handler (FORWARD / APPROVE / REJECT)
  const handleExecuteDecision = async (action: "FORWARD" | "APPROVE" | "REJECT") => {
    setLoading(true);
    setError("");

    try {
      const payload: ReviewDecisionPayload = {
        action,
        remarks: decisionRemarks.trim() || undefined,
      };

      const res = await apiExecuteReviewDecision(application.application_id, payload);
      setActiveModal(null);
      setDecisionRemarks("");
      setActionSuccess(
        `Decision '${action}' executed successfully. Application transitioned to ${res.new_stage.replace(
          /_/g,
          " "
        )} (${res.new_status}).`
      );
      onApplicationUpdated();
    } catch (err: any) {
      setError(err.message || "Failed to execute decision.");
    } finally {
      setLoading(false);
    }
  };

  // Request Correction Handler
  const handleExecuteCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (correctionNotes.trim().length < 5) {
      setError("Please provide specific correction instructions (minimum 5 characters).");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await apiReviewerRequestCorrection(application.application_id, {
        correction_notes: correctionNotes.trim(),
      });
      setActiveModal(null);
      setCorrectionNotes("");
      setActionSuccess("Correction request dispatched to applicant. Status set to CORRECTION_REQUIRED.");
      onApplicationUpdated();
    } catch (err: any) {
      setError(err.message || "Failed to submit correction request.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition"
        >
          ← Back to Application Queue
        </button>

        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-slate-400">Application:</span>
          <span className="rounded-lg bg-blue-600/20 border border-blue-500/30 px-3 py-1 font-mono text-xs font-bold text-blue-300">
            {application.application_number}
          </span>
        </div>
      </div>

      {/* Global Alerts */}
      {error && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
          <span className="text-base">⚠️</span>
          <div className="flex-1">{error}</div>
        </div>
      )}

      {actionSuccess && (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-xs text-emerald-300 flex items-start gap-3">
          <span className="text-base">✓</span>
          <div className="flex-1">{actionSuccess}</div>
        </div>
      )}

      {/* Dossier Header Overview Card */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 shadow-xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 uppercase tracking-wider">
                {application.applicant_type} Facility Dossier
              </span>
              {application.resubmission_version > 1 && (
                <span className="rounded-full bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 text-[10px] font-bold text-amber-300">
                  Version {application.resubmission_version}
                </span>
              )}
            </div>
            <h1 className="mt-2 text-xl sm:text-2xl font-extrabold text-white">
              {application.applicant_name}
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Territorial Jurisdiction: {application.district ? `${application.district}, ` : ""}
              <strong className="text-slate-200">{application.state}</strong>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                application.status === "APPROVED" || application.status === "PROVISIONED"
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                  : application.status === "REJECTED"
                  ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
                  : application.status === "CORRECTION_REQUIRED"
                  ? "bg-amber-500/10 text-amber-300 border-amber-500/30"
                  : "bg-blue-500/10 text-blue-300 border-blue-500/30"
              }`}
            >
              Status: {application.status.replace(/_/g, " ")}
            </span>

            <span className="rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-300">
              Stage: {application.current_stage.replace(/_/g, " ")}
            </span>
          </div>
        </div>

        {/* Institution & Contact Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {/* Box 1: Nodal Authority */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
              Designated Authority Contact
            </h3>
            <p className="text-slate-400">Officer: <strong className="text-white">{application.nodal_officer_name || "N/A"}</strong></p>
            <p className="text-slate-400">Designation: <strong className="text-white">{application.official_designation || "N/A"}</strong></p>
            <p className="text-slate-400">Official Email: <strong className="text-white">{application.applicant_email}</strong></p>
            <p className="text-slate-400">Official Phone: <strong className="text-white">{application.applicant_phone}</strong></p>
          </div>

          {/* Box 2: Facility Address & Location */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
              Secretariat / Facility Address
            </h3>
            <p className="text-slate-400">City / Town: <strong className="text-white">{application.city || "N/A"}</strong></p>
            <p className="text-slate-400">Street Address: <strong className="text-white">{application.address || "N/A"}</strong></p>
            <p className="text-slate-400">PIN Code: <strong className="text-white">{application.pincode || "N/A"}</strong></p>
            <p className="text-slate-400">Registered: <strong className="text-slate-300 font-mono">{formatDateTime(application.created_at)}</strong></p>
          </div>

          {/* Box 3: Operational Capacities (if Hospital) */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
              Operational Profile & Capacities
            </h3>
            {application.profile_data ? (
              <>
                <p className="text-slate-400">
                  Total Beds: <strong className="text-white">{String(application.profile_data.total_beds || "N/A")}</strong>
                </p>
                <p className="text-slate-400">
                  ICU Capacity: <strong className="text-white">{String(application.profile_data.icu_beds || "N/A")}</strong>
                </p>
                <p className="text-slate-400">
                  Emergency Beds: <strong className="text-white">{String(application.profile_data.emergency_beds || "N/A")}</strong>
                </p>
                <p className="text-slate-400">
                  24x7 Casualty: <strong className="text-emerald-400">{application.profile_data.emergency_24x7 ? "Yes" : "No"}</strong>
                </p>
              </>
            ) : (
              <p className="text-slate-500 italic">Administrative Government Office</p>
            )}
          </div>
        </div>

        {/* Existing Rejection / Correction Notes */}
        {application.correction_notes && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-4 text-xs space-y-1">
            <span className="font-bold text-amber-300">Active Reviewer Correction Notice:</span>
            <p className="text-amber-200/90 font-mono">{application.correction_notes}</p>
          </div>
        )}

        {application.rejection_reason && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/20 p-4 text-xs space-y-1">
            <span className="font-bold text-rose-300">Final Rejection Reason:</span>
            <p className="text-rose-200/90 font-mono">{application.rejection_reason}</p>
          </div>
        )}
      </div>

      {/* Document Verification Checklist Section */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 shadow-xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-base font-bold text-white">Regulatory Document Verification Checklist</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Examine each uploaded document scan and mark as verified or rejected with mandatory comments.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Verification Progress:</span>
            <span
              className={`font-bold font-mono px-2.5 py-0.5 rounded-full border ${
                allDocumentsVerified
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                  : "bg-amber-500/10 text-amber-300 border-amber-500/30"
              }`}
            >
              {application.documents.filter((d) => d.verification_status === "VERIFIED").length} /{" "}
              {application.documents.length} Verified
            </span>
          </div>
        </div>

        {/* Document Cards List */}
        <div className="space-y-3">
          {application.documents.map((doc) => (
            <div
              key={doc.document_id}
              className={`rounded-xl border p-4 transition ${
                doc.verification_status === "VERIFIED"
                  ? "border-emerald-500/40 bg-emerald-950/10"
                  : doc.verification_status === "REJECTED"
                  ? "border-rose-500/40 bg-rose-950/10"
                  : "border-slate-800 bg-slate-950/60"
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <span className="text-2xl mt-0.5">📄</span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white">{doc.document_type}</span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                          doc.verification_status === "VERIFIED"
                            ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                            : doc.verification_status === "REJECTED"
                            ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
                            : "bg-blue-500/10 text-blue-300 border-blue-500/30"
                        }`}
                      >
                        {doc.verification_status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 font-medium truncate mt-0.5">
                      {doc.original_filename}
                    </p>
                    <p className="text-[11px] text-slate-500 font-mono">
                      {formatBytes(doc.file_size_bytes)} • Uploaded {formatDateTime(doc.uploaded_at)}
                    </p>
                  </div>
                </div>

                {/* Document Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => handlePreviewDocument(doc.document_id)}
                    disabled={loading}
                    className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition"
                  >
                    🔍 Inspect File
                  </button>

                  {canActOnCurrentStage && !isTerminal && (
                    <>
                      <button
                        type="button"
                        onClick={() => handleVerifyDocument(doc.document_id)}
                        disabled={loading || doc.verification_status === "VERIFIED"}
                        className="rounded-lg border border-emerald-600/40 bg-emerald-600/20 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-600 hover:text-white disabled:opacity-40 transition"
                      >
                        ✓ Mark Verified
                      </button>

                      <button
                        type="button"
                        onClick={() => handleOpenDocRejectModal(doc.document_id)}
                        disabled={loading}
                        className="rounded-lg border border-rose-600/40 bg-rose-600/20 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-600 hover:text-white disabled:opacity-40 transition"
                      >
                        ✕ Reject
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Reviewer remarks if rejected */}
              {doc.reviewer_remarks && (
                <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-950/20 p-2.5 text-xs text-rose-300">
                  <strong className="font-semibold">Reviewer Rejection Reason:</strong> {doc.reviewer_remarks}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Reviewer Stage Decision Bar */}
      {canActOnCurrentStage && !isTerminal && (
        <div className="rounded-2xl border border-blue-500/30 bg-slate-900/90 p-6 sm:p-7 shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <span className="rounded-full bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 uppercase tracking-wider">
                Jurisdiction Decision Authority
              </span>
              <h2 className="mt-1.5 text-base font-bold text-white">
                Execute Review Decision on Application
              </h2>
              <p className="text-xs text-slate-400">
                You are reviewing as <strong className="text-slate-200">{role.replace(/_/g, " ")}</strong> at stage{" "}
                <strong className="text-blue-300">{application.current_stage.replace(/_/g, " ")}</strong>.
              </p>
            </div>

            {/* Checklist requirement */}
            <div className="text-xs">
              {!allDocumentsVerified ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 font-semibold text-amber-300">
                  ⚠️ All documents must be marked Verified before forwarding/approval
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 font-semibold text-emerald-300">
                  ✓ Document checklist complete
                </span>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => {
                setCorrectionNotes("");
                setActiveModal("CORRECTION");
              }}
              className="rounded-xl border border-amber-600/40 bg-amber-950/30 px-4 py-2.5 text-xs font-bold text-amber-300 hover:bg-amber-900/40 transition shadow"
            >
              ⚠️ Request Applicant Correction
            </button>

            <button
              type="button"
              onClick={() => {
                setDecisionRemarks("");
                setActiveModal("REJECT");
              }}
              className="rounded-xl border border-rose-600/40 bg-rose-950/30 px-4 py-2.5 text-xs font-bold text-rose-300 hover:bg-rose-900/40 transition shadow"
            >
              ✕ Reject Application
            </button>

            {isCentralReviewer ? (
              <button
                type="button"
                disabled={!allDocumentsVerified}
                onClick={() => {
                  setDecisionRemarks("");
                  setActiveModal("APPROVE");
                }}
                className="rounded-xl bg-emerald-600 px-6 py-2.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-40 transition shadow-lg shadow-emerald-900/20"
              >
                ✓ Final Approve & Provision Account
              </button>
            ) : (
              <button
                type="button"
                disabled={!allDocumentsVerified}
                onClick={() => {
                  setDecisionRemarks("");
                  setActiveModal("FORWARD");
                }}
                className="rounded-xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-40 transition shadow-lg shadow-blue-900/20"
              >
                Forward to Next Review Authority →
              </button>
            )}
          </div>
        </div>
      )}

      {/* Application Timeline & Milestone Progression */}
      <ApplicationTimeline
        status={application.status}
        currentStage={application.current_stage}
        resubmissionVersion={application.resubmission_version}
      />

      {/* Reviewer Audit History Table */}
      {application.history && application.history.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 shadow-xl space-y-4">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
            Reviewer Decision Audit Trail ({application.history.length})
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] font-bold text-slate-400 uppercase">
                  <th className="py-2.5 px-3">Action</th>
                  <th className="py-2.5 px-3">Review Tier</th>
                  <th className="py-2.5 px-3">Reviewer ID</th>
                  <th className="py-2.5 px-3">Transition</th>
                  <th className="py-2.5 px-3">Remarks</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {application.history.map((h, i) => (
                  <tr key={i} className="hover:bg-slate-800/20">
                    <td className="py-2.5 px-3 font-semibold text-blue-400">{h.action}</td>
                    <td className="py-2.5 px-3 text-slate-300">{h.review_tier}</td>
                    <td className="py-2.5 px-3 font-mono text-slate-400">{h.reviewer_user_id}</td>
                    <td className="py-2.5 px-3 text-slate-400">
                      {h.previous_status} → <strong className="text-slate-200">{h.new_status}</strong>
                    </td>
                    <td className="py-2.5 px-3 text-slate-300 max-w-xs truncate">{h.remarks || "—"}</td>
                    <td className="py-2.5 px-3 font-mono text-slate-500 text-[11px]">
                      {h.created_at ? formatDateTime(h.created_at) : "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* ACTION CONFIRMATION MODALS                                  */}
      {/* ============================================================ */}

      {/* FORWARD CONFIRMATION MODAL */}
      {activeModal === "FORWARD" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-white">Forward Application to Next Review Level</h3>
            <p className="text-xs text-slate-400">
              Confirm forwarding application <strong className="text-white">{application.application_number}</strong> to the higher authority tier.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300">Reviewer Endorsement Remarks (Optional)</label>
              <textarea
                rows={3}
                value={decisionRemarks}
                onChange={(e) => setDecisionRemarks(e.target.value)}
                placeholder="e.g. All clinical licenses and fire safety NOCs verified on site."
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => handleExecuteDecision("FORWARD")}
                className="rounded-xl bg-blue-600 px-5 py-2 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {loading ? "Processing..." : "Confirm Forward →"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* APPROVE & PROVISION CONFIRMATION MODAL */}
      {activeModal === "APPROVE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-emerald-500/40 bg-slate-900 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-emerald-400 font-bold text-base">
              <span>✓</span>
              <span>Final Central Approval & Account Provisioning</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              This action will approve <strong className="text-white">{application.applicant_name}</strong> and immediately provision their operational healthcare account.
              An activation invitation with an outbox event will be created in the database transaction.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300">Approval Endorsement Remarks (Optional)</label>
              <textarea
                rows={3}
                value={decisionRemarks}
                onChange={(e) => setDecisionRemarks(e.target.value)}
                placeholder="e.g. Cleared under National Referral Registry guidelines."
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder-slate-600 outline-none focus:border-emerald-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => handleExecuteDecision("APPROVE")}
                className="rounded-xl bg-emerald-600 px-5 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
              >
                {loading ? "Provisioning..." : "Final Approve & Provision ✓"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REJECT CONFIRMATION MODAL */}
      {activeModal === "REJECT" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-rose-500/40 bg-slate-900 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-rose-400 font-bold text-base">
              <span>✕</span>
              <span>Reject Application</span>
            </div>
            <p className="text-xs text-slate-400">
              Rejecting will permanently terminate the application review lifecycle. A formal reason is mandatory.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300">Mandatory Rejection Reason *</label>
              <textarea
                rows={3}
                value={decisionRemarks}
                onChange={(e) => setDecisionRemarks(e.target.value)}
                placeholder="Provide a detailed, verifiable reason for rejection..."
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder-slate-600 outline-none focus:border-rose-500"
                required
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={loading || !decisionRemarks.trim()}
                onClick={() => handleExecuteDecision("REJECT")}
                className="rounded-xl bg-rose-600 px-5 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50"
              >
                {loading ? "Rejecting..." : "Confirm Rejection ✕"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REQUEST CORRECTION MODAL */}
      {activeModal === "CORRECTION" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <form
            onSubmit={handleExecuteCorrection}
            className="w-full max-w-md rounded-2xl border border-amber-500/40 bg-slate-900 p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center gap-2 text-amber-400 font-bold text-base">
              <span>⚠️</span>
              <span>Request Applicant Corrections</span>
            </div>
            <p className="text-xs text-slate-400">
              The application will be set to <strong className="text-white">CORRECTION_REQUIRED</strong>. The applicant can log in to update documents and submit a resubmission notes summary.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300">Correction Instructions for Applicant *</label>
              <textarea
                rows={4}
                value={correctionNotes}
                onChange={(e) => setCorrectionNotes(e.target.value)}
                placeholder="e.g. Please re-upload Fire Safety NOC with clear endorsement seal and update emergency bed count."
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder-slate-600 outline-none focus:border-amber-500"
                required
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || correctionNotes.trim().length < 5}
                className="rounded-xl bg-amber-600 px-5 py-2 text-xs font-bold text-white hover:bg-amber-500 disabled:opacity-50"
              >
                {loading ? "Sending..." : "Submit Correction Request →"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* REJECT SPECIFIC DOCUMENT MODAL */}
      {activeModal === "DOC_REJECT" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <form
            onSubmit={handleConfirmDocReject}
            className="w-full max-w-md rounded-2xl border border-rose-500/40 bg-slate-900 p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center gap-2 text-rose-400 font-bold text-base">
              <span>✕</span>
              <span>Reject Document</span>
            </div>
            <p className="text-xs text-slate-400">
              Specify the reason why this document does not meet compliance standards.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300">Reviewer Rejection Reason *</label>
              <textarea
                rows={3}
                value={docRejectRemarks}
                onChange={(e) => setDocRejectRemarks(e.target.value)}
                placeholder="e.g. Certificate is illegible or expired on 2025-12-31."
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder-slate-600 outline-none focus:border-rose-500"
                required
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !docRejectRemarks.trim()}
                className="rounded-xl bg-rose-600 px-5 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50"
              >
                {loading ? "Submitting..." : "Reject Document"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* DOCUMENT PREVIEW MODAL */}
      {activeModal === "DOC_PREVIEW" && previewBlobUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-4xl h-[85vh] rounded-2xl border border-slate-800 bg-slate-900 p-5 flex flex-col shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 truncate">
                <span className="text-xl">📄</span>
                <span className="text-sm font-bold text-white truncate">{previewFilename}</span>
                <span className="text-[11px] text-slate-400">({previewContentType})</span>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={previewBlobUrl}
                  download={previewFilename}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  Download File
                </a>
                <button
                  onClick={() => {
                    setActiveModal(null);
                    setPreviewBlobUrl(null);
                  }}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="flex-1 mt-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-950 flex items-center justify-center">
              {previewContentType.includes("pdf") ? (
                <iframe src={previewBlobUrl} className="w-full h-full rounded-xl" title="Document Preview" />
              ) : previewContentType.includes("image") ? (
                <img
                  src={previewBlobUrl}
                  alt="Document Preview"
                  className="max-h-full max-w-full object-contain p-2"
                />
              ) : (
                <div className="text-center p-8 space-y-3">
                  <span className="text-4xl">📎</span>
                  <p className="text-xs text-slate-300">File format preview not supported directly in browser.</p>
                  <a
                    href={previewBlobUrl}
                    download={previewFilename}
                    className="inline-block rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-500"
                  >
                    Download {previewFilename}
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
