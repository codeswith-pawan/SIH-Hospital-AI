"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { User } from "@/lib/types";
import { getStoredUser } from "@/lib/api";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { ReviewerPortal } from "@/components/reviewer/ReviewerPortal";

export default function ReviewerPage() {
  const [user, setUser] = useState<User | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = getStoredUser();
    if (stored) {
      setUser(stored);
    }
  }, []);

  if (!mounted) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        <div className="text-xs text-slate-400">Loading reviewer authentication session...</div>
      </div>
    );
  }

  const isReviewer =
    user && (user.role === "DISTRICT_ADMIN" || user.role === "STATE_ADMIN" || user.role === "CENTRAL_ADMIN");

  if (!isReviewer) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
        <RegistrationNavbar />
        <main className="flex-1 flex items-center justify-center p-6">
          <div className="max-w-md w-full rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center space-y-4 shadow-xl">
            <span className="text-4xl block">🔒</span>
            <h1 className="text-lg font-bold text-white">Reviewer Authentication Required</h1>
            <p className="text-xs text-slate-400 leading-relaxed">
              Access to the Healthcare Registration Review Queue requires an active District, State, or Central administrative session.
            </p>
            <div className="pt-2">
              <Link
                href="/"
                className="inline-block rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-blue-500 transition"
              >
                Sign in to Operational Account →
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-[10px] font-bold text-blue-400 uppercase tracking-wider">
                Government Reviewer Portal
              </span>
              <span className="text-xs text-slate-400">
                Tier: <strong className="text-white">{user.role.replace(/_/g, " ")}</strong>
              </span>
            </div>
            <h1 className="mt-1 text-2xl font-extrabold text-white">
              Healthcare Registration Review Queue
            </h1>
            <p className="text-xs text-slate-400">
              Authority: {user.name} ({user.username}) {user.district ? `• District: ${user.district}` : ""} {user.state ? `• State: ${user.state}` : ""}
            </p>
          </div>

          <Link
            href="/"
            className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition"
          >
            ← Open Operations Dashboard
          </Link>
        </div>

        <ReviewerPortal user={user} />
      </main>
    </div>
  );
}
