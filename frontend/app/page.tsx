"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  MapPin,
  ShieldCheck,
  Globe,
  ArrowRight,
  Shield,
  Activity,
  BedDouble,
  FileCheck2,
  CheckCircle2,
  ChevronRight,
  PhoneCall,
  Layers,
  HeartPulse,
  BadgeCheck,
  Lock,
  Hospital,
} from "lucide-react";
import HospitalDashboard from "@/components/HospitalDashboard";
import DistrictDashboard from "@/components/DistrictDashboard";
import StateDashboard from "@/components/StateDashboard";
import CentralDashboard from "@/components/CentralDashboard";
import { User } from "@/lib/types";
import {
  getStoredUser,
  clearStoredSession,
} from "@/lib/api";
import { LoadingState } from "@/components/shared/LoadingAndErrorStates";
import { GovernmentHeader } from "@/components/shared/GovernmentHeader";
import { GovernmentFooter } from "@/components/shared/GovernmentFooter";

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [mounted, setMounted] = useState(false);

  // Restore authenticated session on page refresh
  useEffect(() => {
    setMounted(true);
    const stored = getStoredUser();
    if (stored) {
      setUser(stored);
    }
  }, []);

  const handleSignOut = () => {
    clearStoredSession();
    setUser(null);
  };

  if (!mounted) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <LoadingState message="Initializing healthcare session..." />
      </main>
    );
  }

  // Route to Authorized Tier Dashboard if authenticated
  if (user) {
    if (user.role === "HOSPITAL") {
      return <HospitalDashboard user={user} />;
    }
    if (user.role === "DISTRICT_ADMIN") {
      return <DistrictDashboard user={user} />;
    }
    if (user.role === "STATE_ADMIN") {
      return <StateDashboard user={user} />;
    }
    if (user.role === "CENTRAL_ADMIN") {
      return <CentralDashboard user={user} />;
    }

    return (
      <main className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center p-6">
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center max-w-md shadow-xs">
          <h1 className="text-xl font-bold">Unrecognized Healthcare Role</h1>
          <p className="mt-2 text-xs text-slate-500">
            Account {user.username} with role {user.role} does not have an active dashboard configuration.
          </p>
          <button
            onClick={handleSignOut}
            className="mt-5 rounded-lg bg-blue-900 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-800"
          >
            Sign Out & Return
          </button>
        </div>
      </main>
    );
  }

  // Public Government Healthcare Landing Page
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans">
      <GovernmentHeader />

      {/* Hero Section */}
      <section className="relative bg-white border-b border-slate-200 overflow-hidden">
        {/* Subtle patterned backdrop */}
        <div className="absolute inset-0 bg-[radial-gradient(#e2e8f0_1px,transparent_1px)] [background-size:16px_16px] opacity-40 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 py-14 sm:py-20 lg:py-24">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            {/* Left Column: Hero Text & CTAs */}
            <div className="lg:col-span-7 space-y-6 text-left">
              <div className="inline-flex items-center gap-2 rounded-full bg-blue-50 border border-blue-200 px-3 py-1 text-xs font-bold text-blue-900 tracking-wide uppercase">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>SIH Healthcare Reference Platform</span>
              </div>

              <h1 className="text-3xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15]">
                National Hospital Management & Coordination Portal
              </h1>

              <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-2xl">
                A unified digital platform for hospital administration, healthcare coordination, registration, verification and monitoring.
              </p>

              {/* CTAs */}
              <div className="flex flex-wrap items-center gap-3.5 pt-2">
                <Link
                  href="/portal"
                  className="rounded-lg bg-blue-900 px-6 py-3 text-sm font-bold text-white hover:bg-blue-800 transition shadow-xs flex items-center gap-2"
                >
                  <span>Explore Portal</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>

                <Link
                  href="/register"
                  className="rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 hover:text-blue-900 transition shadow-2xs flex items-center gap-2"
                >
                  <FileCheck2 className="w-4 h-4 text-blue-800" />
                  <span>Register Hospital</span>
                </Link>

                <Link
                  href="/application/track"
                  className="rounded-lg px-4 py-3 text-sm font-semibold text-slate-600 hover:text-blue-900 transition flex items-center gap-1.5"
                >
                  <span>Track Application</span>
                  <ChevronRight className="w-4 h-4 text-slate-400" />
                </Link>
              </div>

              {/* Highlights Checklist */}
              <div className="pt-6 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-slate-600">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Multi-Tier Verification</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Real-Time Bed Accounting</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Jurisdictional Isolation</span>
                </div>
              </div>
            </div>

            {/* Right Column: Key Portal Quick Cards */}
            <div className="lg:col-span-5 space-y-4">
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-6 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Administrative Access Tiers
                  </span>
                  <Link href="/portal" className="text-xs font-bold text-blue-800 hover:underline">
                    View All 4 Tiers →
                  </Link>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <Link
                    href="/portal/hospital/login"
                    className="p-3.5 rounded-lg border border-slate-200 bg-white hover:border-blue-300 hover:shadow-2xs transition group"
                  >
                    <Building2 className="w-5 h-5 text-blue-600 mb-2" />
                    <h4 className="text-xs font-bold text-slate-900 group-hover:text-blue-900">Hospital Portal</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">Beds & Triage</p>
                  </Link>

                  <Link
                    href="/portal/district/login"
                    className="p-3.5 rounded-lg border border-slate-200 bg-white hover:border-indigo-300 hover:shadow-2xs transition group"
                  >
                    <MapPin className="w-5 h-5 text-indigo-600 mb-2" />
                    <h4 className="text-xs font-bold text-slate-900 group-hover:text-indigo-900">District Portal</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">Local Review</p>
                  </Link>

                  <Link
                    href="/portal/state/login"
                    className="p-3.5 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:shadow-2xs transition group"
                  >
                    <ShieldCheck className="w-5 h-5 text-teal-600 mb-2" />
                    <h4 className="text-xs font-bold text-slate-900 group-hover:text-teal-900">State Portal</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">Directorate</p>
                  </Link>

                  <Link
                    href="/portal/central/login"
                    className="p-3.5 rounded-lg border border-slate-200 bg-white hover:border-purple-300 hover:shadow-2xs transition group"
                  >
                    <Globe className="w-5 h-5 text-purple-600 mb-2" />
                    <h4 className="text-xs font-bold text-slate-900 group-hover:text-purple-900">Central Portal</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">National Oversight</p>
                  </Link>
                </div>

                <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-[11px] text-blue-900 flex items-start gap-2">
                  <Shield className="w-4 h-4 text-blue-700 shrink-0 mt-0.5" />
                  <span>
                    Direct access is restricted by jurisdictional credentials. Non-registered facilities must submit accreditation dossiers.
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 1: About the Portal */}
      <section id="about" className="py-16 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-12">
          <div className="text-center max-w-3xl mx-auto space-y-3">
            <span className="text-xs font-bold tracking-wider uppercase text-blue-800">
              Platform Overview
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              About the National Healthcare Coordination Portal
            </h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Designed under the Smart India Hackathon framework, this portal unifies health directorates, district health administrations, and frontline public/private hospitals into a single, real-time healthcare logistics infrastructure.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 text-blue-800">
                <HeartPulse className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Critical Care Logistics</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Connects emergency rooms and ICUs across facilities to prevent patient transfer delays and ambulance diversions during critical care surges.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 text-emerald-800">
                <BadgeCheck className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Transparent Accreditation</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                A structured 3-tier regulatory pipeline ensuring verified clinical licenses, fire safety compliance, and pollution control clearances before network admission.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-100 text-purple-800">
                <Layers className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Multi-Tier Governance</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Granular data segregation from hospital-level patient files up to aggregated district, state, and central healthcare telemetry.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: Key Services */}
      <section id="services" className="py-16 bg-slate-50 border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-12">
          <div className="text-center max-w-3xl mx-auto space-y-3">
            <span className="text-xs font-bold tracking-wider uppercase text-blue-800">
              Core Capabilities
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Comprehensive Health System Services
            </h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Equipping public health administrators and medical officers with high-reliability digital tools.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                <BedDouble className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Bed & ICU Allocation</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Live bed accounting with atomic reservations and automatic expiry release mechanisms to prevent artificial hoarding.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                <Activity className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Clinical Referrals</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                End-to-end referral dispatch, priority triage, ambulance transit tracking, and bedside admission confirmations.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                <FileCheck2 className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Hospital Accreditation</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Digital application filing with nodal officer OTP verification, document review, and multi-tier government sign-offs.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">System Telemetry</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Real-time operational monitoring, worker heartbeats, database connection pool stats, and SLA threshold alerts.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 3: Hospital Network & Capability Surveillance (Audited: Secure, Informative Overview) */}
      <section id="network" className="py-16 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <span className="text-xs font-bold tracking-wider uppercase text-blue-800">
                Hospital Network Architecture
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mt-1">
                Accredited Hospital Network & Capacity Surveillance
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
                Real-time bed availability tracking, dynamic capacity surveillance, and verified clinical decision support across accredited multi-tier healthcare facilities.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Link
                href="/portal/hospital/login"
                className="rounded-lg bg-blue-900 text-white px-4 py-2 text-xs font-bold hover:bg-blue-800 transition shadow-xs"
              >
                Access Hospital Operations →
              </Link>
            </div>
          </div>

          {/* Network Tier Architecture Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3 shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-blue-100 text-blue-800 px-2.5 py-0.5 text-[10px] font-bold uppercase">
                  Primary Level
                </span>
                <Hospital className="w-5 h-5 text-blue-700" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Community Health Centers</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Initial clinical triage, emergency stabilization, general bed availability, and referral initiation into regional network.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3 shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-indigo-100 text-indigo-800 px-2.5 py-0.5 text-[10px] font-bold uppercase">
                  Secondary Level
                </span>
                <Building2 className="w-5 h-5 text-indigo-700" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">District General Hospitals</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Secondary acute care, surgical operations, intermediate ICUs, oxygen inventory surveillance, and district-wide ambulance intake.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3 shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-teal-100 text-teal-800 px-2.5 py-0.5 text-[10px] font-bold uppercase">
                  Tertiary Level
                </span>
                <ShieldCheck className="w-5 h-5 text-teal-700" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Medical Colleges & Institutes</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Multi-specialty critical care, advanced ventilator allocation, dedicated trauma centers, and inter-district patient transfers.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 space-y-3 shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-purple-100 text-purple-800 px-2.5 py-0.5 text-[10px] font-bold uppercase">
                  Apex Level
                </span>
                <Globe className="w-5 h-5 text-purple-700" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">National Specialty Centers</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Apex healthcare institutions with high-dependency capacity, national referral intake, and centralized health logistics monitoring.
              </p>
            </div>
          </div>

          {/* Clinical Security Notice Banner */}
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 text-xs text-blue-900 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <Lock className="w-5 h-5 text-blue-800 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-bold text-blue-950">
                  Protected Clinical Triage & Patient Privacy Safeguards
                </h4>
                <p className="text-blue-800 mt-0.5">
                  Direct patient lookups, AI eligibility triage, and bed reservations are strictly restricted to authenticated hospital medical staff. Clinical data is safeguarded with role-based access control and never exposed to unauthenticated public visitors.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5 shrink-0">
              <Link
                href="/portal/hospital/login"
                className="rounded-lg bg-blue-900 text-white px-3.5 py-2 font-bold hover:bg-blue-800 transition shadow-xs text-xs"
              >
                Hospital Staff Sign-In
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Section 4: Registration & Verification Pipeline */}
      <section id="registration" className="py-16 bg-slate-50 border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-12">
          <div className="text-center max-w-3xl mx-auto space-y-3">
            <span className="text-xs font-bold tracking-wider uppercase text-blue-800">
              National Accreditation Workflow
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Hospital Registration & Verification Pipeline
            </h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Every facility undergoes structured four-stage administrative screening before gaining network access.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-blue-900 font-bold text-xs">
                1
              </span>
              <h3 className="text-sm font-bold text-slate-900">Facility Profile & Capacity</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Submit bed counts, ICU resources, oxygen storage, ventilator inventory, and geo-coordinates.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-indigo-900 font-bold text-xs">
                2
              </span>
              <h3 className="text-sm font-bold text-slate-900">Nodal Officer 2FA Verification</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Two-factor email ownership verification confirming nodal authority credentials and contact identity.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-teal-100 text-teal-900 font-bold text-xs">
                3
              </span>
              <h3 className="text-sm font-bold text-slate-900">Compliance Document Audit</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Upload clinical establishment certificates, fire safety NOC, and bio-medical waste clearances.
              </p>
            </div>

            <div className="rounded-xl bg-white border border-slate-200 p-6 space-y-3 shadow-xs">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-purple-100 text-purple-900 font-bold text-xs">
                4
              </span>
              <h3 className="text-sm font-bold text-slate-900">Multi-Tier Review & Activation</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Sequential review by District, State, and Central reviewers followed by credential provisioning.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
            <Link
              href="/register"
              className="rounded-lg bg-blue-900 px-6 py-2.5 text-xs font-bold text-white hover:bg-blue-800 transition shadow-xs"
            >
              Start Facility Registration →
            </Link>
            <Link
              href="/application/track"
              className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-2xs"
            >
              Track Existing Application
            </Link>
          </div>
        </div>
      </section>

      {/* Section 5: Authorized Personnel Department Portals */}
      <section id="login" className="py-16 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-10">
          <div className="text-center max-w-2xl mx-auto space-y-2">
            <span className="text-xs font-bold tracking-wider uppercase text-blue-800">
              Administrative Access
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Sign In to Health Operations
            </h2>
            <p className="text-xs sm:text-sm text-slate-500">
              Access your designated facility or administrative jurisdiction dashboard through dedicated department portals with strict Role-Based Access Control.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Hospital Portal Card */}
            <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-6 flex flex-col justify-between shadow-2xs hover:border-blue-400 hover:shadow-xs transition group">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 text-blue-800 border border-blue-200">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-bold text-blue-800 border border-blue-200 uppercase tracking-wider">
                    Facility Tier
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 group-hover:text-blue-900 transition">
                  Hospital Operations
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Real-time bed allocation, ICU resources, triage recommendations, and patient referral processing.
                </p>
              </div>
              <div className="pt-5 mt-4 border-t border-blue-100">
                <Link
                  href="/portal/hospital/login"
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-blue-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-blue-800 transition shadow-2xs"
                >
                  <span>Hospital Login</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* District Portal Card */}
            <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-6 flex flex-col justify-between shadow-2xs hover:border-indigo-400 hover:shadow-xs transition group">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-100 text-indigo-800 border border-indigo-200">
                    <MapPin className="w-5 h-5" />
                  </div>
                  <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-bold text-indigo-800 border border-indigo-200 uppercase tracking-wider">
                    District Tier
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-900 transition">
                  District Administration
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  District-level hospital monitoring, Stage-1 accreditation dossier review, and jurisdictional oversight.
                </p>
              </div>
              <div className="pt-5 mt-4 border-t border-indigo-100">
                <Link
                  href="/portal/district/login"
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-indigo-800 transition shadow-2xs"
                >
                  <span>District Login</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* State Portal Card */}
            <div className="rounded-xl border border-teal-200 bg-teal-50/40 p-6 flex flex-col justify-between shadow-2xs hover:border-teal-400 hover:shadow-xs transition group">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-100 text-teal-800 border border-teal-200">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <span className="rounded-full bg-teal-100 px-2.5 py-0.5 text-[10px] font-bold text-teal-800 border border-teal-200 uppercase tracking-wider">
                    State Tier
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 group-hover:text-teal-900 transition">
                  State Directorate
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  State-wide capacity monitoring, Stage-2 secondary verification, and regional healthcare coordination.
                </p>
              </div>
              <div className="pt-5 mt-4 border-t border-teal-100">
                <Link
                  href="/portal/state/login"
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-teal-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-teal-800 transition shadow-2xs"
                >
                  <span>State Login</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* Central Portal Card */}
            <div className="rounded-xl border border-purple-200 bg-purple-50/40 p-6 flex flex-col justify-between shadow-2xs hover:border-purple-400 hover:shadow-xs transition group">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-100 text-purple-800 border border-purple-200">
                    <Globe className="w-5 h-5" />
                  </div>
                  <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-[10px] font-bold text-purple-800 border border-purple-200 uppercase tracking-wider">
                    National Tier
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 group-hover:text-purple-900 transition">
                  Central Health Command
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  National aggregate health surveillance, Final Stage-3 accreditation sign-off, and telemetry analytics.
                </p>
              </div>
              <div className="pt-5 mt-4 border-t border-purple-100">
                <Link
                  href="/portal/central/login"
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-purple-900 px-4 py-2.5 text-xs font-bold text-white hover:bg-purple-800 transition shadow-2xs"
                >
                  <span>Central Login</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-5 rounded-xl border border-slate-200 bg-slate-50 text-xs text-slate-600">
            <div className="flex items-start gap-2.5">
              <Shield className="w-4 h-4 text-blue-700 shrink-0 mt-0.5" />
              <span>
                <strong>Role Mismatch Protection:</strong> To ensure jurisdictional integrity, each department portal strictly accepts only authorized tier credentials.
              </span>
            </div>
            <Link
              href="/portal"
              className="shrink-0 font-bold text-blue-900 hover:underline flex items-center gap-1"
            >
              <span>Explore All Department Portals</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </section>

      {/* Section 6: Help, Contact & Support */}
      <section id="contact" className="py-16 bg-slate-50 border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="rounded-2xl bg-blue-900 text-white p-8 sm:p-12 shadow-sm relative overflow-hidden">
            <div className="relative z-10 max-w-3xl space-y-4">
              <span className="rounded-full bg-blue-800 border border-blue-700 px-3 py-1 text-xs font-bold text-blue-200 uppercase tracking-wider">
                Support & Emergency Information
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                24/7 National Emergency & Technical Helpdesk
              </h2>
              <p className="text-sm text-blue-100 leading-relaxed">
                For administrative onboarding assistance, technical integration inquiries, or hospital coordination, reach out through the verified support channels.
              </p>
              <div className="pt-2 flex flex-wrap items-center gap-4 text-xs font-semibold">
                <div className="flex items-center gap-2 bg-blue-800/80 px-4 py-2.5 rounded-lg border border-blue-700">
                  <PhoneCall className="w-4 h-4 text-emerald-400" />
                  <span>Ambulance Emergency: 108 (Participating States/UTs)</span>
                </div>
                <div className="flex items-center gap-2 bg-blue-800/80 px-4 py-2.5 rounded-lg border border-blue-700">
                  <PhoneCall className="w-4 h-4 text-sky-400" />
                  <span>National Health Helpline: 1075 (Toll-Free, MoHFW)</span>
                </div>
                <Link
                  href="/portal"
                  className="rounded-lg bg-white text-blue-950 px-5 py-2.5 font-bold hover:bg-blue-50 transition"
                >
                  Access Department Portals →
                </Link>
              </div>
              <p className="pt-2 text-[11px] text-blue-200/80">
                Note: 108 and 1075 are official public telephone emergency services. SIH Hospital AI is an independent Smart India Hackathon technical prototype and reference platform.
              </p>
            </div>
          </div>
        </div>
      </section>

      <GovernmentFooter />
    </div>
  );
}
