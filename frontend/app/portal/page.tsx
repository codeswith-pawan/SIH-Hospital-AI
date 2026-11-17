"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  MapPin,
  ShieldCheck,
  Globe,
  ArrowRight,
  Lock,
  ChevronRight,
  Shield,
  CheckCircle2,
  UserCheck,
} from "lucide-react";
import { GovernmentHeader } from "@/components/shared/GovernmentHeader";
import { GovernmentFooter } from "@/components/shared/GovernmentFooter";
import { getStoredUser } from "@/lib/api";
import { User } from "@/lib/types";

const DEPARTMENTS = [
  {
    id: "hospital",
    title: "HOSPITAL PORTAL",
    tagline: "Facility Operations & Bed Allocation",
    tier: "Facility Tier",
    icon: Building2,
    iconColor: "text-blue-600 bg-blue-50 border-blue-200",
    hoverBorder: "hover:border-blue-400 group-hover:border-blue-500",
    badgeColor: "bg-blue-50 text-blue-800 border-blue-200",
    buttonColor: "bg-blue-800 hover:bg-blue-900 text-white",
    description:
      "Facility-level management for inpatient admissions, ICU bed inventory, emergency triage, and inter-hospital patient transfers.",
    features: [
      "Hospital administration",
      "Bed and inventory management",
      "Patient referrals",
      "Operational dashboard",
    ],
    loginPath: "/portal/hospital/login",
  },
  {
    id: "district",
    title: "DISTRICT PORTAL",
    tagline: "Jurisdiction Monitoring & Accreditation",
    tier: "District Tier",
    icon: MapPin,
    iconColor: "text-indigo-600 bg-indigo-50 border-indigo-200",
    hoverBorder: "hover:border-indigo-400 group-hover:border-indigo-500",
    badgeColor: "bg-indigo-50 text-indigo-800 border-indigo-200",
    buttonColor: "bg-indigo-800 hover:bg-indigo-900 text-white",
    description:
      "District health surveillance, hospital registration verification, application review, and localized coordination.",
    features: [
      "District hospital monitoring",
      "Hospital verification",
      "Application review",
      "District-level coordination",
    ],
    loginPath: "/portal/district/login",
  },
  {
    id: "state",
    title: "STATE PORTAL",
    tagline: "Directorate Oversight & Policy Approvals",
    tier: "State Tier",
    icon: ShieldCheck,
    iconColor: "text-teal-600 bg-teal-50 border-teal-200",
    hoverBorder: "hover:border-teal-400 group-hover:border-teal-500",
    badgeColor: "bg-teal-50 text-teal-800 border-teal-200",
    buttonColor: "bg-teal-800 hover:bg-teal-900 text-white",
    description:
      "State-wide hospital administration, inter-district monitoring, stage-2 application approvals, and regional performance analytics.",
    features: [
      "State hospital administration",
      "District monitoring",
      "State-level approvals",
      "Performance overview",
    ],
    loginPath: "/portal/state/login",
  },
  {
    id: "central",
    title: "CENTRAL PORTAL",
    tagline: "National Coordination & Governance",
    tier: "National Tier",
    icon: Globe,
    iconColor: "text-purple-600 bg-purple-50 border-purple-200",
    hoverBorder: "hover:border-purple-400 group-hover:border-purple-500",
    badgeColor: "bg-purple-50 text-purple-800 border-purple-200",
    buttonColor: "bg-purple-800 hover:bg-purple-900 text-white",
    description:
      "National-level surveillance, apex hospital accreditation approvals, nationwide bed availability tracking, and system oversight.",
    features: [
      "National-level monitoring",
      "State and district administration",
      "Hospital approvals",
      "System-wide oversight",
    ],
    loginPath: "/portal/central/login",
  },
];

