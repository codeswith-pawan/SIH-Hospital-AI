import React, { useState, useMemo } from "react";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingAndErrorStates";

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T, index: number) => React.ReactNode;
  align?: "left" | "center" | "right";
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  searchPlaceholder?: string;
  searchFilterKeys?: (keyof T | string)[];
  statusFilterOptions?: { label: string; value: string }[];
  statusFilterKey?: keyof T | string;
  pageSize?: number;
  headerAction?: React.ReactNode;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  keyExtractor,
  loading = false,
  emptyTitle = "No records found",
  emptyDescription = "There are no entries matching your current filters.",
  searchPlaceholder,
  searchFilterKeys,
  statusFilterOptions,
  statusFilterKey,
  pageSize = 10,
  headerAction,
}: DataTableProps<T>) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [currentPage, setCurrentPage] = useState(1);

  // Filter Data
  const filteredData = useMemo(() => {
    let result = data;

    if (selectedStatus !== "ALL" && statusFilterKey) {
      result = result.filter(
        (item) => String(item[statusFilterKey]).toUpperCase() === selectedStatus.toUpperCase()
      );
    }

    if (searchTerm.trim() && searchFilterKeys && searchFilterKeys.length > 0) {
      const term = searchTerm.toLowerCase();
      result = result.filter((item) =>
        searchFilterKeys.some((k) => {
          const val = item[k];
          return val !== undefined && val !== null && String(val).toLowerCase().includes(term);
        })
      );
    }

    return result;
  }, [data, selectedStatus, statusFilterKey, searchTerm, searchFilterKeys]);

  // Pagination
  const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredData.slice(start, start + pageSize);
  }, [filteredData, currentPage, pageSize]);

  return (
    <div className="space-y-4">
      {/* Search and Filters Toolbar */}
      {(searchPlaceholder || statusFilterOptions || headerAction) && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 flex-wrap items-center gap-2.5">
            {searchPlaceholder && (
              <div className="relative min-w-[240px] flex-1 sm:max-w-xs">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500 text-xs">
                  🔍
                </span>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setCurrentPage(1);
                  }}
                  placeholder={searchPlaceholder}
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 py-2 pl-8 pr-3 text-xs text-white placeholder-slate-500 outline-none transition focus:border-blue-500"
                />
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm("")}
                    className="absolute inset-y-0 right-0 pr-3 text-xs text-slate-500 hover:text-white"
                  >
                    ✕
                  </button>
                )}
              </div>
            )}

            {statusFilterOptions && statusFilterOptions.length > 0 && (
              <select
                value={selectedStatus}
                onChange={(e) => {
                  setSelectedStatus(e.target.value);
                  setCurrentPage(1);
                }}
                className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-300 outline-none focus:border-blue-500"
              >
                <option value="ALL">All Statuses ({data.length})</option>
                {statusFilterOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          {headerAction && <div>{headerAction}</div>}
        </div>
      )}

      {/* Table Container */}
      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-sm">
        {loading ? (
          <LoadingState message="Fetching live records..." />
        ) : filteredData.length === 0 ? (
          <EmptyState title={emptyTitle} description={emptyDescription} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/70 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={`px-4 py-3.5 ${
                        col.align === "center"
                          ? "text-center"
                          : col.align === "right"
                          ? "text-right"
                          : "text-left"
                      } ${col.className || ""}`}
                    >
                      {col.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs">
                {paginatedData.map((item, idx) => (
                  <tr
                    key={keyExtractor(item)}
                    className="transition hover:bg-slate-800/40"
                  >
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={`px-4 py-3.5 align-middle ${
                          col.align === "center"
                            ? "text-center"
                            : col.align === "right"
                            ? "text-right"
                            : "text-left"
                        } ${col.className || ""}`}
                      >
                        {col.render
                          ? col.render(item, idx)
                          : String(item[col.key] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {!loading && filteredData.length > pageSize && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-800/80 bg-slate-950/40 px-4 py-3 text-xs text-slate-400">
            <p>
              Showing{" "}
              <span className="font-semibold text-slate-200">
                {(currentPage - 1) * pageSize + 1}
              </span>{" "}
              to{" "}
              <span className="font-semibold text-slate-200">
                {Math.min(currentPage * pageSize, filteredData.length)}
              </span>{" "}
              of{" "}
              <span className="font-semibold text-slate-200">
                {filteredData.length}
              </span>{" "}
              entries
            </p>

            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                disabled={currentPage === 1}
                className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="px-2 font-medium text-slate-300">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                disabled={currentPage === totalPages}
                className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
