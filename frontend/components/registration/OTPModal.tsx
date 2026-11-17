"use client";

import React, { useState, useEffect } from "react";
import { apiSendRegistrationOTP, apiVerifyRegistrationOTP } from "@/lib/api";
import { OTPVerifyResponse } from "@/lib/types";

interface OTPModalProps {
  isOpen: boolean;
  onClose: () => void;
  contactTarget: string;
  purpose?: "REGISTRATION_OTP" | "PORTAL_ACCESS_OTP";
  applicationNumber?: string;
  onVerified: (response: OTPVerifyResponse) => void;
}

export const OTPModal: React.FC<OTPModalProps> = ({
  isOpen,
  onClose,
  contactTarget,
  purpose = "REGISTRATION_OTP",
  applicationNumber,
  onVerified,
}) => {
  const [tokenId, setTokenId] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [countdown, setCountdown] = useState(60);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [infoMessage, setInfoMessage] = useState("");

  const handleRequestOTP = async () => {
    setSending(true);
    setError("");
    setInfoMessage("");
    setOtp("");

    try {
      const res = await apiSendRegistrationOTP({
        contact_target: contactTarget.trim(),
        channel: "EMAIL",
        purpose,
        application_number: applicationNumber,
      });

      setTokenId(res.token_id);
      setCountdown(res.resend_available_in_seconds || 60);
      setInfoMessage(`Verification code dispatched to ${contactTarget}.`);
    } catch (err: any) {
      setError(err.message || "Failed to dispatch verification code. Please check email address.");
    } finally {
      setSending(false);
    }
  };

  // Request OTP when opened or contact target changes
  useEffect(() => {
    if (isOpen && contactTarget) {
      handleRequestOTP();
    } else {
      setOtp("");
      setError("");
      setInfoMessage("");
    }
  }, [isOpen, contactTarget]);

  // Countdown timer for resend cooldown
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tokenId) {
      setError("No active verification token. Please click Resend OTP.");
      return;
    }

    if (otp.trim().length !== 6) {
      setError("Please enter the 6-digit numeric verification code.");
      return;
    }

    setVerifying(true);
    setError("");

    try {
      const res = await apiVerifyRegistrationOTP({
        token_id: tokenId,
        otp: otp.trim(),
        purpose,
        application_number: applicationNumber,
      });

      if (res.verified) {
        onVerified(res);
        onClose();
      } else {
        setError(res.message || "Verification code could not be validated.");
      }
    } catch (err: any) {
      setError(err.message || "Invalid or expired verification code.");
    } finally {
      setVerifying(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-7 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400">
              ✉
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">Email Verification</h3>
              <p className="text-[11px] text-slate-400">Two-Factor Security Authentication</p>
            </div>
          </div>
          <button
            onClick={onClose}
            type="button"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleVerify} className="mt-5 space-y-4">
          <p className="text-xs text-slate-300">
            A 6-digit verification code has been dispatched to:
            <br />
            <strong className="text-blue-400 font-semibold">{contactTarget}</strong>
          </p>

          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Enter 6-Digit Code
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
              placeholder="123456"
              className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-center text-xl font-mono tracking-widest text-white placeholder-slate-600 outline-none focus:border-blue-500 transition"
              autoFocus
              required
            />
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
              {error}
            </div>
          )}

          {infoMessage && (
            <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-2.5 text-xs text-blue-300">
              {infoMessage}
            </div>
          )}

          <div className="flex items-center justify-between pt-1 text-xs">
            <button
              type="button"
              disabled={countdown > 0 || sending}
              onClick={handleRequestOTP}
              className={`font-medium transition ${
                countdown > 0 || sending
                  ? "text-slate-500 cursor-not-allowed"
                  : "text-blue-400 hover:underline"
              }`}
            >
              {sending
                ? "Sending code..."
                : countdown > 0
                ? `Resend code in ${countdown}s`
                : "Resend Code"}
            </button>
          </div>

          <div className="mt-6 flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={verifying || otp.trim().length !== 6}
              className="flex-1 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {verifying ? "Verifying..." : "Confirm & Proceed"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
