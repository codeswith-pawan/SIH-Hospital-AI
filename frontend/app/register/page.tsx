"use client";

import React from "react";
import Link from "next/link";
import { RegistrationNavbar } from "@/components/registration/RegistrationNavbar";

export default function RegisterHubPage() {
  const tiers = [
    {
      type: "HOSPITAL",
      title: "Hospital & Healthcare Facility",
      desc: "For government, municipal, charitable, and accredited private hospitals offering inpatient or emergency beds.",
      badge: "Hospital Tier",
      badgeColor: "border-blue-500/30 text-blue-300 bg-blue-500/10",
      icon: "🏥",
      href: "/register/hospital",
      requirements: [
        "Clinical Establishment Registration (Act / Reg. No.)",
        "Fire Safety NOC Clearance Certificate",
        "Designated Nodal Officer & Emergency Contact",
        "Bed & ICU Operational Capacities",
      ],
      cta: "Register Hospital Facility",
      popular: true,
    },
    {
      type: "DISTRICT",
      title: "District Health Administration",
      desc: "For Chief Medical Officers (CMO) and District Health Offices overseeing territorial bed inventory and ambulances.",
      badge: "District Tier",
      badgeColor: "border-indigo-500/30 text-indigo-300 bg-indigo-500/10",
      icon: "🏛️",
      href: "/register/district",
      requirements: [
        "Official Government Authorization Order",
        "Chief Medical Officer / Civil Surgeon Designation",
        "Government Email & Contact Credentials",
        "Designated District Territorial Jurisdiction",
      ],
      cta: "Register District Authority",
      popular: false,
    },
    {
      type: "STATE",
      title: "State Health Directorate",
      desc: "For State Health Departments, Medical Education Directorates, and State Health Missions governing state-wide healthcare.",
      badge: "State Tier",
      badgeColor: "border-teal-500/30 text-teal-300 bg-teal-500/10",
      icon: "🏢",
      href: "/register/state",
      requirements: [
        "State Health Mission / Directorate Order",
        "Principal Secretary / Director of Health Authorization",
        "Official State Health Department Domain Email",
        "Territorial State Jurisdiction Assignment",
      ],
      cta: "Register State Directorate",
      popular: false,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col font-sans">
      <RegistrationNavbar />

      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-10 sm:py-14 space-y-12">
        {/* Header Hero */}
        <div className="text-center max-w-3xl mx-auto space-y-3">
          <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-bold text-blue-400 border border-blue-500/20 uppercase tracking-wider">
            Hierarchical Governance Onboarding
          </span>
          <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white">
            Healthcare Entity Registration
          </h1>
          <p className="text-sm sm:text-base text-slate-400">
            Select your administrative jurisdiction or medical facility classification to begin the official multi-tier verification and provisioning workflow.
          </p>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
          {tiers.map((t) => (
            <div
              key={t.type}
              className={`rounded-2xl border bg-slate-900/80 p-6 sm:p-8 flex flex-col justify-between relative transition hover:border-blue-500/50 hover:shadow-xl ${
                t.popular ? "border-blue-500/40 shadow-blue-900/20 shadow-lg" : "border-slate-800"
              }`}
            >
              {t.popular && (
                <div className="absolute -top-3 right-6 rounded-full bg-blue-600 px-3 py-0.5 text-[10px] font-bold text-white shadow">
                  MOST ACTIVE
                </div>
              )}

              <div>
                <div className="flex items-center justify-between">
                  <span className="text-3xl">{t.icon}</span>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${t.badgeColor}`}
                  >
                    {t.badge}
                  </span>
                </div>

                <h2 className="mt-4 text-lg font-bold text-white">{t.title}</h2>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">{t.desc}</p>

                <div className="mt-6 border-t border-slate-800/80 pt-4">
                  <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2.5">
                    Prerequisites & Requirements
                  </h3>
                  <ul className="space-y-2 text-xs text-slate-400">
                    {t.requirements.map((req, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-blue-400 text-[10px] mt-0.5">✔</span>
                        <span>{req}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-8 pt-4">
                <Link
                  href={t.href}
                  className={`block w-full text-center rounded-xl py-3 px-4 text-xs font-bold transition shadow ${
                    t.popular
                      ? "bg-blue-600 text-white hover:bg-blue-500"
                      : "bg-slate-800 text-slate-200 hover:bg-slate-700 hover:text-white border border-slate-700"
                  }`}
                >
                  {t.cta} →
                </Link>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom Fast Access Banner */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 sm:p-8 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="space-y-1 text-center sm:text-left">
            <h3 className="text-base font-bold text-white">Already Have An Active Application?</h3>
            <p className="text-xs text-slate-400">
              Track real-time approval milestones with your tracking token or resume editing your draft application.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/application/track"
              className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition"
            >
              🔍 Track by Reference Token
            </Link>
            <Link
              href="/application/status"
              className="rounded-xl bg-blue-600/20 border border-blue-500/30 px-4 py-2.5 text-xs font-semibold text-blue-300 hover:bg-blue-600/30 transition"
            >
              🔐 Applicant Login / Resume Draft
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
