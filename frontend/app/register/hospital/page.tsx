"use client";

import React, { useState } from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { OTPModal } from "@/components/registration/OTPModal";
import { DocumentUploader } from "@/components/registration/DocumentUploader";
import { CANONICAL_STATES, getDistrictsForState } from "@/lib/jurisdictions";
import {
  apiCreateHospitalApplication,
  apiGetMyApplication,
  apiSubmitApplication,
} from "@/lib/api";
import { ApplicantApplication, DocumentType } from "@/lib/types";

const HOSPITAL_DOC_SLOTS = [
  {
    type: "CLINICAL_LICENSE" as DocumentType,
    label: "Clinical Establishment Registration",
    description: "Valid certificate under Clinical Establishments (Registration and Regulation) Act.",
    required: true,
  },
  {
    type: "FIRE_SAFETY_NOC" as DocumentType,
    label: "Fire Safety NOC Clearance",
    description: "Fire department safety compliance and clearance certificate.",
    required: true,
  },
  {
    type: "POLLUTION_CONTROL_NOC" as DocumentType,
    label: "Bio-Medical Waste & Pollution Control NOC",
    description: "State Pollution Control Board authorization for bio-medical waste management.",
    required: false,
  },
  {
    type: "MEDICAL_COUNCIL_AFFILIATION" as DocumentType,
    label: "Medical Council Affiliation / Accreditation",
    description: "NMC / NABH / NABL certificate or university teaching hospital affiliation.",
    required: false,
  },
];

