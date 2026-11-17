"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { ApplicationTimeline } from "@/components/registration/ApplicationTimeline";
import { apiPublicTrackApplication } from "@/lib/api";
import { PublicTrackingData } from "@/lib/types";

function TrackForm() {
  const searchParams = useSearchParams();
  const [appNumber, setAppNumber] = useState("");
  const [trackingToken, setTrackingToken] = useState("");
  const [trackingData, setTrackingData] = useState<PublicTrackingData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchTracking = async (app = appNumber, token = trackingToken) => {
    if (!app.trim() || !token.trim()) {
      setError("Please provide both Application Number and Secret Tracking Token.");
      return;
    }

    setLoading(true);
    setError("");
    setTrackingData(null);

    try {
      const data = await apiPublicTrackApplication(app.trim(), token.trim());
      setTrackingData(data);
    } catch (err: any) {
      setError(err.message || "Invalid application number or tracking token.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const qApp = searchParams.get("app");
    const qToken = searchParams.get("token");
    if (qApp && qToken) {
      setAppNumber(qApp);
      setTrackingToken(qToken);
      fetchTracking(qApp, qToken);
    }
  }, [searchParams]);

  const handleTrack = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTracking();
  };

  return (
    <div className="space-y-8">
      {/* Search Input Box */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-8 shadow-xl">
        <form onSubmit={handleTrack} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Official Application Number
              </label>
              <input
                type="text"
                value={appNumber}
                onChange={(e) => setAppNumber(e.target.value)}
                placeholder="e.g. APP-HOSP-202611-ABC123"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500 font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Secret Tracking Token
              </label>
              <input
                type="text"
                value={trackingToken}
                onChange={(e) => setTrackingToken(e.target.value)}
                placeholder="16+ character secret token"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500 font-mono"
                required
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <span className="text-[11px] text-slate-500">
              🔒 Confidential tracking token was provided upon registration submission.
            </span>
            <button
              type="submit"
              disabled={loading}
              className="rounded-xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow"
            >
              {loading ? "Verifying..." : "Track Status →"}
            </button>
          </div>
        </form>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
          <span className="text-base">⚠</span>
          <div className="flex-1">{error}</div>
        </div>
      )}

      {/* Tracking Result View */}
      {trackingData && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 sm:p-7 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
                  {trackingData.applicant_type} Facility
                </span>
                <h3 className="mt-1.5 text-lg font-bold text-white">{trackingData.applicant_name}</h3>
                <p className="text-xs text-slate-400">
                  Jurisdiction: {trackingData.district ? `${trackingData.district}, ` : ""}{trackingData.state}
                </p>
              </div>

              <div className="text-right">
                <span className="text-[11px] text-slate-500 font-mono block">Reference</span>
                <span className="text-sm font-mono font-bold text-blue-400">
                  {trackingData.application_number}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Registered On</span>
                <p className="mt-1 text-slate-200 font-medium">
                  {trackingData.created_at ? new Date(trackingData.created_at).toLocaleDateString() : "N/A"}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Submitted On</span>
                <p className="mt-1 text-slate-200 font-medium">
                  {trackingData.submitted_at ? new Date(trackingData.submitted_at).toLocaleDateString() : "Draft"}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Review Level</span>
                <p className="mt-1 text-blue-400 font-medium">
                  {trackingData.current_stage.replace(/_/g, " ")}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Version</span>
                <p className="mt-1 text-slate-200 font-medium">
                  v{trackingData.resubmission_version}
                </p>
              </div>
            </div>
          </div>

          {/* Timeline Component */}
          <ApplicationTimeline
            status={trackingData.status}
            currentStage={trackingData.current_stage}
            milestones={trackingData.milestones}
            resubmissionVersion={trackingData.resubmission_version}
          />

          {/* Callout to Authenticated Applicant View */}
          <div className="rounded-2xl border border-blue-500/20 bg-blue-950/20 p-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
            <div>
              <p className="font-semibold text-white">Need to update documents or address reviewer feedback?</p>
              <p className="text-slate-400 mt-0.5">
                Sign in with an email verification code to view private documents and submit corrections.
              </p>
            </div>
            <Link
              href="/application/status"
              className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 font-bold text-white hover:bg-blue-500 transition"
            >
              Sign In to Applicant Portal →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ApplicationTrackPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 sm:px-6 py-10 sm:py-14 space-y-8">
        <div className="text-center max-w-2xl mx-auto space-y-2">
          <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
            Public Milestone Tracking
          </span>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white">
            Track Application Verification Status
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            Enter your official registration reference number and confidential tracking token to check real-time approval milestones.
          </p>
        </div>

        <Suspense fallback={<div className="text-center text-slate-500 text-xs py-10">Loading tracking portal...</div>}>
          <TrackForm />
        </Suspense>
      </main>
    </div>
  );
}
