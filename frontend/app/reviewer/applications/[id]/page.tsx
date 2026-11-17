"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import { User } from "@/lib/types";
import { getStoredUser } from "@/lib/api";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";
import { ReviewerPortal } from "@/components/reviewer/ReviewerPortal";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ReviewerApplicationDetailPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const applicationId = resolvedParams.id;

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
        <div className="text-xs text-slate-400">Loading dossier session...</div>
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
              Please sign in to your authorized District, State, or Central administrative account to review this application.
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
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-8">
        <ReviewerPortal user={user} initialApplicationId={applicationId} />
      </main>
    </div>
  );
}
