"use client";

import React, { useState } from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { apiRequestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Please provide your registered operational email address.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await apiRequestPasswordReset({ email: email.trim() });
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || "Failed to process password reset request.");
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
              Security Recovery
            </span>
            <h1 className="text-xl sm:text-2xl font-bold text-white">
              Reset Account Password
            </h1>
            <p className="text-xs text-slate-400">
              Enter your registered official email address to receive password recovery instructions.
            </p>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
              <span className="text-base">⚠️</span>
              <div className="flex-1">{error}</div>
            </div>
          )}

          {submitted ? (
            <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/20 p-5 text-center space-y-4">
              <span className="text-3xl block">✉️</span>
              <h2 className="text-sm font-bold text-emerald-300">Password Recovery Request Received</h2>
              <p className="text-xs text-slate-300 leading-relaxed">
                If an operational account is associated with <strong className="text-white">{email}</strong>, a secure password recovery link has been dispatched.
              </p>
              <p className="text-[11px] text-slate-400">
                The link is valid for 1 hour. Please check your inbox and spam folder.
              </p>
              <div className="pt-2">
                <Link
                  href="/"
                  className="inline-block rounded-xl border border-slate-700 bg-slate-800 px-5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  ← Return to Sign In
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Registered Operational Email *
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. admin@hospital.punjab.gov.in"
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl bg-blue-600 py-3 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow"
              >
                {loading ? "Processing Request..." : "Send Recovery Instructions →"}
              </button>
            </form>
          )}

          <div className="border-t border-slate-800 pt-4 flex items-center justify-between text-xs text-slate-400">
            <Link href="/reset-password" className="text-blue-400 hover:underline">
              Already have a reset token?
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