export default function RegisterHospitalPage() {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Form States - Step 1: Facility Profile & Capacity
  const [facilityName, setFacilityName] = useState("");
  const [state, setState] = useState("");
  const [district, setDistrict] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [pincode, setPincode] = useState("");
  const [totalBeds, setTotalBeds] = useState<number>(100);
  const [icuBeds, setIcuBeds] = useState<number>(20);
  const [emergencyBeds, setEmergencyBeds] = useState<number>(15);
  const [ventilatorCount, setVentilatorCount] = useState<number>(10);
  const [emergency24x7, setEmergency24x7] = useState<boolean>(true);
  const [latitude, setLatitude] = useState<number>(31.634);
  const [longitude, setLongitude] = useState<number>(74.8723);

  // Form States - Step 2: Nodal Officer & Contact
  const [nodalOfficerName, setNodalOfficerName] = useState("");
  const [officialDesignation, setOfficialDesignation] = useState("Medical Superintendent");
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

  // Step 1 Validation -> Proceed to Step 2
  const handleProceedToStep2 = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!facilityName.trim()) {
      setError("Please enter the official hospital or facility name.");
      return;
    }
    if (!state || !district) {
      setError("Please select both State and District jurisdictions.");
      return;
    }
    if (totalBeds < 1 || icuBeds < 0) {
      setError("Please enter valid bed capacities.");
      return;
    }
    if (icuBeds > totalBeds) {
      setError("ICU beds cannot exceed total bed capacity.");
      return;
    }

    setStep(2);
  };

  // Step 2: Create Draft Application after OTP verification
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
        applicant_name: facilityName.trim(),
        applicant_email: applicantEmail.trim(),
        applicant_phone: applicantPhone.trim(),
        state,
        district,
        city: city.trim() || undefined,
        address: address.trim() || undefined,
        pincode: pincode.trim() || undefined,
        official_designation: officialDesignation.trim() || undefined,
        nodal_officer_name: nodalOfficerName.trim() || undefined,
        profile_data: {
          total_beds: Number(totalBeds),
          icu_beds: Number(icuBeds),
          emergency_beds: Number(emergencyBeds),
          ventilators: Number(ventilatorCount),
          emergency_24x7: Boolean(emergency24x7),
          latitude: Number(latitude),
          longitude: Number(longitude),
        },
      };

      const res = await apiCreateHospitalApplication(payload);
      setApplicantToken(res.applicant_token);
      setTrackingToken(res.tracking_token);

      // Fetch the full applicant application view
      const appData = await apiGetMyApplication(res.applicant_token);
      setApplication(appData);

      setStep(3); // Proceed to Document Uploads
    } catch (err: any) {
      setError(err.message || "Failed to create hospital application draft.");
    } finally {
      setLoading(false);
    }
  };

  // Reload documents when modified in Step 3
  const refreshApplicationDocuments = async () => {
    if (!applicantToken) return;
    try {
      const refreshed = await apiGetMyApplication(applicantToken);
      setApplication(refreshed);
    } catch {
      // ignore
    }
  };

  // Step 3 Validation -> Proceed to Step 4 Preview
  const handleProceedToStep4 = () => {
    setError("");
    const docs = application?.documents || [];
    const hasLicense = docs.some((d) => d.document_type === "CLINICAL_LICENSE");
    const hasFire = docs.some((d) => d.document_type === "FIRE_SAFETY_NOC");

    if (!hasLicense || !hasFire) {
      setError("Mandatory documents missing! Please upload both Clinical Establishment Registration and Fire Safety NOC.");
      return;
    }

    setStep(4);
  };

  // Step 4: Final Submit Application
  const handleFinalSubmit = async () => {
    if (!applicantToken || !application) return;
    setLoading(true);
    setError("");

    try {
      const res = await apiSubmitApplication("Final hospital submission", applicantToken);
      setSubmissionSuccess({
        applicationNumber: res.application_number,
        trackingToken: res.tracking_token || trackingToken || "",
      });
    } catch (err: any) {
      setError(err.message || "Final submission failed. Please ensure all requirements are met.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 sm:px-6 py-8 sm:py-10 space-y-8">
        {/* Breadcrumb & Title */}
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Link href="/register" className="hover:text-blue-400">Registration Hub</Link>
            <span>/</span>
            <span className="text-slate-200">Hospital Facility</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-white">
                Hospital Onboarding & Accreditation
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Onboard inpatient beds, critical care logistics, and emergency intake into the SIH network.
              </p>
            </div>
            {application && (
              <span className="rounded-full bg-blue-500/10 border border-blue-500/30 px-3 py-1 text-xs font-mono font-bold text-blue-300">
                {application.application_number}
              </span>
            )}
          </div>
        </div>

        {/* Wizard Step Indicator */}
        {!submissionSuccess && (
          <div className="grid grid-cols-4 gap-2 border-b border-slate-800 pb-5">
            {[
              { num: 1, title: "1. Facility Profile" },
              { num: 2, title: "2. Nodal Officer & OTP" },
              { num: 3, title: "3. Documents" },
              { num: 4, title: "4. Review & Submit" },
            ].map((s) => (
              <div
                key={s.num}
                className={`text-center pb-2 border-b-2 font-medium text-xs transition ${
                  step === s.num
                    ? "border-blue-500 text-blue-400 font-bold"
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

        {/* Global Error Notice */}
        {error && (
          <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
            <span className="text-base">⚠</span>
            <div className="flex-1">{error}</div>
          </div>
        )}

        {/* SUCCESS CONFIRMATION VIEW */}
        {submissionSuccess ? (
          <div className="rounded-3xl border border-emerald-500/40 bg-slate-900/90 p-8 sm:p-12 text-center space-y-6 shadow-2xl">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-600/20 border border-emerald-500/40 text-3xl text-emerald-400 shadow-inner">
              ✓
            </div>
            <div>
              <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                Application Successfully Submitted
              </span>
              <h2 className="mt-3 text-2xl font-bold text-white">
                Application Submitted for District Verification
              </h2>
              <p className="mt-2 text-xs text-slate-300 max-w-lg mx-auto">
                Your hospital onboarding request has been entered into the government review hierarchy.
                Save your Reference Number and Secret Tracking Token below to monitor real-time approval milestones.
              </p>
            </div>

            {/* Reference Credentials Box */}
            <div className="max-w-md mx-auto rounded-2xl border border-slate-700 bg-slate-950 p-5 text-left space-y-3 font-mono">
              <div>
                <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">
                  Official Application Number
                </span>
                <p className="text-base font-bold text-blue-400 select-all">
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
                className="rounded-xl bg-blue-600 px-6 py-3 text-xs font-bold text-white hover:bg-blue-500 transition shadow"
              >
                Track Live Application →
              </Link>
              <Link
                href="/application/status"
                className="rounded-xl border border-slate-700 bg-slate-800 px-6 py-3 text-xs font-bold text-slate-200 hover:bg-slate-700 hover:text-white transition"
              >
                View Full Applicant Record
              </Link>
            </div>
          </div>
        ) : (
          <>
            {/* STEP 1: FACILITY PROFILE & CAPACITY */}
            {step === 1 && (
              <form onSubmit={handleProceedToStep2} className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-5">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                    Hospital Facility Details
                  </h3>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300">
                      Official Hospital / Facility Name *
                    </label>
                    <input
                      type="text"
                      value={facilityName}
                      onChange={(e) => setFacilityName(e.target.value)}
                      placeholder="e.g. Guru Nanak Dev Hospital & Medical Research Centre"
                      className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
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
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
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
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500 disabled:opacity-50"
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
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">City / Town</label>
                      <input
                        type="text"
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        placeholder="e.g. Amritsar"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-semibold text-slate-300">Street Address</label>
                      <input
                        type="text"
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                        placeholder="e.g. Majitha Road, Medical Enclave"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                      />
                    </div>
                  </div>

                  <div className="w-full sm:w-1/3">
                    <label className="block text-xs font-semibold text-slate-300">PIN Code</label>
                    <input
                      type="text"
                      maxLength={6}
                      value={pincode}
                      onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
                      placeholder="e.g. 143001"
                      className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                {/* Capacity & Logistics */}
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-5">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                    Clinical Bed & Critical Care Capacity
                  </h3>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">Total Beds *</label>
                      <input
                        type="number"
                        min={1}
                        value={totalBeds}
                        onChange={(e) => setTotalBeds(Number(e.target.value))}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">ICU Beds *</label>
                      <input
                        type="number"
                        min={0}
                        value={icuBeds}
                        onChange={(e) => setIcuBeds(Number(e.target.value))}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">Emergency Beds</label>
                      <input
                        type="number"
                        min={0}
                        value={emergencyBeds}
                        onChange={(e) => setEmergencyBeds(Number(e.target.value))}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">Ventilators</label>
                      <input
                        type="number"
                        min={0}
                        value={ventilatorCount}
                        onChange={(e) => setVentilatorCount(Number(e.target.value))}
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        id="emergency24x7"
                        checked={emergency24x7}
                        onChange={(e) => setEmergency24x7(e.target.checked)}
                        className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-blue-600 focus:ring-0"
                      />
                      <label htmlFor="emergency24x7" className="text-xs font-medium text-slate-200">
                        24x7 Emergency Casualty Unit
                      </label>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">Latitude</label>
                      <input
                        type="number"
                        step="0.0001"
                        value={latitude}
                        onChange={(e) => setLatitude(Number(e.target.value))}
                        className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">Longitude</label>
                      <input
                        type="number"
                        step="0.0001"
                        value={longitude}
                        onChange={(e) => setLongitude(Number(e.target.value))}
                        className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    className="rounded-xl bg-blue-600 px-6 py-3 text-xs font-bold text-white hover:bg-blue-500 transition shadow"
                  >
                    Proceed to Contact & Verification →
                  </button>
                </div>
              </form>
            )}

            {/* STEP 2: NODAL OFFICER & EMAIL OTP VERIFICATION */}
            {step === 2 && (
              <form onSubmit={handleCreateDraft} className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-5">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                    Designated Nodal Officer & Contact
                  </h3>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Nodal Officer / Medical Superintendent Name *
                      </label>
                      <input
                        type="text"
                        value={nodalOfficerName}
                        onChange={(e) => setNodalOfficerName(e.target.value)}
                        placeholder="e.g. Dr. Harpreet Singh"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
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
                        placeholder="e.g. Chief Medical Superintendent"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
                        required
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Official Contact Email *
                      </label>
                      <div className="mt-1.5 flex gap-2">
                        <input
                          type="email"
                          value={applicantEmail}
                          onChange={(e) => {
                            setApplicantEmail(e.target.value);
                            setEmailVerified(false);
                          }}
                          placeholder="e.g. nodal.hospital@punjab.gov.in"
                          className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
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
                              : "bg-blue-600 text-white hover:bg-blue-500"
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
                        placeholder="e.g. +91 98765 43210"
                        className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white outline-none focus:border-blue-500"
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
                    ← Back to Facility
                  </button>

                  <button
                    type="submit"
                    disabled={loading || !emailVerified}
                    className="rounded-xl bg-blue-600 px-6 py-3 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow"
                  >
                    {loading ? "Creating Draft..." : "Save Draft & Proceed to Documents →"}
                  </button>
                </div>
              </form>
            )}

            {/* STEP 3: MANDATORY DOCUMENT UPLOADS */}
            {step === 3 && (
              <div className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-7 space-y-4">
                  <div>
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-400">
                      Upload Regulatory & Safety Documents
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">
                      Upload clear scans or digitally signed PDF, JPEG, or PNG certificates (up to 25 MB).
                      Documents undergo antivirus inspection and cryptographic SHA-256 verification.
                    </p>
                  </div>

                  <DocumentUploader
                    slots={HOSPITAL_DOC_SLOTS}
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
                    className="rounded-xl bg-blue-600 px-6 py-3 text-xs font-bold text-white hover:bg-blue-500 transition shadow"
                  >
                    Review Application Summary →
                  </button>
                </div>
              </div>
            )}

            {/* STEP 4: PREVIEW & FINAL SUBMISSION */}
            {step === 4 && (
              <div className="space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 space-y-6">
                  <div className="border-b border-slate-800 pb-4">
                    <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
                      Application Summary Review
                    </span>
                    <h3 className="mt-2 text-lg font-bold text-white">{facilityName}</h3>
                    <p className="text-xs text-slate-400">
                      Jurisdiction: {district}, {state}
                    </p>
                  </div>

                  {/* Summary Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-2">
                      <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                        Operational Capacities
                      </h4>
                      <p className="text-slate-400">Total Beds: <strong className="text-white">{totalBeds}</strong></p>
                      <p className="text-slate-400">ICU Beds: <strong className="text-white">{icuBeds}</strong></p>
                      <p className="text-slate-400">Emergency Beds: <strong className="text-white">{emergencyBeds}</strong></p>
                      <p className="text-slate-400">Ventilators: <strong className="text-white">{ventilatorCount}</strong></p>
                      <p className="text-slate-400">24x7 Emergency: <strong className="text-white">{emergency24x7 ? "Yes" : "No"}</strong></p>
                    </div>

                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-2">
                      <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                        Nodal Authority Contact
                      </h4>
                      <p className="text-slate-400">Officer: <strong className="text-white">{nodalOfficerName}</strong></p>
                      <p className="text-slate-400">Designation: <strong className="text-white">{officialDesignation}</strong></p>
                      <p className="text-slate-400">Email: <strong className="text-white">{applicantEmail}</strong></p>
                      <p className="text-slate-400">Phone: <strong className="text-white">{applicantPhone}</strong></p>
                    </div>
                  </div>

                  {/* Documents Verified */}
                  <div>
                    <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[11px] mb-2">
                      Uploaded Documents ({application?.documents.length || 0})
                    </h4>
                    <div className="space-y-2">
                      {application?.documents.map((d) => (
                        <div
                          key={d.document_id}
                          className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs"
                        >
                          <span className="font-medium text-slate-200">
                            {d.document_type}: {d.original_filename}
                          </span>
                          <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-400 font-semibold">
                            Attached
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Legal Declaration */}
                  <div className="rounded-xl border border-blue-500/20 bg-blue-950/20 p-4 text-xs text-blue-200 space-y-2">
                    <p className="font-semibold text-white">Applicant Formal Declaration:</p>
                    <p className="text-[11px] text-blue-300/80 leading-relaxed">
                      I solemnly affirm that the bed capacities, clinical certifications, and contact information provided are genuine, authentic, and authorized under government health department guidelines.
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

        {/* OTP Verification Modal */}
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
