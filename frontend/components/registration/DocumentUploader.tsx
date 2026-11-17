"use client";

import React, { useState } from "react";
import { DocumentMetadata, DocumentType } from "@/lib/types";
import { apiUploadDocument, apiDeleteDocument } from "@/lib/api";

interface DocumentSlot {
  type: DocumentType;
  label: string;
  description: string;
  required: boolean;
}

interface DocumentUploaderProps {
  slots: DocumentSlot[];
  existingDocuments: DocumentMetadata[];
  applicantToken?: string | null;
  canEdit?: boolean;
  onDocumentsChanged: () => void;
}

const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB
const ALLOWED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"];

export const DocumentUploader: React.FC<DocumentUploaderProps> = ({
  slots,
  existingDocuments,
  applicantToken,
  canEdit = true,
  onDocumentsChanged,
}) => {
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [errorMap, setErrorMap] = useState<Record<string, string>>({});

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const handleFileSelect = async (slotType: DocumentType, file: File | null) => {
    if (!file) return;

    setErrorMap((prev) => ({ ...prev, [slotType]: "" }));

    // Client-side validations
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      setErrorMap((prev) => ({
        ...prev,
        [slotType]: "Invalid file format. Allowed formats: PDF (.pdf), JPEG (.jpg, .jpeg), PNG (.png).",
      }));
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setErrorMap((prev) => ({
        ...prev,
        [slotType]: `File exceeds maximum allowed size of 25 MB (${formatBytes(file.size)}).`,
      }));
      return;
    }

    setUploadingType(slotType);

    try {
      await apiUploadDocument(slotType, file, applicantToken);
      onDocumentsChanged();
    } catch (err: any) {
      setErrorMap((prev) => ({
        ...prev,
        [slotType]: err.message || "Upload failed. Please verify the document meets guidelines.",
      }));
    } finally {
      setUploadingType(null);
    }
  };

  const handleDelete = async (docId: string, slotType: string) => {
    if (!confirm("Are you sure you want to remove this document?")) return;

    setDeletingId(docId);
    setErrorMap((prev) => ({ ...prev, [slotType]: "" }));

    try {
      await apiDeleteDocument(docId, applicantToken);
      onDocumentsChanged();
    } catch (err: any) {
      setErrorMap((prev) => ({
        ...prev,
        [slotType]: err.message || "Failed to remove document.",
      }));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {slots.map((slot) => {
        const uploadedDoc = existingDocuments.find((d) => d.document_type === slot.type);
        const isUploading = uploadingType === slot.type;
        const err = errorMap[slot.type];

        return (
          <div
            key={slot.type}
            className={`rounded-2xl border p-4 sm:p-5 transition ${
              uploadedDoc
                ? uploadedDoc.verification_status === "REJECTED"
                  ? "border-rose-500/40 bg-rose-950/10"
                  : uploadedDoc.verification_status === "VERIFIED"
                  ? "border-emerald-500/40 bg-emerald-950/10"
                  : "border-slate-800 bg-slate-900/60"
                : "border-slate-800/80 bg-slate-900/30"
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{slot.label}</span>
                  {slot.required ? (
                    <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-rose-400 border border-rose-500/20">
                      Required
                    </span>
                  ) : (
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">
                      Optional
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-400">{slot.description}</p>
              </div>

              {/* Status Badge */}
              {uploadedDoc && (
                <div className="flex items-center gap-2">
                  {uploadedDoc.verification_status === "VERIFIED" && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-300">
                      ✓ Verified
                    </span>
                  )}
                  {uploadedDoc.verification_status === "REJECTED" && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-0.5 text-xs font-semibold text-rose-300">
                      ✕ Rejected
                    </span>
                  )}
                  {uploadedDoc.verification_status === "PENDING" && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 text-xs font-semibold text-blue-300">
                      ⟳ Pending Review
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* If uploaded */}
            {uploadedDoc ? (
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/80 p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-xl">📄</span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-200 truncate">
                        {uploadedDoc.original_filename}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {formatBytes(uploadedDoc.file_size_bytes)} • Uploaded{" "}
                        {new Date(uploadedDoc.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  {canEdit && (
                    <div className="flex items-center gap-2">
                      <label className="cursor-pointer rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-[11px] font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition">
                        Replace File
                        <input
                          type="file"
                          accept=".pdf,.jpg,.jpeg,.png"
                          className="hidden"
                          onChange={(e) => handleFileSelect(slot.type, e.target.files?.[0] || null)}
                          disabled={isUploading}
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => handleDelete(uploadedDoc.document_id, slot.type)}
                        disabled={deletingId === uploadedDoc.document_id}
                        className="rounded-lg border border-rose-800/40 bg-rose-950/30 px-3 py-1.5 text-[11px] font-semibold text-rose-300 hover:bg-rose-900/50 transition disabled:opacity-50"
                      >
                        {deletingId === uploadedDoc.document_id ? "Removing..." : "Remove"}
                      </button>
                    </div>
                  )}
                </div>

                {/* Reviewer remarks if rejected */}
                {uploadedDoc.reviewer_remarks && (
                  <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-2.5 text-xs text-rose-300">
                    <strong className="font-semibold">Reviewer Reason:</strong> {uploadedDoc.reviewer_remarks}
                  </div>
                )}
              </div>
            ) : (
              /* Upload Area */
              canEdit && (
                <div className="mt-3">
                  <label
                    className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/40 px-4 py-5 text-center cursor-pointer hover:border-blue-500 hover:bg-slate-900/50 transition ${
                      isUploading ? "opacity-50 pointer-events-none" : ""
                    }`}
                  >
                    <span className="text-2xl mb-1">📤</span>
                    <span className="text-xs font-semibold text-slate-200">
                      {isUploading ? "Uploading & scanning document..." : "Click to select or drag and drop"}
                    </span>
                    <span className="mt-1 text-[11px] text-slate-500">
                      PDF, JPEG, or PNG up to 25 MB
                    </span>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      className="hidden"
                      onChange={(e) => handleFileSelect(slot.type, e.target.files?.[0] || null)}
                      disabled={isUploading}
                    />
                  </label>
                </div>
              )
            )}

            {/* Error banner */}
            {err && (
              <div className="mt-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-2.5 text-xs text-rose-300">
                {err}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
