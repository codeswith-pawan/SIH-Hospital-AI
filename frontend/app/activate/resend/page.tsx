"use client";

import React, { useState } from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { apiResendActivation } from "@/lib/api";

export default function ResendActivationPage() {
  const [appNumber, setAppNumber] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appNumber.trim() || !email.trim()) {
      setError("Please provide both Application Number and registered official email.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      const res = await apiResendActivation({
        application_number: appNumber.trim(),
        applicant_email: email.trim(),
      });
      setSuccessMsg(res.message || "A fresh activation link has been sent to your email.");
    } catch (err: any) {
      setError(err.message || "Unable to resend activation link. Verify application details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />
      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 py-12">
        <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/90 p-6 sm:p-8 shadow-2xl space-y-6">
          <div className="text-center space-y-2">
            <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
              Activation Recovery
            </span>
            <h1 className="text-xl sm:text-2xl font-bold text-white">
              Resend Account Activation Link
            </h1>
            <p className="text-xs text-slate-400">
              Enter your official application reference number and applicant email to receive a fresh single-use activation invitation.
            </p>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
              <span className="text-base">⚠️</span>
              <div className="flex-1">{error}</div>
            </div>
          )}

          {successMsg && (
            <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-xs text-emerald-300 flex items-start gap-3">
              <span className="text-base">✓</span>
              <div className="flex-1">{successMsg}</div>
            </div>
          )}

          <form onSubmit={handleResend} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Application Reference Number *
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
                Designated Applicant Email Address *
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. nodal.officer@punjab.gov.in"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-blue-600 py-3 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow"
            >
              {loading ? "Dispatching Activation Link..." : "Send Fresh Activation Link →"}
            </button>
          </form>

          <div className="border-t border-slate-800 pt-4 flex items-center justify-between text-xs text-slate-400">
            <Link href="/activate" className="text-blue-400 hover:underline">
              Have an activation token?
            </Link>
            <Link href="/" className="hover:text-white">
              Back to Sign In
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
