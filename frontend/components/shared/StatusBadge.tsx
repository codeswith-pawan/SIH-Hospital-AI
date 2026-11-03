import React from "react";
import { ReferralStatus } from "@/lib/types";
import { REFERRAL_STATUS_MAP, getPriorityStyles } from "@/lib/formatters";

interface StatusBadgeProps {
  status: ReferralStatus | string;
  size?: "sm" | "md";
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = "md",
}) => {
  const normStatus = (status || "").toUpperCase() as ReferralStatus;
  const info = REFERRAL_STATUS_MAP[normStatus] || {
    label: status,
    badge: "bg-slate-700/30 text-slate-300 border-slate-600/30",
    icon: "•",
  };

  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${info.badge} ${sizeClasses} whitespace-nowrap`}
    >
      <span className="text-[10px]">{info.icon}</span>
      <span>{info.label}</span>
    </span>
  );
};

interface PriorityBadgeProps {
  priority: string;
  size?: "sm" | "md";
}

export const PriorityBadge: React.FC<PriorityBadgeProps> = ({
  priority,
  size = "md",
}) => {
  const styles = getPriorityStyles(priority);
  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold rounded-full ${styles.badge} ${sizeClasses} whitespace-nowrap`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${styles.dot}`} />
      <span>{priority || "Stable"}</span>
    </span>
  );
};
