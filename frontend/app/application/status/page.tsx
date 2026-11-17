"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { ApplicationTimeline } from "@/components/registration/ApplicationTimeline";
import { DocumentUploader } from "@/components/registration/DocumentUploader";
import { OTPModal } from "@/components/registration/OTPModal";
import { NotificationPanel } from "@/components/shared/NotificationPanel";
import {
  apiGetMyApplication,
  apiSubmitApplication,
  apiResubmitApplication,
  apiGetApplicantNotifications,
  apiMarkApplicantNotificationRead,
  apiMarkAllApplicantNotificationsRead,
  getApplicantToken,
  setApplicantToken,
  clearApplicantToken,
} from "@/lib/api";
import { ApplicantApplication, DocumentType, OTPVerifyResponse, NotificationItem } from "@/lib/types";

const ALL_DOC_SLOTS = [
  {
    type: "CLINICAL_LICENSE" as DocumentType,
    label: "Clinical Establishment Registration",
    description: "Valid certificate under Clinical Establishments Act.",
    required: true,
  },
  {
    type: "FIRE_SAFETY_NOC" as DocumentType,
    label: "Fire Safety NOC Clearance",
    description: "Fire department safety compliance and clearance certificate.",
    required: true,
  },
  {
    type: "GOVERNMENT_ORDER" as DocumentType,
    label: "Government Order / Authorization Notification",
    description: "Official gazetted order appointing the CMO / authorizing state or district onboarding.",
    required: true,
  },
  {
    type: "POLLUTION_CONTROL_NOC" as DocumentType,
    label: "Bio-Medical Waste NOC",
    description: "State Pollution Control Board authorization.",
    required: false,
  },
  {
    type: "MEDICAL_COUNCIL_AFFILIATION" as DocumentType,
    label: "Accreditation / Medical Council",
    description: "NMC / NABH / NABL certificate.",
    required: false,
  },
];

