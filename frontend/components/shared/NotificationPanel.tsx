import React, { useState, useRef, useEffect } from "react";
import { NotificationItem } from "@/lib/types";
import { formatDateTime } from "@/lib/formatters";

interface NotificationPanelProps {
  notifications: NotificationItem[];
  unreadCount: number;
  loading: boolean;
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
  onRefresh: () => void;
}

export const NotificationPanel: React.FC<NotificationPanelProps> = ({
  notifications,
  unreadCount,
  loading,
  onMarkRead,
  onMarkAllRead,
  onRefresh,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex items-center justify-center rounded-xl border border-slate-700 bg-slate-800 p-2 text-slate-300 hover:bg-slate-700 hover:text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        title="Notification Center"
        aria-label="Toggle notifications"
      >
        <span className="text-base">🔔</span>
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white shadow-sm ring-2 ring-slate-900">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-2xl z-50 animate-fade-in">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                Operational Alerts
              </h4>
              {unreadCount > 0 && (
                <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-400">
                  {unreadCount} unread
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={onRefresh}
                disabled={loading}
                className="text-[11px] text-slate-400 hover:text-slate-200 transition disabled:opacity-50"
                title="Refresh notifications"
              >
                🔄
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={onMarkAllRead}
                  className="text-[11px] font-medium text-blue-400 hover:text-blue-300 transition"
                >
                  Mark all read
                </button>
              )}
            </div>
          </div>

          <div className="mt-3 max-h-80 overflow-y-auto space-y-2.5 pr-1 divide-y divide-slate-800/40">
            {notifications.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No active notifications or alerts.
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.notification_id}
                  onClick={() => !n.is_read && onMarkRead(n.notification_id)}
                  className={`pt-2.5 first:pt-0 cursor-pointer rounded-lg p-2 transition ${
                    n.is_read
                      ? "opacity-60 hover:opacity-100 hover:bg-slate-800/40"
                      : "bg-blue-950/20 border-l-2 border-blue-500 hover:bg-blue-950/30"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <p className="text-xs font-semibold text-slate-200 line-clamp-1">
                      {n.title}
                    </p>
                    <span className="text-[10px] text-slate-400 whitespace-nowrap">
                      {formatDateTime(n.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400 line-clamp-2">
                    {n.message}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
