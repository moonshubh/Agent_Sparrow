"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Separator } from "@/shared/ui/separator";
import { Upload, FileText, CheckCircle2, AlertCircle } from "lucide-react";
import { feedMeApi } from "@/features/feedme/services/feedme-api";
import { useUIStore } from "@/state/stores/ui-store";
import { useRouter } from "next/navigation";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

type Sel = {
  file: File;
  status: "pending" | "uploading" | "processing" | "done" | "error";
  message?: string;
  conversationId?: number;
  progress?: number;
};

export default function UploadDialog({ isOpen, onClose }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [sel, setSel] = useState<Sel[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [duplicateTarget, setDuplicateTarget] = useState<{
    conversationId: number;
    fileName: string;
  } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const canUpload = useMemo(
    () =>
      sel.length > 0 &&
      sel.every((s) => s.status === "pending" || s.status === "error"),
    [sel],
  );

  const pickFiles = () => inputRef.current?.click();

  const validatePdf = (f: File) =>
    f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const arr = Array.from(files);
      const onlyPdf = arr.filter(validatePdf);
      const trimmed = onlyPdf.slice(0, Math.max(0, 3 - sel.length));
      const mapped = trimmed.map<Sel>((f) => ({ file: f, status: "pending" }));
      const rejected = arr.filter((f) => !validatePdf(f));

      if (rejected.length > 0) {
        useUIStore.getState().actions.showToast({
          type: "warning",
          title: "Invalid files rejected",
          message: `${rejected.length} non-PDF file(s) were not added`,
          duration: 3500,
        });
      }

      setSel((prev) => [...prev, ...mapped]);
    },
    [sel.length],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (!e.dataTransfer.files?.length) return;
    addFiles(e.dataTransfer.files);
  };

  const onBrowse = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    e.currentTarget.value = "";
  };

  const removeAt = (idx: number) =>
    setSel((prev) => prev.filter((_, i) => i !== idx));

  const doUpload = async () => {
    setIsUploading(true);
    const abortController = new AbortController();

    try {
      const results: Sel[] = [];
      for (let i = 0; i < sel.length; i++) {
        const s = sel[i];
        if (s.status === "done") {
          results.push(s);
          continue;
        }

        // Update state once per file instead of multiple times
        setSel((prev) => {
          const updated = [...prev];
          updated[i] = { ...s, status: "uploading" };
          return updated;
        });
        results.push({ ...s, status: "uploading" });

        try {
          const res = await feedMeApi.uploadTranscriptFile(
            s.file.name.replace(/\.pdf$/i, ""),
            s.file,
          );
          const convId = res.conversation_id || res.id;

          if (res.duplicate && convId) {
            setSel((prev) => {
              const updated = [...prev];
              updated[i] = {
                ...s,
                status: "done",
                conversationId: convId,
                progress: 100,
                message: "Duplicate detected - existing conversation reused",
              };
              return updated;
            });
            results[i] = {
              ...s,
              status: "done",
              conversationId: convId,
              progress: 100,
              message: "Duplicate detected - existing conversation reused",
            };
            setDuplicateTarget({ conversationId: convId, fileName: s.file.name });
            useUIStore.getState().actions.showToast({
              type: "info",
              title: "Duplicate PDF detected",
              message: "Reused existing conversation instead of creating a new job.",
              duration: 4500,
            });
            continue;
          }

          if (convId) {
            // Update to processing state
            setSel((prev) => {
              const updated = [...prev];
              updated[i] = {
                ...s,
                status: "processing",
                conversationId: convId,
                progress: 10,
                message: "Uploaded",
              };
              return updated;
            });
            results[i] = {
              ...s,
              status: "processing",
              conversationId: convId,
              progress: 10,
              message: "Uploaded",
            };

            // Poll with exponential backoff
            let done = false;
            let attempts = 0;
            let delay = 1000;
            const maxAttempts = 30;
            const maxDelay = 10000;

            while (
              !done &&
              attempts < maxAttempts &&
              !abortController.signal.aborted
            ) {
              attempts++;

              try {
                const st = await feedMeApi.getProcessingStatus(convId);
                const prog = Math.max(
                  0,
                  Math.min(100, Math.round(st.progress_percentage ?? 0)),
                );
                const status = st.status;
                const statusMessage = st.message || status;

                setSel((prev) => {
                  const updated = [...prev];
                  updated[i] = {
                    ...updated[i],
                    status:
                      status === "completed"
                        ? "done"
                        : status === "failed" || status === "cancelled"
                          ? "error"
                          : "processing",
                    progress: status === "completed" ? 100 : prog,
                    message: statusMessage,
                  };
                  return updated;
                });
                results[i] = {
                  ...results[i],
                  status:
                    status === "completed"
                      ? "done"
                      : status === "failed" || status === "cancelled"
                        ? "error"
                        : "processing",
                  progress: status === "completed" ? 100 : prog,
                  message: statusMessage,
                };

                if (status === "completed" || status === "failed") {
                  useUIStore.getState().actions.showToast({
                    type: status === "completed" ? "success" : "error",
                    title:
                      status === "completed"
                        ? "Upload processed"
                        : "Processing failed",
                    message: st.message || s.file.name,
                    duration: status === "completed" ? 3500 : 5000,
                  });
                  done = true;
                }
              } catch (err) {
                console.error("Error checking processing status:", err);
              }

              if (!done && !abortController.signal.aborted) {
                await new Promise((r) => setTimeout(r, delay));
                delay = Math.min(delay * 1.5, maxDelay);
              }
            }
          } else {
            setSel((prev) => {
              const updated = [...prev];
              updated[i] = {
                ...s,
                status: "done",
                progress: 100,
                message: "Uploaded",
              };
              return updated;
            });
            results[i] = {
              ...s,
              status: "done",
              progress: 100,
              message: "Uploaded",
            };
          }
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : "Failed";
          setSel((prev) => {
            const updated = [...prev];
            updated[i] = { ...s, status: "error", message: errorMessage };
            return updated;
          });
          results[i] = { ...s, status: "error", message: errorMessage };
          useUIStore.getState().actions.showToast({
            type: "error",
            title: "Upload failed",
            message: s.file.name,
            duration: 5000,
          });
        }
      }
    } finally {
      setIsUploading(false);
      abortController.abort();
    }
  };

  // Keyboard shortcuts: Esc to close, Enter to upload
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      // Remove Enter key handler to avoid stale closure issues
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[760px] w-[760px] p-0 overflow-hidden">
        <div className="px-6 pt-6 pb-3 flex items-center justify-between">
          <DialogHeader className="p-0">
            <DialogTitle>Upload PDFs</DialogTitle>
            <DialogDescription>
              Drag & drop up to 3 PDF files or browse.
            </DialogDescription>
          </DialogHeader>
        </div>
        <Separator />
        <section className="p-6 space-y-4">
          <div
            className={
              `relative flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 ` +
              (dragActive
                ? "border-accent bg-accent/5"
                : "border-border/60 bg-background/60")
            }
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            role="region"
            aria-label="Upload area"
          >
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="mt-2 text-sm text-muted-foreground">
              Drop up to 3 PDF files here
            </p>
            <Button variant="secondary" className="mt-3" onClick={pickFiles}>
              Browse files
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              multiple
              onChange={onBrowse}
              className="hidden"
            />
          </div>

          {sel.length > 0 && (
            <ul className="space-y-2">
              {sel.map((s, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded-md border bg-background/60 px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">{s.file.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.status === "processing" && (
                      <span className="text-accent flex items-center gap-1 text-xs">
                        <Upload className="h-3 w-3" /> Processing{" "}
                        {s.progress ? `${s.progress}%` : ""}
                      </span>
                    )}
                    {s.status === "done" && (
                      <span className="text-green-500 flex items-center gap-1 text-sm">
                        <CheckCircle2 className="h-4 w-4" /> Completed
                      </span>
                    )}
                    {s.status === "error" && (
                      <span className="text-red-500 flex items-center gap-1 text-sm">
                        <AlertCircle className="h-4 w-4" /> {s.message}
                      </span>
                    )}
                    {s.status === "pending" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-2"
                        onClick={() => removeAt(i)}
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <DialogFooter className="px-6 pb-6">
          <Button variant="secondary" onClick={onClose} disabled={isUploading}>
            Close
          </Button>
          <Button disabled={!canUpload || isUploading} onClick={doUpload}>
            {isUploading ? "Uploading…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>

      <AlertDialog
        open={!!duplicateTarget}
        onOpenChange={(open) => {
          if (!open) {
            setDuplicateTarget(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Duplicate PDF found</AlertDialogTitle>
            <AlertDialogDescription>
              {duplicateTarget
                ? `“${duplicateTarget.fileName}” matches an existing upload.`
                : "This file already exists."}{" "}
              Open the existing conversation instead of uploading another copy?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep Here</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!duplicateTarget) return;
                const conversationId = duplicateTarget.conversationId;
                setDuplicateTarget(null);
                onClose();
                router.push(`/feedme/conversation/${conversationId}`);
              }}
            >
              Open Existing Conversation
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