export default function PortalSelectionPage() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  useEffect(() => {
    const u = getStoredUser();
    if (u) setCurrentUser(u);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-800">
      <GovernmentHeader />

      {/* Breadcrumb Section */}
      <div className="bg-white border-b border-slate-200 py-3 px-4 sm:px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-slate-500">
            <Link href="/" className="hover:text-blue-900 font-medium transition">
              Home
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-800 font-semibold">Department Selection</span>
          </div>

          <div className="flex items-center gap-1.5 text-slate-600">
            <Lock className="w-3.5 h-3.5 text-emerald-600" />
            <span className="text-[11px] font-medium hidden sm:inline">
              Secured Ministry Healthcare Gateway
            </span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-10 sm:py-14 space-y-10">
        {/* Page Header */}
        <div className="text-center max-w-3xl mx-auto space-y-3">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 px-3 py-1 text-xs font-bold text-blue-900 tracking-wide uppercase">
            <Shield className="w-3.5 h-3.5 text-blue-700" />
            <span>Authorized Health Personnel Access</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
            Select Your Department
          </h1>
          <p className="text-sm sm:text-base text-slate-600 leading-relaxed">
            Choose your authorized department to access the portal. Each department provides tailored administrative tools, jurisdictional data isolation, and live operational dashboards.
          </p>

          {currentUser && (
            <div className="mt-4 p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 inline-flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>
                You are currently signed in as <strong>{currentUser.username}</strong> ({currentUser.role}).
              </span>
              <Link href="/" className="ml-2 underline font-bold hover:text-emerald-950">
                Go to My Dashboard →
              </Link>
            </div>
          )}
        </div>

        {/* 4 Professional Department Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {DEPARTMENTS.map((dept) => {
            const Icon = dept.icon;
            return (
              <div
                key={dept.id}
                className="group relative flex flex-col justify-between rounded-xl bg-white border border-slate-200 p-6 shadow-xs hover:shadow-md hover:border-slate-300 transition duration-200 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2"
              >
                <div className="space-y-4">
                  {/* Top Bar: Icon + Tier Badge */}
                  <div className="flex items-center justify-between">
                    <div
                      className={`flex h-12 w-12 items-center justify-center rounded-xl border ${dept.iconColor} shadow-xs transition group-hover:scale-105`}
                    >
                      <Icon className="w-6 h-6" />
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase border ${dept.badgeColor}`}
                    >
                      {dept.tier}
                    </span>
                  </div>

                  {/* Title & Tagline */}
                  <div>
                    <h2 className="text-base sm:text-lg font-bold text-slate-900 group-hover:text-blue-900 transition">
                      {dept.title}
                    </h2>
                    <p className="text-[11px] font-semibold text-slate-500 mt-0.5">
                      {dept.tagline}
                    </p>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-slate-600 leading-relaxed">
                    {dept.description}
                  </p>

                  {/* Key Features List */}
                  <div className="pt-2 border-t border-slate-100 space-y-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      Key Capabilities:
                    </span>
                    <ul className="space-y-1.5 text-xs text-slate-700">
                      {dept.features.map((feat) => (
                        <li key={feat} className="flex items-start gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Bottom CTA Action Button */}
                <div className="pt-6 mt-4 border-t border-slate-100">
                  <Link
                    href={dept.loginPath}
                    className={`w-full flex items-center justify-center gap-2 rounded-lg py-2.5 px-4 text-xs font-bold transition shadow-xs ${dept.buttonColor}`}
                  >
                    <span>Login to {dept.id.charAt(0).toUpperCase() + dept.id.slice(1)}</span>
                    <ArrowRight className="w-3.5 h-3.5 transition group-hover:translate-x-1" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>

        {/* Security & Access Information */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-50 border border-amber-200 text-amber-700">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
                Role-Based Access Control (RBAC) Notice
              </h3>
              <p className="text-xs text-slate-600 mt-0.5 max-w-2xl">
                Access is restricted to authorized administrative personnel and accredited healthcare providers. User sessions and system actions are authenticated and audited in accordance with role-based access control policies.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Link
              href="/register"
              className="rounded-lg border border-slate-300 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
            >
              Register Facility
            </Link>
            <Link
              href="/application/track"
              className="rounded-lg border border-slate-300 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
            >
              Track Status
            </Link>
          </div>
        </div>
      </main>

      <GovernmentFooter />
    </div>
  );
}
