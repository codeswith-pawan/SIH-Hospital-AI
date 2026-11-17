"use client";

import React from "react";
import { Globe } from "lucide-react";
import { DepartmentLoginPage } from "@/components/auth/DepartmentLoginPage";

export default function CentralLoginPage() {
  return (
    <DepartmentLoginPage
      department="central"
      title="Central Health Command Login"
      subtitle="Sign in with your national healthcare administration credentials to access apex hospital approvals, nationwide capacity analytics, and system-wide monitoring."
      tier="National Tier • Apex Governance Access"
      expectedRole="CENTRAL_ADMIN"
      icon={Globe}
      accentColor={{
        bg: "bg-purple-600",
        text: "text-purple-700",
        border: "border-purple-200",
        button: "bg-purple-900 hover:bg-purple-800",
        lightBg: "bg-purple-50",
      }}
    />
  );
}
