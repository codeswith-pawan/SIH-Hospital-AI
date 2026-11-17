import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
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
  const [categoryFilter, setCategoryFilter] = useState<"ALL" | "REFERRAL" | "BED" | "CAPACITY">("ALL");
  const [displayLimit, setDisplayLimit] = useState(15);
  const panelRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const getCategoryBadge = (eventType: string) => {
    const ev = (eventType || "").toUpperCase();
    if (ev.includes("REFERRAL")) {
      return { label: "Referral", color: "bg-blue-500/10 text-blue-400 border-blue-500/20" };
    }
    if (ev.includes("BED") || ev.includes("RESERVATION") || ev.includes("PATIENT")) {
      return { label: "Bed Hold", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" };
    }
    if (ev.includes("AVAILABILITY") || ev.includes("CAPACITY")) {
      return { label: "Capacity", color: "bg-amber-500/10 text-amber-400 border-amber-500/20" };
    }
    if (ev.includes("REGISTRATION") || ev.includes("REVIEW") || ev.includes("CORRECTION")) {
      return { label: "Review", color: "bg-purple-500/10 text-purple-400 border-purple-500/20" };
    }
    return { label: "General", color: "bg-slate-500/10 text-slate-400 border-slate-500/20" };
  };

  const getRelativeTime = (dateStr: string) => {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays < 7) return `${diffDays}d ago`;
      return formatDateTime(dateStr);
    } catch {
      return dateStr;
    }
  };

  const handleNotificationClick = (n: NotificationItem) => {
    const notifId = n.notification_id || String(n.id || "");
    if (!n.is_read && notifId) {
      onMarkRead(notifId);
    }
    if (n.action_url) {
      setIsOpen(false);
      router.push(n.action_url);
    }
  };

  const filteredNotifications = notifications.filter((n) => {
    if (categoryFilter === "ALL") return true;
    const ev = (n.event_type || "").toUpperCase();
    if (categoryFilter === "REFERRAL") return ev.includes("REFERRAL");
    if (categoryFilter === "BED") return ev.includes("BED") || ev.includes("RESERVATION") || ev.includes("PATIENT");
    if (categoryFilter === "CAPACITY") return ev.includes("AVAILABILITY") || ev.includes("CAPACITY");
    return true;
  });

  const visibleNotifications = filteredNotifications.slice(0, displayLimit);

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

          {/* Category Filter Pills */}
          <div className="flex items-center gap-1.5 mt-2.5 pb-2 border-b border-slate-800/60 overflow-x-auto text-[10px]">
            {(
              [
                { id: "ALL", label: "All" },
                { id: "REFERRAL", label: "Referrals" },
                { id: "BED", label: "Bed Holds" },
                { id: "CAPACITY", label: "Capacity" },
              ] as const
            ).map((cat) => (
              <button
                key={cat.id}
                onClick={() => {
                  setCategoryFilter(cat.id);
                  setDisplayLimit(15);
                }}
                className={`rounded-full px-2.5 py-0.5 font-medium transition ${
                  categoryFilter === cat.id
                    ? "bg-blue-600 text-white shadow-sm"
                    : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <div className="mt-2.5 max-h-80 overflow-y-auto space-y-2 pr-1 divide-y divide-slate-800/40">
            {loading && visibleNotifications.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 animate-pulse">
                Fetching notifications...
              </div>
            ) : visibleNotifications.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No active {categoryFilter !== "ALL" ? categoryFilter.toLowerCase() : ""} notifications.
              </div>
            ) : (
              visibleNotifications.map((n, index) => {
                const badge = getCategoryBadge(n.event_type);
                const notifId = n.notification_id || String(n.id || "");
                return (
                  <div
                    key={notifId || `notif-${index}`}
                    onClick={() => handleNotificationClick(n)}
                    className={`pt-2.5 first:pt-0 cursor-pointer rounded-lg p-2 transition group ${
                      n.is_read
                        ? "opacity-60 hover:opacity-100 hover:bg-slate-800/40"
                        : "bg-blue-950/20 border-l-2 border-blue-500 hover:bg-blue-950/30"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className={`inline-block rounded px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wider border ${badge.color}`}>
                          {badge.label}
                        </span>
                        <p className="text-xs font-semibold text-slate-200 truncate group-hover:text-blue-300 transition">
                          {n.title}
                        </p>
                      </div>
                      <span className="text-[10px] text-slate-400 whitespace-nowrap shrink-0">
                        {getRelativeTime(n.created_at)}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 line-clamp-2">
                      {n.message}
                    </p>
                    {n.action_url && (
                      <div className="mt-1 flex items-center gap-1 text-[10px] text-blue-400 font-medium">
                        <span>View action</span>
                        <span>→</span>
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {filteredNotifications.length > displayLimit && (
              <div className="pt-2 text-center">
                <button
                  onClick={() => setDisplayLimit((prev) => prev + 15)}
                  className="text-[11px] font-medium text-blue-400 hover:text-blue-300 transition py-1"
                >
                  Load more ({filteredNotifications.length - displayLimit} remaining)
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
