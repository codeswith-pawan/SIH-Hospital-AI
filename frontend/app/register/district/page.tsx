"use client";

import React, { useState } from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { OTPModal } from "@/components/registration/OTPModal";
import { DocumentUploader } from "@/components/registration/DocumentUploader";
import { CANONICAL_STATES, getDistrictsForState } from "@/lib/jurisdictions";
import {
  apiCreateDistrictApplication,
  apiGetMyApplication,
  apiSubmitApplication,
} from "@/lib/api";
import { ApplicantApplication, DocumentType } from "@/lib/types";

const DISTRICT_DOC_SLOTS = [
  {
    type: "GOVERNMENT_ORDER" as DocumentType,
    label: "Official Government Order / Gazetted Notification",
    description: "Official gazetted order appointing the CMO / authorizing district jurisdiction onboarding.",
    required: true,
  },
  {
    type: "IDENTITY_PROOF" as DocumentType,
    label: "Government Identity Proof",
    description: "Authorized officer government service identity card or civil credentials.",
    required: false,
  },
];

export default function RegisterDistrictPage() {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Form States - Step 1: District Jurisdiction
  const [districtAuthorityName, setDistrictAuthorityName] = useState("");
  const [state, setState] = useState("");
  const [district, setDistrict] = useState("");
  const [address, setAddress] = useState("");
  const [pincode, setPincode] = useState("");

  // Form States - Step 2: Nodal Officer & Contact
  const [nodalOfficerName, setNodalOfficerName] = useState("");
  const [officialDesignation, setOfficialDesignation] = useState("Chief Medical Officer (CMO)");
  const [applicantEmail, setApplicantEmail] = useState("");
  const [applicantPhone, setApplicantPhone] = useState("");
  const [emailVerified, setEmailVerified] = useState(false);

  // OTP Modal State
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);

  // Created Draft Application & Token
  const [application, setApplication] = useState<ApplicantApplication | null>(null);
  const [applicantToken, setApplicantToken] = useState<string | null>(null);
  const [trackingToken, setTrackingToken] = useState<string | null>(null);

  // Submission & UI States
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [submissionSuccess, setSubmissionSuccess] = useState<{
    applicationNumber: string;
    trackingToken: string;
  } | null>(null);

  const districts = state ? getDistrictsForState(state) : [];

  const handleProceedToStep2 = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!districtAuthorityName.trim()) {
      setError("Please enter the district authority / office title.");
      return;
    }
    if (!state || !district) {
      setError("Please select both State and District jurisdictions.");
      return;
    }

    setStep(2);
  };

  const handleCreateDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!emailVerified) {
      setIsOtpModalOpen(true);
      return;
    }

    if (!nodalOfficerName.trim() || !applicantEmail.trim() || !applicantPhone.trim()) {
      setError("Please fill in all mandatory contact information.");
      return;
    }

    setLoading(true);

    try {
      const payload = {
        applicant_name: districtAuthorityName.trim(),
        applicant_email: applicantEmail.trim(),
        applicant_phone: applicantPhone.trim(),
        state,
        district,
        address: address.trim() || undefined,
        pincode: pincode.trim() || undefined,
        official_designation: officialDesignation.trim() || undefined,
        nodal_officer_name: nodalOfficerName.trim() || undefined,
      };

      const res = await apiCreateDistrictApplication(payload);
      setApplicantToken(res.applicant_token);
      setTrackingToken(res.tracking_token);

      const appData = await apiGetMyApplication(res.applicant_token);
      setApplication(appData);

      setStep(3);
    } catch (err: any) {
      setError(err.message || "Failed to create district authority application draft.");
    } finally {
      setLoading(false);
    }
  };

  const refreshApplicationDocuments = async () => {
    if (!applicantToken) return;
    try {
      const refreshed = await apiGetMyApplication(applicantToken);
      setApplication(refreshed);
    } catch {
      // ignore
    }
  };

  const handleProceedToStep4 = () => {
    setError("");
    const docs = application?.documents || [];
    const hasOrder = docs.some((d) => d.document_type === "GOVERNMENT_ORDER");

    if (!hasOrder) {
      setError("Mandatory document missing! Please upload the Official Government Order / Notification.");
      return;
    }

    setStep(4);
  };

  const handleFinalSubmit = async () => {
    if (!applicantToken || !application) return;
    setLoading(true);
    setError("");

    try {
      const res = await apiSubmitApplication("Final district submission", applicantToken);
      setSubmissionSuccess({
        applicationNumber: res.application_number,
        trackingToken: res.tracking_token || trackingToken || "",
      });
    } catch (err: any) {
      setError(err.message || "Final submission failed. Please verify requirements.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 sm:px-6 py-8 sm:py-10 space-y-8">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Link href="/register" className="hover:text-blue-400">Registration Hub</Link>
            <span>/</span>
            <span className="text-slate-200">District Health Authority</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-white">
                District Health Administration Registration
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Register a District Health Office to supervise local hospital inventories, bed allocations, and referrals.
              </p>
            </div>
            {application && (
              <span className="rounded-full bg-indigo-500/10 border border-indigo-500/30 px-3 py-1 text-xs font-mono font-bold text-indigo-300">
                {application.application_number}
              </span>
            )}
          </div>
        </div>

        {!submissionSuccess && (
          <div className="grid grid-cols-4 gap-2 border-b border-slate-800 pb-5">
            {[
              { num: 1, title: "1. Jurisdiction" },
              { num: 2, title: "2. CMO & OTP" },
              { num: 3, title: "3. Documents" },
              { num: 4, title: "4. Review & Submit" },
            ].map((s) => (
              <div
                key={s.num}
                className={`text-center pb-2 border-b-2 font-medium text-xs transition ${
                  step === s.num
                    ? "border-indigo-500 text-indigo-400 font-bold"
                    : step > s.num
                    ? "border-emerald-500 text-emerald-400"
                    : "border-transparent text-slate-500"
                }`}
              >
                {step > s.num ? `✓ ${s.title}` : s.title}
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
            <span className="text-base">⚠</span>
            <div className="flex-1">{error}</div>
          </div>
        )}

        {submissionSuccess ? (
          <div className="rounded-3xl border border-emerald-500/40 bg-slate-900/90 p-8 sm:p-12 text-center space-y-6 shadow-2xl">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-600/20 border border-emerald-500/40 text-3xl text-emerald-400 shadow-inner">
              ✓
            </div>
            <div>
              <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                District Application Submitted
              </span>
              <h2 className="mt-3 text-2xl font-bold text-white">
                Application Submitted for State Verification
              </h2>
              <p className="mt-2 text-xs text-slate-300 max-w-lg mx-auto">
                Your District Health Authority application has been forwarded to the State Health Directorate for formal verification.
              </p>
            </div>

            <div className="max-w-md mx-auto rounded-2xl border border-slate-700 bg-slate-950 p-5 text-left space-y-3 font-mono">
              <div>
                <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">
                  Official Application Number
                </span>
                <p className="text-base font-bold text-indigo-400 select-all">
                  {submissionSuccess.applicationNumber}
                </p>
              </div>
              <div className="border-t border-slate-800 pt-2">
                <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">
                  Secret Tracking Token
                </span>
                <p className="text-xs text-emerald-400 select-all break-all">
                  {submissionSuccess.trackingToken}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
              <Link
                href={`/application/track?app=${encodeURIComponent(
                  submissionSuccess.applicationNumber
                )}&token=${encodeURIComponent(submissionSuccess.trackingToken)}`}
                className="rounded-xl bg-indigo-600 px-6 py-3 text-xs font-bold text-white hover:bg-indigo-500 transition shadow"
              >
                Track Live Application →
              </Link>
              <Link
                href="/application/status"
                className="rounded-xl border border-slate-700 bg-slate-800 px-6 py-3 text-xs font-bold text-slate-200 hover:bg-slate-700 hover:text-white transition"
              >
                View Full Record
              </Link>
            </div>
          </div>
        ) : (
          <>
            {step === 1 && (
              <form onSubmit={handleProceedToStep2} className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-5">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                    District Authority Jurisdiction
                  </h3>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300">
                      District Office / Authority Title *
                    </label>
                    <input
                      type="text"
                      value={districtAuthorityName}
                      onChange={(e) => setDistrictAuthorityName(e.target.value)}
                      placeholder="e.g. Office of the Chief Medical Officer, Amritsar"
                      className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-indigo-500"
                      required
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        State Jurisdiction *
                      </label>
                      <select
                        value={state}
                        onChange={(e) => {
                          setState(e.target.value);
                          setDistrict("");
                        }}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500"
                        required
                      >
                        <option value="">Select State</option>
                        {CANONICAL_STATES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        District Jurisdiction *
                      </label>
                      <select
                        value={district}
                        onChange={(e) => setDistrict(e.target.value)}
                        disabled={!state}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500 disabled:opacity-50"
                        required
                      >
                        <option value="">
                          {state ? "Select District" : "Select State First"}
                        </option>
                        {districts.map((d) => (
                          <option key={d} value={d}>
                            {d}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-semibold text-slate-300">Office Address</label>
                      <input
                        type="text"
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                        placeholder="e.g. Civil Lines, Health Complex"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">PIN Code</label>
                      <input
                        type="text"
                        maxLength={6}
                        value={pincode}
                        onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
                        placeholder="e.g. 143001"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    className="rounded-xl bg-indigo-600 px-6 py-3 text-xs font-bold text-white hover:bg-indigo-500 transition shadow"
                  >
                    Proceed to Authority Contact →
                  </button>
                </div>
              </form>
            )}

            {step === 2 && (
              <form onSubmit={handleCreateDraft} className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-5">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                    District CMO / Authority Contact
                  </h3>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Designated Officer Name *
                      </label>
                      <input
                        type="text"
                        value={nodalOfficerName}
                        onChange={(e) => setNodalOfficerName(e.target.value)}
                        placeholder="e.g. Dr. Rajesh Sharma"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Official Designation *
                      </label>
                      <input
                        type="text"
                        value={officialDesignation}
                        onChange={(e) => setOfficialDesignation(e.target.value)}
                        placeholder="e.g. Chief Medical Officer"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500"
                        required
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Official Government Email *
                      </label>
                      <div className="mt-1.5 flex gap-2">
                        <input
                          type="email"
                          value={applicantEmail}
                          onChange={(e) => {
                            setApplicantEmail(e.target.value);
                            setEmailVerified(false);
                          }}
                          placeholder="e.g. cmo.amritsar@punjab.gov.in"
                          className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => {
                            if (!applicantEmail.includes("@")) {
                              setError("Please enter a valid email address.");
                              return;
                            }
                            setIsOtpModalOpen(true);
                          }}
                          className={`rounded-xl px-3 py-2 text-xs font-bold transition ${
                            emailVerified
                              ? "bg-emerald-600/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-indigo-600 text-white hover:bg-indigo-500"
                          }`}
                        >
                          {emailVerified ? "✓ Verified" : "Verify Email"}
                        </button>
                      </div>
                      {emailVerified && (
                        <p className="mt-1.5 text-[11px] text-emerald-400">
                          ✓ Two-Factor Email Ownership Confirmed
                        </p>
                      )}
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Official Phone Number *
                      </label>
                      <input
                        type="tel"
                        value={applicantPhone}
                        onChange={(e) => setApplicantPhone(e.target.value)}
                        placeholder="e.g. +91 98140 12345"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-indigo-500"
                        required
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-between items-center">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
                  >
                    ← Back to Jurisdiction
                  </button>

                  <button
                    type="submit"
                    disabled={loading || !emailVerified}
                    className="rounded-xl bg-indigo-600 px-6 py-3 text-xs font-bold text-white hover:bg-indigo-500 disabled:opacity-50 transition shadow"
                  >
                    {loading ? "Creating Draft..." : "Save Draft & Proceed to Documents →"}
                  </button>
                </div>
              </form>
            )}

            {step === 3 && (
              <div className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-4">
                  <div>
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                      Upload Government Authorization Order
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">
                      Upload the official Government Order or Gazetted Notification issued by the State Department of Health and Family Welfare.
                    </p>
                  </div>

                  <DocumentUploader
                    slots={DISTRICT_DOC_SLOTS}
                    existingDocuments={application?.documents || []}
                    applicantToken={applicantToken}
                    canEdit={true}
                    onDocumentsChanged={refreshApplicationDocuments}
                  />
                </div>

                <div className="flex justify-between items-center">
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
                  >
                    ← Back to Contact
                  </button>

                  <button
                    type="button"
                    onClick={handleProceedToStep4}
                    className="rounded-xl bg-indigo-600 px-6 py-3 text-xs font-bold text-white hover:bg-indigo-500 transition shadow"
                  >
                    Review Application Summary →
                  </button>
                </div>
              </div>
            )}

            {step === 4 && (
              <div className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 space-y-6">
                  <div className="border-b border-slate-800 pb-4">
                    <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-[10px] font-bold text-indigo-400 border border-indigo-500/20 uppercase tracking-wider">
                      District Application Review
                    </span>
                    <h3 className="mt-2 text-lg font-bold text-white">{districtAuthorityName}</h3>
                    <p className="text-xs text-slate-400">
                      Jurisdiction: {district}, {state}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-2">
                      <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                        Officer Information
                      </h4>
                      <p className="text-slate-400">Officer: <strong className="text-white">{nodalOfficerName}</strong></p>
                      <p className="text-slate-400">Designation: <strong className="text-white">{officialDesignation}</strong></p>
                      <p className="text-slate-400">Address: <strong className="text-white">{address || "N/A"}</strong></p>
                    </div>

                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-2">
                      <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                        Verified Credentials
                      </h4>
                      <p className="text-slate-400">Email: <strong className="text-white">{applicantEmail}</strong></p>
                      <p className="text-slate-400">Phone: <strong className="text-white">{applicantPhone}</strong></p>
                      <p className="text-slate-400">Documents: <strong className="text-white">{application?.documents.length || 0} Attached</strong></p>
                    </div>
                  </div>

                  <div className="rounded-xl border border-indigo-500/20 bg-indigo-950/20 p-4 text-xs text-indigo-200">
                    <p className="font-semibold text-white">Declaration:</p>
                    <p className="text-[11px] text-indigo-300/80 mt-1 leading-relaxed">
                      I certify that this registration is submitted on behalf of the designated District Health Authority under the purview of the State Department of Health.
                    </p>
                  </div>
                </div>

                <div className="flex justify-between items-center">
                  <button
                    type="button"
                    onClick={() => setStep(3)}
                    className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
                  >
                    ← Back to Documents
                  </button>

                  <button
                    type="button"
                    disabled={loading}
                    onClick={handleFinalSubmit}
                    className="rounded-xl bg-emerald-600 px-8 py-3.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition shadow-lg shadow-emerald-900/30"
                  >
                    {loading ? "Submitting Application..." : "Final Submit Application ✓"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        <OTPModal
          isOpen={isOtpModalOpen}
          onClose={() => setIsOtpModalOpen(false)}
          contactTarget={applicantEmail}
          purpose="REGISTRATION_OTP"
          onVerified={() => {
            setEmailVerified(true);
            setIsOtpModalOpen(false);
          }}
        />
      </main>
    </div>
  );
}
