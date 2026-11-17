"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { apiActivateAccount } from "@/lib/api";
import { AccountActivationResponse } from "@/lib/types";

function ActivateForm() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activationResult, setActivationResult] = useState<AccountActivationResponse | null>(null);

  useEffect(() => {
    const qToken = searchParams.get("token");
    if (qToken) {
      setToken(qToken);
    }
  }, [searchParams]);

  // Password Policy Checklist
  const hasMinLength = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;
  const isPasswordValid = hasMinLength && hasUpper && hasLower && hasDigit && hasSpecial && passwordsMatch;

  const handleActivate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      setError("Please provide a valid single-use activation token.");
      return;
    }

    if (!isPasswordValid) {
      setError("Password does not meet all security policy requirements.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await apiActivateAccount({
        activation_token: token.trim(),
        password,
        confirm_password: confirmPassword,
      });
      setActivationResult(res);
    } catch (err: any) {
      setError(
        err.message ||
          "Activation failed. The token may be invalid, expired (72h limit), or already consumed."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-lg mx-auto">
      {/* SUCCESS CONFIRMATION VIEW */}
      {activationResult ? (
        <div className="rounded-3xl border border-emerald-500/40 bg-slate-900/90 p-8 sm:p-10 text-center space-y-6 shadow-2xl">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-600/20 border border-emerald-500/40 text-3xl text-emerald-400 shadow-inner">
            ✓
          </div>
          <div>
            <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
              Account Activated Successfully
            </span>
            <h2 className="mt-3 text-2xl font-bold text-white">
              Welcome to SIH Healthcare Operations
            </h2>
            <p className="mt-2 text-xs text-slate-300">
              Your credentials have been securely provisioned and stored with PBKDF2-HMAC-SHA256 encryption.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-950 p-5 text-left space-y-2.5 font-mono text-xs">
            <div>
              <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">Assigned Username</span>
              <p className="text-sm font-bold text-blue-400 select-all">{activationResult.username}</p>
            </div>
            <div className="border-t border-slate-800 pt-2 flex justify-between">
              <div>
                <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">Assigned Role</span>
                <p className="text-slate-200">{activationResult.role}</p>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-slate-500 uppercase font-sans font-bold">Application</span>
                <p className="text-slate-400">{activationResult.application_number}</p>
              </div>
            </div>
          </div>

          <div className="pt-2">
            <Link
              href="/portal/hospital/login"
              className="block w-full text-center rounded-xl bg-blue-600 py-3 text-xs font-bold text-white hover:bg-blue-500 transition shadow"
            >
              Sign In to Healthcare Dashboard →
            </Link>
          </div>
        </div>
      ) : (
        /* ACTIVATION FORM */
        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 sm:p-8 shadow-2xl space-y-6">
          <div className="text-center space-y-2">
            <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
              Official Account Provisioning
            </span>
            <h1 className="text-xl sm:text-2xl font-bold text-white">
              Activate Operational Account
            </h1>
            <p className="text-xs text-slate-400">
              Set your initial operational password to activate your approved healthcare portal account.
            </p>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
              <span className="text-base">⚠️</span>
              <div className="flex-1">{error}</div>
            </div>
          )}

          <form onSubmit={handleActivate} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Single-Use Activation Token *
              </label>
              <input
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Enter 32+ character activation token"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500 font-mono"
                required
              />
              <span className="mt-1 block text-[11px] text-slate-500">
                Supplied in your official approval notification email. Valid for 72 hours.
              </span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300">
                New Operational Password *
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter secure password"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Confirm Operational Password *
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-white placeholder-slate-600 outline-none focus:border-blue-500"
                required
              />
            </div>

            {/* Password Complexity Checklist */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-1.5 text-[11px]">
              <span className="font-bold text-slate-400 block mb-1">Password Policy Requirements:</span>
              <div className="grid grid-cols-2 gap-1.5">
                <span className={hasMinLength ? "text-emerald-400" : "text-slate-500"}>
                  {hasMinLength ? "✓" : "○"} At least 8 characters
                </span>
                <span className={hasUpper ? "text-emerald-400" : "text-slate-500"}>
                  {hasUpper ? "✓" : "○"} 1+ Uppercase letter (A-Z)
                </span>
                <span className={hasLower ? "text-emerald-400" : "text-slate-500"}>
                  {hasLower ? "✓" : "○"} 1+ Lowercase letter (a-z)
                </span>
                <span className={hasDigit ? "text-emerald-400" : "text-slate-500"}>
                  {hasDigit ? "✓" : "○"} 1+ Numeric digit (0-9)
                </span>
                <span className={hasSpecial ? "text-emerald-400" : "text-slate-500"}>
                  {hasSpecial ? "✓" : "○"} 1+ Special character
                </span>
                <span className={passwordsMatch ? "text-emerald-400" : "text-slate-500"}>
                  {passwordsMatch ? "✓" : "○"} Passwords match
                </span>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !isPasswordValid || !token.trim()}
              className="w-full rounded-xl bg-blue-600 py-3 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-40 transition shadow"
            >
              {loading ? "Activating Operational Account..." : "Confirm & Activate Account →"}
            </button>
          </form>

          <div className="border-t border-slate-800 pt-4 flex items-center justify-between text-xs text-slate-400">
            <Link href="/activate/resend" className="text-blue-400 hover:underline">
              Need to resend activation link?
            </Link>
            <Link href="/" className="hover:text-white">
              Back to Sign In
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ActivatePage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />
      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 py-12">
        <Suspense fallback={<div className="text-xs text-slate-400">Loading activation session...</div>}>
          <ActivateForm />
        </Suspense>
      </main>
    </div>
  );
}
