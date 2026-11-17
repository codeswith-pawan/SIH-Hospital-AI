"use client";

import React from "react";
import { ShieldCheck } from "lucide-react";
import { DepartmentLoginPage } from "@/components/auth/DepartmentLoginPage";

export default function StateLoginPage() {
  return (
    <DepartmentLoginPage
      department="state"
      title="State Health Directorate Login"
      subtitle="Sign in with your state health directorate credentials to manage inter-district transfer logistics, review escalated applications, and view state-wide healthcare metrics."
      tier="State Tier • Directorate Access"
      expectedRole="STATE_ADMIN"
      icon={ShieldCheck}
      accentColor={{
        bg: "bg-teal-600",
        text: "text-teal-700",
        border: "border-teal-200",
        button: "bg-teal-900 hover:bg-teal-800",
        lightBg: "bg-teal-50",
      }}
    />
  );
}
