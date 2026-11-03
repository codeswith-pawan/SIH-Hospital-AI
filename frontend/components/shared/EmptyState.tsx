import React from "react";

interface EmptyStateProps {
  icon?: string | React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = "📋",
  title,
  description,
  action,
  className = "",
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center sm:p-12 ${className}`}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800 text-2xl shadow-inner">
        {icon}
      </div>
      <h3 className="mt-4 text-base font-semibold text-slate-200">{title}</h3>
      {description && (
        <p className="mx-auto mt-1 max-w-sm text-xs text-slate-400 sm:text-sm">
          {description}
        </p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};
