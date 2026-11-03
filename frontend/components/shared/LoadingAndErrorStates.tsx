import React from "react";

interface LoadingStateProps {
  message?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = "Loading verified clinical records...",
  size = "md",
  className = "",
}) => {
  const spinnerSize = {
    sm: "h-5 w-5 border-2",
    md: "h-8 w-8 border-2",
    lg: "h-12 w-12 border-3",
  }[size];

  return (
    <div
      className={`flex flex-col items-center justify-center p-8 text-center ${className}`}
      role="status"
      aria-live="polite"
    >
      <div
        className={`animate-spin rounded-full border-blue-500 border-t-transparent ${spinnerSize}`}
      />
      {message && (
        <p className="mt-3 text-xs font-medium text-slate-400 sm:text-sm">
          {message}
        </p>
      )}
    </div>
  );
};

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Operational Notice",
  message,
  onRetry,
  className = "",
}) => {
  return (
    <div
      className={`rounded-xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-300 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <span className="text-lg">⚠️</span>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-rose-200">{title}</h4>
          <p className="mt-1 text-xs text-rose-300/90 leading-relaxed">
            {message}
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/20 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-500/30"
            >
              Retry Action
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
