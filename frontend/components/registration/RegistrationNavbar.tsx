"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export const RegistrationNavbar: React.FC = () => {
  const pathname = usePathname();

  const navLinks = [
    { href: "/register", label: "Registration Hub" },
    { href: "/application/track", label: "Track Application" },
    { href: "/application/status", label: "Applicant Portal" },
    { href: "/reviewer", label: "Reviewer Portal" },
  ];

  return (
    <header className="border-b border-slate-800/80 bg-slate-900/90 backdrop-blur sticky top-0 z-30">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 py-3.5">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/30 text-xl shadow-inner group-hover:border-blue-400 transition">
            🏥
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-white group-hover:text-blue-300 transition">
                SIH Hospital AI
              </span>
              <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-400 border border-blue-500/20">
                Gov Portal
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              National Facility Registration & Administrative Onboarding
            </p>
          </div>
        </Link>

        {/* Center / Right Navigation Links */}
        <div className="flex items-center gap-2 sm:gap-4">
          <nav className="flex items-center gap-1 sm:gap-2">
            {navLinks.map((link) => {
              const isActive = pathname === link.href || (link.href !== "/register" && pathname.startsWith(link.href));
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-lg px-2.5 sm:px-3 py-1.5 text-xs font-medium transition ${
                    isActive
                      ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                      : "text-slate-400 hover:text-white hover:bg-slate-800/60"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>

          <div className="hidden md:block h-4 w-px bg-slate-800" />

          <Link
            href="/portal"
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition"
          >
            <span>🔐 Department Portals</span>
          </Link>
        </div>
      </div>
    </header>
  );
};
