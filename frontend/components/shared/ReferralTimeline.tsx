import React from "react";
import { Referral } from "@/lib/types";
import { formatDateTime, LIFECYCLE_STAGES, REFERRAL_STATUS_MAP } from "@/lib/formatters";

interface ReferralTimelineProps {
  referral: Referral;
}

export const ReferralTimeline: React.FC<ReferralTimelineProps> = ({
  referral,
}) => {
  const statusKey = (referral.status || "PENDING").toUpperCase();
  const statusInfo = REFERRAL_STATUS_MAP[statusKey as keyof typeof REFERRAL_STATUS_MAP] || {
    label: referral.status,
    badge: "bg-slate-700/30 text-slate-300",
    stageIndex: -1,
  };

  const isTerminalNegative = ["REJECTED", "DIED", "TRANSFERRED", "CLOSED"].includes(statusKey);
  const currentStageIndex = statusInfo.stageIndex;

  // Discrete historical events with recorded timestamps
  const chronologicalEvents = [
    {
      title: "Referral Created",
      timestamp: referral.created_at,
      description: `Initiated by Hospital ${referral.from_hospital_id}${
        referral.from_hospital_name ? ` (${referral.from_hospital_name})` : ""
      } for Priority ${referral.priority}`,
      meta: referral.bed_type ? `Requested: ${referral.bed_type} Bed` : undefined,
    },
    {
      title: "Referral Accepted",
      timestamp: referral.accepted_at,
      description: `Accepted by Destination Hospital ${referral.to_hospital_id}${
        referral.to_hospital_name ? ` (${referral.to_hospital_name})` : ""
      }`,
      meta: referral.bed_number
        ? `Allocated Bed #${referral.bed_number} (${referral.bed_type || "ICU"})`
        : referral.bed_id
        ? `Bed ID: ${referral.bed_id}`
        : "Bed automatically reserved in inventory",
    },
    {
      title: "Ambulance Dispatched / In Transit",
      timestamp: referral.dispatched_at || referral.in_transit_at,
      description: referral.ambulance_id
        ? `Vehicle ID: ${referral.ambulance_id}${referral.eta_minutes ? ` • ETA: ~${referral.eta_minutes} mins` : ""}`
        : "Patient in transit under active monitoring",
      meta: referral.notes ? `En-route Notes: ${referral.notes}` : undefined,
    },
    {
      title: "Patient Arrived at Destination",
      timestamp: referral.arrived_at,
      description: "Patient safely received at emergency/intake triage",
    },
    {
      title: "Treatment Commenced",
      timestamp: referral.treatment_started_at,
      description: "Patient admitted to clinical unit; active intervention underway",
    },
    {
      title: "Referral Completed",
      timestamp: referral.completed_at,
      description: "Treatment finished or discharge completed. Bed released back to inventory.",
    },
    {
      title: "Referral Rejected",
      timestamp: referral.rejected_at,
      description: referral.rejection_reason || referral.notes || "Declined by receiving facility due to clinical or capacity constraints.",
      isNegative: true,
    },
    {
      title: "Patient Deceased",
      timestamp: referral.died_at,
      description: "Clinical demise recorded. Bed released.",
      isNegative: true,
    },
    {
      title: "Transferred to Higher Center",
      timestamp: referral.transferred_at,
      description: "Patient escalated to quaternary/specialized care facility.",
    },
    {
      title: "Referral Closed",
      timestamp: referral.closed_at,
      description: "Administrative closure confirmed.",
    },
  ].filter((e) => Boolean(e.timestamp));

  return (
    <div className="space-y-6 rounded-xl border border-slate-800 bg-slate-950 p-5">
      {/* Header Info */}
      <div className="flex flex-col justify-between gap-2 border-b border-slate-800/80 pb-4 sm:flex-row sm:items-center">
        <div>
          <h4 className="text-sm font-semibold text-white">
            Referral Lifecycle Tracking
          </h4>
          <p className="mt-0.5 text-xs text-slate-400">
            Case: <span className="font-mono text-slate-300">{referral.referral_id}</span> • Patient:{" "}
            <span className="font-mono text-slate-300">{referral.patient_id}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Current Phase:</span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold border ${
              isTerminalNegative
                ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
                : "border-blue-500/30 bg-blue-500/10 text-blue-400"
            }`}
          >
            {statusInfo.label}
          </span>
        </div>
      </div>

      {/* Linear Lifecycle Step Progress Bar */}
      {!isTerminalNegative && (
        <div className="py-2">
          <div className="grid grid-cols-6 gap-1 sm:gap-2">
            {LIFECYCLE_STAGES.map((stage, idx) => {
              const isPassed = currentStageIndex > idx;
              const isCurrent = currentStageIndex === idx;

              return (
                <div key={stage.key} className="flex flex-col items-center text-center">
                  <div
                    className={`h-2 w-full rounded-full transition-all ${
                      isPassed
                        ? "bg-emerald-500"
                        : isCurrent
                        ? "bg-blue-500 ring-2 ring-blue-500/30"
                        : "bg-slate-800"
                    }`}
                  />
                  <span
                    className={`mt-2 text-[10px] font-medium sm:text-xs truncate max-w-full ${
                      isPassed
                        ? "text-emerald-400 font-semibold"
                        : isCurrent
                        ? "text-blue-400 font-bold"
                        : "text-slate-500"
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Terminal Callout for Rejected/Died/Transferred */}
      {isTerminalNegative && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300">
          <p className="font-semibold text-rose-200">
            Lifecycle Halted: {statusInfo.label}
          </p>
          <p className="mt-1 text-slate-300">
            {referral.rejection_reason ||
              referral.notes ||
              "This referral entered a terminal non-admission state."}
          </p>
        </div>
      )}

      {/* Vertical Detailed Event Log */}
      <div className="relative border-l border-slate-800 pl-4 space-y-4">
        {chronologicalEvents.map((evt, i) => (
          <div key={i} className="relative">
            {/* Circle Node */}
            <div
              className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-slate-950 ${
                evt.isNegative
                  ? "bg-rose-500"
                  : i === chronologicalEvents.length - 1
                  ? "bg-blue-400 animate-pulse"
                  : "bg-emerald-400"
              }`}
            />
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
              <p className="text-xs font-semibold text-slate-200">{evt.title}</p>
              <p className="text-[11px] font-mono text-slate-400">
                {formatDateTime(evt.timestamp)}
              </p>
            </div>
            <p className="mt-0.5 text-xs text-slate-400">{evt.description}</p>
            {evt.meta && (
              <p className="mt-1 inline-block rounded bg-slate-900 px-2 py-0.5 text-[11px] text-blue-300 border border-slate-800">
                {evt.meta}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
