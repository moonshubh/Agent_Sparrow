"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Separator } from "@/shared/ui/separator";
import { ScrollArea } from "@/shared/ui/scroll-area";
import {
  CheckCircle2,
  Clock,
  Loader2,
  FileText,
  X,
  RefreshCw,
  Trash2,
  AlertCircle,
  ArrowLeft,
  Maximize2,
} from "lucide-react";
import { Input } from "@/shared/ui/input";
import {
  feedMeApi,
  isSupersededRequestError,
} from "@/features/feedme/services/feedme-api";
import { useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
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
import { useUIStore } from "@/state/stores/ui-store";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/shared/lib/utils";
import type { ProcessingStageValue } from "@/state/stores/realtime-store";
import { DialogErrorBoundary } from "./DialogErrorBoundary";
import { GlowingEffect } from "@/shared/ui/glowing-effect";
import { useFoldersStore } from "@/state/stores/folders-store";

// Constants
const MAX_CONVERSATIONS_PER_PAGE = 100;

interface Props {
  isOpen: boolean;
  onClose: () => void;
  folderId: number;
  folderName: string;
  folderColor?: string;
}

interface ConversationItem {
  id: number;
  title: string;
  processing_status:
    | "pending"
    | "processing"
    | "completed"
    | "failed"
    | "cancelled";
  progress_percentage?: number;
  processing_stage?: ProcessingStageValue;
  status_message?: string;
  created_at: string;
  updated_at?: string;
  extracted_text?: string;
  processing_method?: string;
  metadata?: Record<string, unknown>;
  folder_id?: number | null;
}

const FolderConversationsDialog = React.memo(
  function FolderConversationsDialog({
    isOpen,
    onClose,
    folderId,
    folderName,
    folderColor = "#6b7280",
  }: Props) {
    const [conversations, setConversations] = useState<ConversationItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [titleDraft, setTitleDraft] = useState("");
    const [originalTitle, setOriginalTitle] = useState("");
    const [isRenaming, setIsRenaming] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<ConversationItem | null>(
      null,
    );
    const [isDeleting, setIsDeleting] = useState(false);
    const [hasFetchedData, setHasFetchedData] = useState(false);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [moveTargetId, setMoveTargetId] = useState<string>("none");
    const [confirmBulkMoveOpen, setConfirmBulkMoveOpen] = useState(false);
    const [isBulkMoving, setIsBulkMoving] = useState(false);
    const router = useRouter();
    const showToast = useUIStore((state) => state.actions.showToast);
    const folderTree = useFoldersStore((state) => state.folderTree);
    const renameInputRef = useRef<HTMLInputElement | null>(null);
    const inFlightFetchRef = useRef<Promise<void> | null>(null);
    const fetchRequestIdRef = useRef(0);

    const fetchFolderConversations = useCallback(async () => {
      if (inFlightFetchRef.current) {
        return inFlightFetchRef.current;
      }

      const requestId = ++fetchRequestIdRef.current;
      setLoading(true);
      setError(null);

      const fetchPromise = (async () => {
        try {
          // Fetch conversations for this specific folder
          const response = await feedMeApi.listConversations(
            1,
            MAX_CONVERSATIONS_PER_PAGE,
            undefined,
            undefined,
            undefined,
            folderId,
          );

          if (requestId !== fetchRequestIdRef.current) {
            return;
          }

          // API already filters by folderId, no need for client-side filtering
          interface ProcessingTracker {
            progress?: number;
            stage?: ProcessingStageValue;
            message?: string;
          }

          const enriched: ConversationItem[] = response.conversations.map(
            (conv) => {
              const safeMetadata = (conv.metadata ?? {}) as {
                processing_tracker?: ProcessingTracker;
                processing_method?: string;
              };
              const tracker = safeMetadata.processing_tracker ?? {};
              const processingMethod =
                (conv as { processing_method?: string }).processing_method ??
                safeMetadata.processing_method;
              const statusMessageSource = conv as {
                status_message?: string;
                message?: string;
              };
              const progress =
                typeof tracker.progress === "number"
                  ? tracker.progress
                  : conv.processing_status === "completed" ||
                      conv.processing_status === "failed"
                    ? 100
                    : undefined;

              const conversationId = conv.id ?? conv.conversation_id ?? 0;

              const extendedConv = conv as {
                updated_at?: string;
                extracted_text?: string;
              };

              return {
                id: conversationId,
                title: conv.title ?? `Conversation ${conversationId}`,
                processing_status:
                  conv.processing_status as ConversationItem["processing_status"],
                progress_percentage: progress,
                processing_stage: tracker.stage,
                status_message:
                  tracker.message ??
                  statusMessageSource.status_message ??
                  statusMessageSource.message ??
                  undefined,
                created_at: conv.created_at ?? new Date().toISOString(),
                updated_at: extendedConv.updated_at,
                extracted_text: extendedConv.extracted_text,
                processing_method: processingMethod,
                metadata: conv.metadata as Record<string, unknown> | undefined,
                folder_id:
                  (conv as { folder_id?: number | null }).folder_id ?? null,
              };
            },
          );

          setConversations(enriched);
          setSelectedIds(new Set());
        } catch (err) {
          if (isSupersededRequestError(err)) {
            return;
          }
          if (requestId !== fetchRequestIdRef.current) {
            return;
          }
          console.error("Failed to fetch folder conversations:", err);
          const errorMessage =
            err instanceof Error ? err.message : "Failed to load conversations";
          setError(errorMessage);
        } finally {
          if (requestId === fetchRequestIdRef.current) {
            setLoading(false);
          }
        }
      })();

      inFlightFetchRef.current = fetchPromise;
      try {
        await fetchPromise;
      } finally {
        if (inFlightFetchRef.current === fetchPromise) {
          inFlightFetchRef.current = null;
        }
      }
    }, [folderId]);

    // Fetch conversations when dialog opens
    useEffect(() => {
      if (!isOpen || !folderId) {
        fetchRequestIdRef.current += 1;
        inFlightFetchRef.current = null;
        setHasFetchedData(false);
        setSelectedIds(new Set());
        setMoveTargetId("none");
        setLoading(false);
        setError(null);
        return;
      }

      // Only fetch if we haven't fetched for this dialog session
      if (!hasFetchedData) {
        fetchFolderConversations();
        setHasFetchedData(true);
      }
    }, [isOpen, folderId, fetchFolderConversations, hasFetchedData]);

    // Focus rename input when editing starts
    useEffect(() => {
      if (editingId && renameInputRef.current) {
        requestAnimationFrame(() => {
          renameInputRef.current?.focus();
          renameInputRef.current?.select();
        });
      }
    }, [editingId]);

    const handleOpenConversation = useCallback(
      (conversationId: number) => {
        router.push(`/feedme/conversation/${conversationId}`);
        onClose();
      },
      [router, onClose],
    );

    const startRename = useCallback((conv: ConversationItem) => {
      setEditingId(conv.id);
      setTitleDraft(conv.title);
      setOriginalTitle(conv.title);
    }, []);

    const cancelRename = useCallback(() => {
      setEditingId(null);
      setTitleDraft("");
      setOriginalTitle("");
    }, []);

    const commitRename = useCallback(async () => {
      if (editingId === null || isRenaming) return;

      const conv = conversations.find((c) => c.id === editingId);
      if (!conv) {
        cancelRename();
        return;
      }

      const trimmed = titleDraft.trim();
      if (!trimmed || trimmed === originalTitle) {
        cancelRename();
        return;
      }

      setIsRenaming(true);
      try {
        await feedMeApi.updateConversation(editingId, { title: trimmed });
        setConversations((prev) =>
          prev.map((c) => (c.id === editingId ? { ...c, title: trimmed } : c)),
        );
        // Broadcast rename to synchronize other open views
        document.dispatchEvent(
          new CustomEvent("feedme:conversation-renamed", {
            detail: { id: editingId, title: trimmed },
          }),
        );
        showToast({
          type: "success",
          title: "Conversation renamed",
          message: `Updated to "${trimmed}"`,
          duration: 3000,
        });
        cancelRename();
      } catch (error) {
        console.error("Failed to rename conversation:", error);
        showToast({
          type: "error",
          title: "Rename failed",
          message: "Could not rename the conversation. Please try again.",
          duration: 4000,
        });
        setTitleDraft(originalTitle);
      } finally {
        setIsRenaming(false);
      }
    }, [
      editingId,
      titleDraft,
      originalTitle,
      isRenaming,
      conversations,
      cancelRename,
      showToast,
    ]);

    const handleDelete = useCallback((conv: ConversationItem) => {
      setDeleteTarget(conv);
    }, []);

    const confirmDelete = useCallback(async () => {
      if (!deleteTarget) return;

      setIsDeleting(true);
      try {
        await feedMeApi.deleteConversation(deleteTarget.id);
        setConversations((prev) =>
          prev.filter((c) => c.id !== deleteTarget.id),
        );
        showToast({
          type: "success",
          title: "Conversation deleted",
          message: `"${deleteTarget.title}" has been removed`,
          duration: 3000,
        });
      } catch (error) {
        console.error("Failed to delete conversation:", error);
        showToast({
          type: "error",
          title: "Delete failed",
          message: "Could not delete the conversation. Please try again.",
          duration: 4000,
        });
      } finally {
        setIsDeleting(false);
        setDeleteTarget(null);
      }
    }, [deleteTarget, showToast]);

    // Listen for external rename events to update titles in this dialog
    useEffect(() => {
      const handler = (e: Event) => {
        const detail = (e as CustomEvent<{ id: number; title: string }>).detail;
        if (!detail) return;
        setConversations((prev) =>
          prev.map((c) =>
            c.id === detail.id ? { ...c, title: detail.title } : c,
          ),
        );
      };
      document.addEventListener("feedme:conversation-renamed", handler);
      return () =>
        document.removeEventListener("feedme:conversation-renamed", handler);
    }, []);

    const folderOptions = folderTree
      .filter((folder) => folder.id !== 0 && folder.id !== folderId)
      .map((folder) => ({ id: folder.id, name: folder.name }));

    const selectedCount = selectedIds.size;

    const moveTargetLabel =
      moveTargetId === "unassigned"
        ? "Unassigned"
        : folderOptions.find((folder) => String(folder.id) === moveTargetId)
            ?.name || "Selected folder";

    const toggleSelection = useCallback((conversationId: number) => {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(conversationId)) {
          next.delete(conversationId);
        } else {
          next.add(conversationId);
        }
        return next;
      });
    }, []);

    const toggleSelectAll = useCallback(() => {
      setSelectedIds((prev) => {
        if (prev.size === conversations.length) {
          return new Set();
        }
        return new Set(conversations.map((conversation) => conversation.id));
      });
    }, [conversations]);

    const executeBulkMove = useCallback(async () => {
      if (moveTargetId === "none") {
        return;
      }
      const ids = Array.from(selectedIds);
      if (ids.length === 0) {
        return;
      }
      if (ids.length > 50) {
        showToast({
          type: "error",
          title: "Too many conversations selected",
          message: "Bulk move supports a maximum of 50 conversations per action.",
          duration: 5000,
        });
        return;
      }

      const targetFolderId =
        moveTargetId === "unassigned" ? null : Number(moveTargetId);

      setIsBulkMoving(true);
      try {
        const result = await feedMeApi.assignConversationsToFolderSupabase(
          targetFolderId,
          ids,
        );

        const movedIds = new Set(result.conversation_ids || []);
        setConversations((prev) =>
          prev.filter((conversation) => !movedIds.has(conversation.id)),
        );
        setSelectedIds(new Set());

        if (result.partial_success) {
          showToast({
            type: "warning",
            title: "Bulk move partially completed",
            message: `Moved ${result.assigned_count} of ${result.requested_count} conversation(s).`,
            duration: 5000,
          });
        } else {
          showToast({
            type: "success",
            title: "Bulk move completed",
            message: `Moved ${result.assigned_count} conversation(s) to ${moveTargetLabel}.`,
            duration: 4000,
          });
        }
      } catch (error) {
        showToast({
          type: "error",
          title: "Bulk move failed",
          message: error instanceof Error ? error.message : "Please try again.",
          duration: 5000,
        });
      } finally {
        setIsBulkMoving(false);
        setConfirmBulkMoveOpen(false);
      }
    }, [moveTargetId, moveTargetLabel, selectedIds, showToast]);

    const getStatusIcon = useCallback(
      (status: ConversationItem["processing_status"]) => {
        switch (status) {
          case "completed":
            return <CheckCircle2 className="h-4 w-4 text-green-600" />;
          case "processing":
            return <Loader2 className="h-4 w-4 animate-spin text-blue-600" />;
          case "failed":
            return <X className="h-4 w-4 text-red-600" />;
          case "pending":
          default:
            return <Clock className="h-4 w-4 text-amber-600" />;
        }
      },
      [],
    );

    return (
      <>
        <Dialog open={isOpen} onOpenChange={onClose}>
          <DialogContent
            hideClose
            className="w-[900px] max-w-[900px] overflow-hidden p-0"
          >
            <DialogErrorBoundary
              fallbackTitle="Failed to load folder conversations"
              onReset={fetchFolderConversations}
            >
              <DialogHeader className="flex flex-row items-center justify-between gap-3 px-6 pt-6 pb-3 space-y-0">
                <div className="flex items-center gap-3">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={onClose}
                    aria-label="Go back to folders"
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: folderColor }}
                  />
                  <DialogTitle className="font-semibold">
                    {folderName}
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({conversations.length} conversation
                      {conversations.length !== 1 ? "s" : ""})
                    </span>
                  </DialogTitle>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={fetchFolderConversations}
                    disabled={loading}
                    aria-label="Refresh conversations"
                  >
                    <RefreshCw
                      className={cn("h-4 w-4", loading && "animate-spin")}
                    />
                    <span className="ml-2">Refresh</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={onClose}
                    aria-label="Close folder conversations"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </DialogHeader>

              <Separator />

              <div className="border-b bg-muted/20 px-6 py-3">
                <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center justify-center gap-2 rounded-xl border border-border/50 bg-background/70 p-2.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={toggleSelectAll}
                    disabled={conversations.length === 0}
                  >
                    {selectedCount === conversations.length &&
                    conversations.length > 0
                      ? "Clear Selection"
                      : "Select All"}
                  </Button>
                  <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                    Selected {selectedCount}
                  </span>
                  <Select value={moveTargetId} onValueChange={setMoveTargetId}>
                    <SelectTrigger className="h-8 w-[220px]">
                      <SelectValue placeholder="Move to folder" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Choose destination</SelectItem>
                      <SelectItem value="unassigned">Unassigned</SelectItem>
                      {folderOptions.map((folder) => (
                        <SelectItem key={folder.id} value={String(folder.id)}>
                          {folder.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    onClick={() => setConfirmBulkMoveOpen(true)}
                    disabled={
                      selectedCount === 0 ||
                      moveTargetId === "none" ||
                      isBulkMoving
                    }
                    className="min-w-[120px]"
                  >
                    Move Selected
                  </Button>
                </div>
              </div>

              <ScrollArea className="h-[500px]">
                <div className="p-6">
                  {loading && conversations.length === 0 && (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  )}

                  {error && (
                    <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                      <div className="flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 text-destructive" />
                        <p className="text-sm text-destructive">{error}</p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={fetchFolderConversations}
                      >
                        Try Again
                      </Button>
                    </div>
                  )}

                  {!loading && !error && conversations.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <FileText className="h-12 w-12 text-muted-foreground/30 mb-4" />
                      <p className="text-sm text-muted-foreground">
                        No conversations in this folder yet.
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Assign conversations from the Unassigned view or Canvas
                        sidebar.
                      </p>
                    </div>
                  )}

                  {!loading && conversations.length > 0 && (
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {conversations.map((conv) => {
                        const isEditing = editingId === conv.id;
                        const createdRelative = formatDistanceToNow(
                          new Date(conv.created_at),
                          { addSuffix: true },
                        );

                        return (
                          <div
                            key={conv.id}
                            className="group relative flex h-full cursor-pointer flex-col rounded-[1.5rem] p-1.5 transition-all duration-300 hover:-translate-y-1"
                            role="article"
                            aria-label={`Conversation: ${conv.title}`}
                            onClick={() => {
                              if (editingId === conv.id) return;
                              handleOpenConversation(conv.id);
                            }}
                          >
                            <GlowingEffect
                              blur={0}
                              borderWidth={3}
                              spread={80}
                              glow={true}
                              disabled={false}
                              proximity={64}
                              inactiveZone={0.01}
                            />

                            <input
                              type="checkbox"
                              checked={selectedIds.has(conv.id)}
                              onChange={(event) => {
                                event.stopPropagation();
                                toggleSelection(conv.id);
                              }}
                              onClick={(event) => event.stopPropagation()}
                              className="absolute left-3 top-3 z-10 h-3 w-3 cursor-pointer rounded border-border bg-background/95 shadow-sm"
                              aria-label={`Select conversation ${conv.id}`}
                            />

                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                handleDelete(conv);
                              }}
                              className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-border/40 bg-background/80 text-muted-foreground/90 opacity-0 backdrop-blur transition-opacity duration-200 group-hover:opacity-100 hover:border-destructive/40 hover:text-destructive z-10"
                              aria-label={`Delete conversation ${conv.title}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>

                            <div className="relative flex h-full flex-col overflow-hidden rounded-[1.25rem] bg-card/95 p-5 pl-5 pr-8 shadow-none">
                              <div className="mb-4 flex items-start gap-3">
                                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/20 text-black shadow-sm backdrop-blur dark:border-white/20 dark:bg-white/10 dark:text-white">
                                  <FileText className="h-4 w-4" />
                                </div>

                                <div className="flex-1 min-w-0">
                                  {isEditing ? (
                                    <Input
                                      ref={renameInputRef}
                                      value={titleDraft}
                                      onChange={(e) =>
                                        setTitleDraft(e.target.value)
                                      }
                                      onClick={(event) =>
                                        event.stopPropagation()
                                      }
                                      onBlur={commitRename}
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          e.preventDefault();
                                          void commitRename();
                                        } else if (e.key === "Escape") {
                                          e.preventDefault();
                                          cancelRename();
                                        }
                                      }}
                                      className="h-9 text-sm bg-background/70"
                                      disabled={isRenaming}
                                      aria-label="Edit conversation title"
                                    />
                                  ) : (
                                    <h4
                                      className="text-sm font-semibold leading-5 text-foreground transition-colors line-clamp-2 group-hover:text-primary"
                                      onDoubleClick={(event) => {
                                        event.stopPropagation();
                                        startRename(conv);
                                      }}
                                    >
                                      {conv.title || `Conversation ${conv.id}`}
                                    </h4>
                                  )}

                                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                    <span>Created {createdRelative}</span>
                                    {conv.processing_method && (
                                      <span>
                                        •{" "}
                                        {conv.processing_method.replace(
                                          /_/g,
                                          " ",
                                        )}
                                      </span>
                                    )}
                                    {conv.progress_percentage !== undefined &&
                                      conv.processing_status ===
                                        "processing" && (
                                        <span>
                                          • {conv.progress_percentage}%
                                        </span>
                                      )}
                                  </div>
                                </div>
                              </div>

                              <div className="mt-auto flex items-center justify-between text-xs text-muted-foreground">
                                <div className="flex items-center gap-2">
                                  {getStatusIcon(conv.processing_status)}
                                  <span className="capitalize">
                                    {conv.processing_status}
                                  </span>
                                </div>
                                {conv.status_message &&
                                  conv.processing_status !== "processing" && (
                                    <span className="line-clamp-1 text-right">
                                      {conv.status_message}
                                    </span>
                                  )}
                              </div>

                              {conv.processing_status === "processing" &&
                                conv.progress_percentage !== undefined && (
                                  <div className="mt-3">
                                    <div className="h-1.5 w-full rounded-full bg-emerald-600/15">
                                      <div
                                        className="h-1.5 rounded-full bg-emerald-400 transition-all duration-300"
                                        style={{
                                          width: `${Math.min(Math.max(conv.progress_percentage, 0), 100)}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                )}

                              {conv.status_message &&
                                conv.processing_status === "processing" && (
                                  <p className="mt-2 text-[11px] text-muted-foreground">
                                    {conv.status_message}
                                  </p>
                                )}

                              <button
                                className="absolute right-3 bottom-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-background/80 text-muted-foreground/90 opacity-0 backdrop-blur transition-opacity duration-200 group-hover:opacity-100 hover:border-accent hover:text-accent-foreground z-10 shadow-sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleOpenConversation(conv.id);
                                }}
                                aria-label={`Open conversation ${conv.title}`}
                              >
                                <Maximize2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </DialogErrorBoundary>
          </DialogContent>
        </Dialog>

        <AlertDialog
          open={confirmBulkMoveOpen}
          onOpenChange={(open) => {
            if (!isBulkMoving) {
              setConfirmBulkMoveOpen(open);
            }
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Move selected conversations?</AlertDialogTitle>
              <AlertDialogDescription>
                Move {selectedCount} conversation(s) to {moveTargetLabel}.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isBulkMoving}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  void executeBulkMove();
                }}
                disabled={isBulkMoving}
              >
                {isBulkMoving && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Move
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog
          open={!!deleteTarget}
          onOpenChange={() => setDeleteTarget(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
              <AlertDialogDescription>
                Are you sure you want to delete &quot;{deleteTarget?.title}
                &quot;? This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isDeleting}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={confirmDelete}
                disabled={isDeleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>
    );
  },
);

export default FolderConversationsDialog;
