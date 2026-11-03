import React from "react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: string | React.ReactNode;
  variant?: "default" | "primary" | "success" | "warning" | "danger" | "purple";
  badge?: string;
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  variant = "default",
  badge,
  className = "",
}) => {
  const variantStyles = {
    default: "border-slate-800 bg-slate-900/90 text-white",
    primary: "border-blue-500/20 bg-blue-950/20 text-blue-100",
    success: "border-emerald-500/20 bg-emerald-950/20 text-emerald-100",
    warning: "border-amber-500/20 bg-amber-950/20 text-amber-100",
    danger: "border-rose-500/20 bg-rose-950/20 text-rose-100",
    purple: "border-purple-500/20 bg-purple-950/20 text-purple-100",
  }[variant];

  const valueColors = {
    default: "text-white",
    primary: "text-blue-400",
    success: "text-emerald-400",
    warning: "text-amber-400",
    danger: "text-rose-400",
    purple: "text-purple-400",
  }[variant];

  return (
    <div
      className={`rounded-xl border p-5 shadow-sm transition hover:border-slate-700 ${variantStyles} ${className}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {title}
        </p>
        {icon && (
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800/80 text-sm">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <p className={`text-2xl font-bold tracking-tight sm:text-3xl ${valueColors}`}>
          {value}
        </p>
        {badge && (
          <span className="rounded-md bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-300">
            {badge}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-1.5 text-xs text-slate-400 line-clamp-1">{subtitle}</p>
      )}
    </div>
  );
};
