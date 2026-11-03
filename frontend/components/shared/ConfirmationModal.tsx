import React, { useEffect } from "react";

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "primary" | "danger" | "success";
  loading?: boolean;
  children?: React.ReactNode;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "primary",
  loading = false,
  children,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !loading) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, loading, onClose]);

  if (!isOpen) return null;

  const confirmBtnStyles = {
    primary: "bg-blue-600 hover:bg-blue-500 focus:ring-blue-500",
    danger: "bg-rose-600 hover:bg-rose-500 focus:ring-rose-500",
    success: "bg-emerald-600 hover:bg-emerald-500 focus:ring-emerald-500",
  }[variant];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl transition-all">
        <div className="flex items-start justify-between">
          <h3
            id="modal-title"
            className="text-lg font-bold text-white tracking-tight"
          >
            {title}
          </h3>
          <button
            onClick={onClose}
            disabled={loading}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition disabled:opacity-50"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {description && (
          <p className="mt-2 text-xs text-slate-400 leading-relaxed">
            {description}
          </p>
        )}

        {children && <div className="mt-4">{children}</div>}

        <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition disabled:opacity-50"
          >
            {cancelLabel}
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-xl px-5 py-2 text-xs font-semibold text-white transition focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50 flex items-center gap-2 ${confirmBtnStyles}`}
          >
            {loading && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            <span>{loading ? "Processing..." : confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
