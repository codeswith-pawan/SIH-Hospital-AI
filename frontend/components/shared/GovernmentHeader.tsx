"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Menu,
  X,
  PhoneCall,
  LogIn,
  FileCheck2,
  Hospital,
} from "lucide-react";
import { getStoredUser, clearStoredSession } from "@/lib/api";
import { User } from "@/lib/types";

export const GovernmentHeader: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [user, setUser] = useState<User | null>(() => getStoredUser());

  const handleSignOut = () => {
    clearStoredSession();
    setUser(null);
    router.push("/portal");
  };

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/#about", label: "About Us" },
    { href: "/#services", label: "Services" },
    { href: "/#network", label: "Hospital Network" },
    { href: "/register", label: "Hospital Registration" },
    { href: "/application/track", label: "Track Application" },
    { href: "/#contact", label: "Help & Contact" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-slate-200 shadow-xs">
      {/* Top Government Tricolor Bar */}
      <div className="h-1 w-full bg-gradient-to-r from-amber-500 via-white to-emerald-600" />

      {/* Official Top Bar */}
      <div className="bg-slate-900 text-slate-200 text-[11px] py-1.5 px-4 sm:px-6 border-b border-slate-800">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white tracking-wide">
              SMART INDIA HACKATHON INITIATIVE
            </span>
            <span className="text-slate-400 hidden sm:inline">•</span>
            <span className="text-slate-300 hidden sm:inline">
              Hospital Management & Coordination Platform
            </span>
            <span className="text-slate-400 hidden md:inline">•</span>
            <span className="text-amber-400 hidden md:inline font-medium">
              National Reference System
            </span>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <div className="flex items-center gap-1.5 text-slate-300">
              <PhoneCall className="w-3 h-3 text-emerald-400" />
              <span>National Helplines: <strong>108</strong> (Ambulance) | <strong>1075</strong> (Health Inquiries)</span>
            </div>
            <div className="hidden sm:flex items-center gap-1 border-l border-slate-700 pl-3">
              <span className="text-white font-medium">English</span>
              <span className="text-slate-400">|</span>
              <span className="text-slate-400 hover:text-white cursor-pointer">हिन्दी</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Navigation Bar */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16 sm:h-20">
          {/* Logo & Portal Identity */}
          <Link href="/" className="flex items-center gap-3 sm:gap-3.5 group">
            <div className="flex h-11 w-11 sm:h-12 sm:w-12 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm border border-slate-800 group-hover:bg-blue-900 transition">
              <Hospital className="w-6 h-6 text-sky-400" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className="text-lg sm:text-xl font-extrabold tracking-tight text-slate-900 group-hover:text-blue-900 transition">
                  SIH Hospital AI
                </span>
                <span className="rounded bg-sky-100 text-sky-800 border border-sky-300 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                  Healthcare Portal
                </span>
              </div>
              <span className="text-[11px] sm:text-xs text-slate-500 font-medium tracking-tight">
                National Hospital Management & Healthcare Coordination Platform
              </span>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden lg:flex items-center gap-1 xl:gap-2">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    isActive
                      ? "text-blue-900 bg-blue-50 font-bold"
                      : "text-slate-700 hover:text-blue-900 hover:bg-slate-100"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>

          {/* Action CTAs */}
          <div className="hidden sm:flex items-center gap-2.5">
            {user ? (
              <div className="flex items-center gap-2.5">
                <span className="text-xs font-medium text-slate-600">
                  Signed in as <strong className="text-slate-900">{user.username}</strong>
                </span>
                <Link
                  href="/"
                  className="rounded-lg bg-blue-900 text-white px-3.5 py-2 text-xs font-semibold hover:bg-blue-800 transition shadow-xs"
                >
                  My Dashboard
                </Link>
                <button
                  onClick={handleSignOut}
                  className="rounded-lg border border-slate-300 text-slate-700 px-3 py-2 text-xs font-semibold hover:bg-slate-100 transition"
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <>
                <Link
                  href="/portal"
                  className="rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:text-blue-900 transition flex items-center gap-1.5 shadow-xs"
                >
                  <LogIn className="w-3.5 h-3.5 text-slate-600" />
                  <span>Department Login</span>
                </Link>
                <Link
                  href="/portal"
                  className="rounded-lg bg-blue-900 px-4 py-2 text-xs font-bold text-white hover:bg-blue-800 transition shadow-xs flex items-center gap-1.5"
                >
                  <span>Explore Portal</span>
                  <span>→</span>
                </Link>
              </>
            )}
          </div>

          {/* Mobile Menu Trigger */}
          <div className="lg:hidden flex items-center gap-2">
            <Link
              href="/portal"
              className="rounded-lg bg-blue-900 text-white px-3 py-1.5 text-xs font-bold hover:bg-blue-800 transition"
            >
              Explore Portal
            </Link>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-lg border border-slate-300 p-2 text-slate-700 hover:bg-slate-100"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-t border-slate-200 bg-white px-4 pt-3 pb-6 space-y-3">
          <div className="flex flex-col space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-blue-900"
              >
                {link.label}
              </Link>
            ))}
          </div>

          <div className="pt-3 border-t border-slate-200 space-y-2">
            <Link
              href="/portal"
              onClick={() => setMobileMenuOpen(false)}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-900 text-white py-2.5 text-xs font-bold shadow-xs"
            >
              <LogIn className="w-4 h-4" />
              <span>Department Portal & Login</span>
            </Link>
            <Link
              href="/register"
              onClick={() => setMobileMenuOpen(false)}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-slate-50 text-slate-700 py-2.5 text-xs font-semibold"
            >
              <FileCheck2 className="w-4 h-4" />
              <span>Register Facility</span>
            </Link>
          </div>
        </div>
      )}
    </header>
  );
};
