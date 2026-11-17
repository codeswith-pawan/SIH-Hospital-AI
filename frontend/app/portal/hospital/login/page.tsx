"use client";

import React from "react";
import { Building2 } from "lucide-react";
import { DepartmentLoginPage } from "@/components/auth/DepartmentLoginPage";

export default function HospitalLoginPage() {
  return (
    <DepartmentLoginPage
      department="hospital"
      title="Hospital Operations Login"
      subtitle="Sign in with your hospital staff or medical superintendent credentials to manage emergency bed allocation, ICU inventory, and clinical referrals."
      tier="Facility Tier • Restricted Access"
      expectedRole="HOSPITAL"
      icon={Building2}
      accentColor={{
        bg: "bg-blue-600",
        text: "text-blue-700",
        border: "border-blue-200",
        button: "bg-blue-900 hover:bg-blue-800",
        lightBg: "bg-blue-50",
      }}
    />
  );
}
