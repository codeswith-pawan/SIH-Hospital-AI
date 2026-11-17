"use client";

import React from "react";
import { MapPin } from "lucide-react";
import { DepartmentLoginPage } from "@/components/auth/DepartmentLoginPage";

export default function DistrictLoginPage() {
  return (
    <DepartmentLoginPage
      department="district"
      title="District Health Authority Login"
      subtitle="Sign in with your district health office credentials to monitor network facilities, review accreditation applications, and oversee local bed capacity."
      tier="District Tier • Administrative Access"
      expectedRole="DISTRICT_ADMIN"
      icon={MapPin}
      accentColor={{
        bg: "bg-indigo-600",
        text: "text-indigo-700",
        border: "border-indigo-200",
        button: "bg-indigo-900 hover:bg-indigo-800",
        lightBg: "bg-indigo-50",
      }}
    />
  );
}
