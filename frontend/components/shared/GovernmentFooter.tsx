"use client";

import React from "react";
import Link from "next/link";
import { Hospital, ShieldCheck, Mail, Phone } from "lucide-react";

export const GovernmentFooter: React.FC = () => {
  return (
    <footer className="bg-slate-900 text-slate-300 border-t border-slate-800 text-xs">
      {/* Upper Footer Links */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8">
          {/* Col 1: Identity & Emblems */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-900/60 border border-blue-500/30 text-white">
                <Hospital className="w-5 h-5 text-sky-400" />
              </div>
              <div>
                <span className="text-base font-bold text-white tracking-tight">
                  SIH Hospital AI
                </span>
                <p className="text-[11px] text-slate-400">
                  National Hospital Management & Coordination Platform
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed pr-4">
              An integrated healthcare digital platform unifying hospital bed inventory, critical care allocation, and multi-tier accreditation verification across District, State, and Central jurisdictions.
            </p>

            <div className="flex items-center gap-2 pt-2 text-[11px] text-slate-400">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Data Protection & Role-Based Jurisdictional Isolation</span>
            </div>
          </div>

          {/* Col 2: Department Portals */}
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">
              Department Portals
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link href="/portal/hospital/login" className="hover:text-white transition">
                  Hospital Operations Portal
                </Link>
              </li>
              <li>
                <Link href="/portal/district/login" className="hover:text-white transition">
                  District Health Authority
                </Link>
              </li>
              <li>
                <Link href="/portal/state/login" className="hover:text-white transition">
                  State Health Directorate
                </Link>
              </li>
              <li>
                <Link href="/portal/central/login" className="hover:text-white transition">
                  Central Health Command
                </Link>
              </li>
              <li>
                <Link href="/portal" className="text-sky-400 hover:underline">
                  All Portals Overview →
                </Link>
              </li>
            </ul>
          </div>

          {/* Col 3: Onboarding & Services */}
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">
              Registration & Verification
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link href="/register/hospital" className="hover:text-white transition">
                  Hospital Facility Onboarding
                </Link>
              </li>
              <li>
                <Link href="/register/district" className="hover:text-white transition">
                  District Authority Registration
                </Link>
              </li>
              <li>
                <Link href="/register/state" className="hover:text-white transition">
                  State Directorate Registration
                </Link>
              </li>
              <li>
                <Link href="/application/track" className="hover:text-white transition">
                  Track Application Status
                </Link>
              </li>
              <li>
                <Link href="/activate" className="hover:text-white transition">
                  Activate Provisioned Account
                </Link>
              </li>
            </ul>
          </div>

          {/* Col 4: Helpdesk & Emergency */}
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-3">
              Emergency & Technical Helpdesk
            </h4>
            <ul className="space-y-2 text-xs text-slate-400">
              <li className="flex items-center gap-2">
                <Phone className="w-3.5 h-3.5 text-sky-400" />
                <span>Ambulance Emergency: <strong>108</strong> (States/UTs)</span>
              </li>
              <li className="flex items-center gap-2">
                <Phone className="w-3.5 h-3.5 text-emerald-400" />
                <span>Health Inquiries: <strong>1075</strong> (Toll-Free, MoHFW)</span>
              </li>
              <li className="flex items-center gap-2">
                <Mail className="w-3.5 h-3.5 text-slate-400" />
                <span>support@sih.hospital.ai</span>
              </li>
              <li className="pt-2">
                <span className="text-[11px] text-slate-400">
                  Developed for the Smart India Hackathon as a technical prototype. Not an official Government of India portal.
                </span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* Tricolor divider */}
      <div className="h-0.5 w-full bg-gradient-to-r from-amber-500 via-white to-emerald-600" />

      {/* Bottom Copyright & Disclaimer */}
      <div className="bg-slate-950 py-4 px-4 sm:px-6 text-[11px] text-slate-400">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>
            © 2026 SIH Hospital AI. Smart India Hackathon Technical Reference Platform.
          </p>
          <div className="flex items-center gap-4 text-slate-400">
            <span className="hover:text-slate-300">Privacy Policy</span>
            <span>•</span>
            <span className="hover:text-slate-300">Terms of Service</span>
            <span>•</span>
            <span className="hover:text-slate-300">Hyperlinking Policy</span>
            <span>•</span>
            <span className="hover:text-slate-300">Accessibility Statement</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