export default function ApplicationStatusPage() {
  const [mounted, setMounted] = useState(false);
  const [applicantTokenState, setApplicantTokenState] = useState<string | null>(null);
  const [application, setApplication] = useState<ApplicantApplication | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Applicant OTP Login Form States
  const [loginAppNumber, setLoginAppNumber] = useState("");
  const [loginContact, setLoginContact] = useState("");
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);

  // Correction Resubmission States
  const [resubmissionNotes, setResubmissionNotes] = useState("");
  const [resubmitting, setResubmitting] = useState(false);
  const [submittingDraft, setSubmittingDraft] = useState(false);
  const [actionSuccess, setActionSuccess] = useState("");

  // Applicant Notifications State (Phase 4D-2)
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifLoading, setNotifLoading] = useState(false);

  const loadApplicantNotifications = async () => {
    setNotifLoading(true);
    try {
      const data = await apiGetApplicantNotifications();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // background poll failure
    } finally {
      setNotifLoading(false);
    }
  };

  const fetchApplication = async (token = applicantTokenState) => {
    if (!token) return;
    setLoading(true);
    setError("");

    try {
      const data = await apiGetMyApplication(token);
      setApplication(data);
      loadApplicantNotifications();
    } catch (err: any) {
      setError(err.message || "Failed to load application details. Please re-authenticate.");
      clearApplicantToken();
      setApplicantTokenState(null);
      setApplication(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
    const storedToken = getApplicantToken();
    if (storedToken) {
      setApplicantTokenState(storedToken);
      fetchApplication(storedToken);
    }
  }, []);

  const handleStartOtpLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!loginAppNumber.trim() || !loginContact.trim()) {
      setError("Please provide both your Application Number and registered Email/Phone.");
      return;
    }

    setIsOtpModalOpen(true);
  };

  const handleOtpVerified = (response: OTPVerifyResponse) => {
    if (response.applicant_token) {
      setApplicantToken(response.applicant_token);
      setApplicantTokenState(response.applicant_token);
      fetchApplication(response.applicant_token);
      setIsOtpModalOpen(false);
    } else {
      setError("Verification succeeded but no applicant session token was issued.");
    }
  };

  const handleSignOut = () => {
    clearApplicantToken();
    setApplicantTokenState(null);
    setApplication(null);
    setError("");
    setActionSuccess("");
  };

  const handleSubmitDraft = async () => {
    if (!applicantTokenState) return;
    setSubmittingDraft(true);
    setError("");
    setActionSuccess("");

    try {
      const res = await apiSubmitApplication("Submitted via applicant portal", applicantTokenState);
      setActionSuccess(`Application ${res.application_number} submitted successfully for review.`);
      fetchApplication();
    } catch (err: any) {
      setError(err.message || "Draft submission failed.");
    } finally {
      setSubmittingDraft(false);
    }
  };

  const handleResubmitCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!applicantTokenState) return;
    if (resubmissionNotes.trim().length < 5) {
      setError("Please explain the corrections made (minimum 5 characters).");
      return;
    }

    setResubmitting(true);
    setError("");
    setActionSuccess("");

    try {
      const res = await apiResubmitApplication(resubmissionNotes.trim(), applicantTokenState);
      setActionSuccess(`Application v${res.resubmission_version} resubmitted successfully for review.`);
      setResubmissionNotes("");
      fetchApplication();
    } catch (err: any) {
      setError(err.message || "Resubmission failed.");
    } finally {
      setResubmitting(false);
    }
  };

  if (!mounted) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        <div className="text-xs text-slate-400">Loading applicant session...</div>
      </div>
    );
  }

  // Filter slots relevant to applicant type
  const relevantSlots = ALL_DOC_SLOTS.filter((s) => {
    if (application?.applicant_type === "HOSPITAL") {
      return s.type !== "GOVERNMENT_ORDER";
    }
    if (application?.applicant_type === "DISTRICT" || application?.applicant_type === "STATE") {
      return s.type === "GOVERNMENT_ORDER" || s.type === "IDENTITY_PROOF";
    }
    return true;
  });

  const isCorrectionRequired = application?.status === "CORRECTION_REQUIRED";
  const isDraft = application?.status === "DRAFT";
  const canEditDocuments = isDraft || isCorrectionRequired;

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />

      <main className="flex-1 mx-auto w-full max-w-5xl px-4 sm:px-6 py-8 sm:py-10 space-y-8">
        {/* Top Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Link href="/register" className="hover:text-blue-400">Registration Hub</Link>
              <span>/</span>
              <span className="text-slate-200">Applicant Portal</span>
            </div>
            <h1 className="mt-1 text-2xl font-extrabold text-white">
              Applicant Dashboard & Document Management
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Securely view official verification remarks, replace requested documents, and resubmit applications.
            </p>
          </div>

          {application && (
            <div className="flex items-center gap-3">
              <NotificationPanel
                notifications={notifications}
                unreadCount={unreadCount}
                loading={notifLoading}
                onMarkRead={(nid) => {
                  apiMarkApplicantNotificationRead(nid).then(loadApplicantNotifications);
                }}
                onMarkAllRead={() => {
                  apiMarkAllApplicantNotificationsRead().then(loadApplicantNotifications);
                }}
                onRefresh={loadApplicantNotifications}
              />
              <button
                onClick={handleSignOut}
                className="rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition"
              >
                Sign Out
              </button>
            </div>
          )}
        </div>

        {/* Global Notices */}
        {error && (
          <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
            <span className="text-base">⚠</span>
            <div className="flex-1">{error}</div>
          </div>
        )}

        {actionSuccess && (
          <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-xs text-emerald-300 flex items-start gap-3">
            <span className="text-base">✓</span>
            <div className="flex-1">{actionSuccess}</div>
          </div>
        )}

        {/* VIEW 1: UN-AUTHENTICATED APPLICANT LOGIN */}
        {!application && !loading && (
          <div className="max-w-md mx-auto rounded-3xl border border-slate-800 bg-slate-900/90 p-6 sm:p-8 shadow-2xl space-y-6">
            <div className="text-center space-y-2">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600/20 border border-blue-500/30 text-2xl text-blue-400">
                🔐
              </div>
              <h2 className="text-lg font-bold text-white">Applicant Two-Factor Sign In</h2>
              <p className="text-xs text-slate-400">
                Access your registered application record by entering your application number and registered email/phone.
              </p>
            </div>

            <form onSubmit={handleStartOtpLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Application Number
                </label>
                <input
                  type="text"
                  value={loginAppNumber}
                  onChange={(e) => setLoginAppNumber(e.target.value)}
                  placeholder="e.g. APP-HOSP-202611-ABC123"
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500 font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Registered Official Email / Phone
                </label>
                <input
                  type="text"
                  value={loginContact}
                  onChange={(e) => setLoginContact(e.target.value)}
                  placeholder="e.g. nodal.officer@punjab.gov.in"
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full rounded-xl bg-blue-600 py-3 text-xs font-bold text-white hover:bg-blue-500 transition shadow"
              >
                Send 2FA Security Code →
              </button>
            </form>

            <div className="border-t border-slate-800 pt-4 text-center">
              <Link href="/register" className="text-xs text-blue-400 hover:underline">
                Need to create a new application? Register here
              </Link>
            </div>
          </div>
        )}

        {/* VIEW 2: AUTHENTICATED APPLICANT DASHBOARD */}
        {application && (
          <div className="space-y-8">
            {/* CORRECTION REQUIRED NOTICE BANNER */}
            {isCorrectionRequired && (
              <div className="rounded-2xl border border-amber-500/50 bg-amber-950/20 p-5 sm:p-6 space-y-3">
                <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                  <span className="text-lg">⚠</span>
                  <span>Action Required: Reviewer Requested Corrections (v{application.resubmission_version})</span>
                </div>
                <p className="text-xs text-amber-200/90 leading-relaxed">
                  The reviewing authority reviewed your application and requested adjustments before clearance.
                  Please review the specific correction instructions below, update the affected documents, and submit your corrections.
                </p>
                {application.correction_notes && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-950/40 p-4 text-xs font-mono text-amber-200">
                    <strong className="font-sans font-bold block mb-1 text-amber-300">
                      Official Reviewer Note:
                    </strong>
                    {application.correction_notes}
                  </div>
                )}
              </div>
            )}

            {/* Application Overview Card */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
                <div>
                  <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
                    {application.applicant_type} Facility Record
                  </span>
                  <h2 className="mt-2 text-xl font-bold text-white">{application.applicant_name}</h2>
                  <p className="text-xs text-slate-400">
                    Jurisdiction: {application.district ? `${application.district}, ` : ""}{application.state}
                  </p>
                </div>

                <div className="text-right">
                  <span className="text-[11px] text-slate-500 font-mono block">Application Number</span>
                  <span className="text-sm font-mono font-bold text-blue-400">
                    {application.application_number}
                  </span>
                </div>
              </div>

              {/* Facility & Contact Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                    Designated Nodal Officer
                  </h4>
                  <p className="text-slate-400">Name: <strong className="text-white">{application.nodal_officer_name || "N/A"}</strong></p>
                  <p className="text-slate-400">Designation: <strong className="text-white">{application.official_designation || "N/A"}</strong></p>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                    Contact Information
                  </h4>
                  <p className="text-slate-400">Email: <strong className="text-white">{application.applicant_email}</strong></p>
                  <p className="text-slate-400">Phone: <strong className="text-white">{application.applicant_phone}</strong></p>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
                  <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                    Address & Location
                  </h4>
                  <p className="text-slate-400 truncate">Street: <strong className="text-white">{application.address || "N/A"}</strong></p>
                  <p className="text-slate-400">PIN Code: <strong className="text-white">{application.pincode || "N/A"}</strong></p>
                </div>
              </div>
            </div>

            {/* Stepper Timeline */}
            <ApplicationTimeline
              status={application.status}
              currentStage={application.current_stage}
              milestones={application.milestones}
              resubmissionVersion={application.resubmission_version}
            />

            {/* Document Management Section */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h3 className="text-base font-bold text-white">Regulatory Documentation</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {canEditDocuments
                      ? "You may upload new or replacement certificates below."
                      : "Document repository is locked while under active government review."}
                  </p>
                </div>

                {isDraft && (
                  <button
                    type="button"
                    onClick={handleSubmitDraft}
                    disabled={submittingDraft}
                    className="rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow"
                  >
                    {submittingDraft ? "Submitting..." : "Submit Draft Application →"}
                  </button>
                )}
              </div>

              <DocumentUploader
                slots={relevantSlots}
                existingDocuments={application.documents}
                applicantToken={applicantTokenState}
                canEdit={canEditDocuments}
                onDocumentsChanged={() => fetchApplication()}
              />
            </div>

            {/* CORRECTION RESUBMISSION FORM */}
            {isCorrectionRequired && (
              <div className="rounded-2xl border border-amber-500/40 bg-slate-900/90 p-6 sm:p-8 space-y-5">
                <div>
                  <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-bold text-amber-400 border border-amber-500/20 uppercase tracking-wider">
                    Resubmission Form
                  </span>
                  <h3 className="mt-2 text-base font-bold text-white">
                    Submit Rectified Application for Review
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Ensure all rejected documents have been replaced above. Provide a detailed note of corrections made for the reviewing officer.
                  </p>
                </div>

                <form onSubmit={handleResubmitCorrection} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300">
                      Applicant Correction Notes *
                    </label>
                    <textarea
                      rows={4}
                      value={resubmissionNotes}
                      onChange={(e) => setResubmissionNotes(e.target.value)}
                      placeholder="e.g. Uploaded renewed Fire Safety NOC dated 2026 and updated total bed breakdown as requested."
                      className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 p-3.5 text-xs text-white placeholder-slate-600 outline-none focus:border-amber-500 transition"
                      required
                    />
                  </div>

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={resubmitting || resubmissionNotes.trim().length < 5}
                      className="rounded-xl bg-amber-600 px-6 py-3 text-xs font-bold text-white hover:bg-amber-500 disabled:opacity-50 transition shadow"
                    >
                      {resubmitting ? "Resubmitting..." : "Resubmit Application for Clearance →"}
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        )}

        {/* OTP Modal */}
        <OTPModal
          isOpen={isOtpModalOpen}
          onClose={() => setIsOtpModalOpen(false)}
          contactTarget={loginContact}
          purpose="PORTAL_ACCESS_OTP"
          applicationNumber={loginAppNumber}
          onVerified={handleOtpVerified}
        />
      </main>
    </div>
  );
}
