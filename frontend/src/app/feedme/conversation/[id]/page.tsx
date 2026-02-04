"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  RefreshCcw,
  CheckCircle2,
  Clock,
  Pencil,
} from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import UnifiedTextCanvas from "@/features/feedme/components/UnifiedTextCanvas";
import ConversationSidebar from "@/features/feedme/components/ConversationSidebar";
import { ErrorBoundary } from "@/features/feedme/components/ErrorBoundary";
import PlatformTagSelector from "@/features/feedme/components/PlatformTagSelector";
import { feedMeApi } from "@/features/feedme/services/feedme-api";
import { useUIStore } from "@/state/stores/ui-store";
import { cn } from "@/shared/lib/utils";
import { formatDistanceToNow } from "date-fns";
// Removed tooltip import as edit control moved to header actions
import type { ConversationDetail, PlatformTag } from "@/shared/types/feedme";

export default function FeedMeConversationPage() {
  const params = useParams();
  const router = useRouter();
  const conversationId = params?.id ? Number(params.id) : null;

  const showToast = useUIStore((state) => state.actions.showToast);

  const [conversation, setConversation] = useState<ConversationDetail | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [savingFolder, setSavingFolder] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [markingReady, setMarkingReady] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [isRenamingTitle, setIsRenamingTitle] = useState(false);

  // Prefer primary ai_note; gracefully fall back to legacy ai_comment when absent
  const aiNote = useMemo(
    () => conversation?.metadata?.ai_note ?? conversation?.metadata?.ai_comment,
    [conversation?.metadata],
  );
  const uploadedRelative = useMemo(
    () =>
      conversation?.created_at
        ? formatDistanceToNow(new Date(conversation.created_at), {
            addSuffix: true,
          })
        : null,
    [conversation?.created_at],
  );
  const updatedRelative = useMemo(
    () =>
      conversation?.updated_at
        ? formatDistanceToNow(new Date(conversation.updated_at), {
            addSuffix: true,
          })
        : null,
    [conversation?.updated_at],
  );

  const fetchConversation = useCallback(async () => {
    if (!conversationId) return;
    try {
      setLoading(true);
      const detail = await feedMeApi.getConversationById(conversationId);

      // Runtime validation of API response
      if (!detail || typeof detail !== "object") {
        throw new Error("Invalid conversation data received");
      }
      if (!("id" in detail) || !("title" in detail)) {
        throw new Error("Conversation data missing required fields");
      }

      setConversation(detail as ConversationDetail);
    } catch (error) {
      console.error("Failed to fetch conversation", error);
      showToast({
        type: "info",
        title: "Unable to load conversation",
        message:
          error instanceof Error ? error.message : "Please try again later",
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [conversationId, showToast]);

  useEffect(() => {
    fetchConversation().catch(() => {});
  }, [fetchConversation]);

  // Simple navigation - no need for useCallback
  const handleBack = () => router.push("/feedme");

  // Passed to UnifiedTextCanvas but it's not memoized - keep useCallback
  const handleTextUpdate = useCallback(
    async (text: string) => {
      if (!conversation) return;
      try {
        await feedMeApi.updateConversation(conversation.id, {
          extracted_text: text,
        });
        showToast({
          type: "success",
          title: "Canvas saved",
          message: "Draft updated successfully",
          duration: 3000,
        });
        await fetchConversation();
      } catch (error) {
        console.error("Failed to update text", error);
        showToast({
          type: "error",
          title: "Failed to save changes",
          message: error instanceof Error ? error.message : "Please try again",
          duration: 5000,
        });
        throw error; // Re-throw to let the UnifiedTextCanvas know the save failed
      }
    },
    [conversation, showToast, fetchConversation],
  );

  const handleFolderChange = useCallback(
    async (folderId: number | null) => {
      if (!conversation) return;
      try {
        setSavingFolder(true);
        // Directly assign to folder
        await feedMeApi.assignConversationsToFolderSupabase(folderId, [
          conversation.id,
        ]);
        setConversation((prev) =>
          prev
            ? {
                ...prev,
                folder_id: folderId,
              }
            : prev,
        );
        showToast({
          type: "success",
          title: "Folder updated",
          message: folderId
            ? "Conversation moved to folder."
            : "Conversation unassigned.",
          duration: 3000,
        });
      } catch (error) {
        console.error("Failed to update folder", error);
        showToast({
          type: "error",
          title: "Failed to update folder",
          message: "Please try again.",
          duration: 5000,
        });
        throw error;
      } finally {
        setSavingFolder(false);
      }
    },
    [conversation, showToast],
  );

  const handleSaveAiNote = useCallback(
    async (note: string) => {
      if (!conversation) return;
      try {
        setSavingNote(true);
        const metadata = { ...(conversation.metadata || {}), ai_note: note };
        await feedMeApi.updateConversation(conversation.id, { metadata });
        setConversation((prev) => (prev ? { ...prev, metadata } : prev));
        showToast({
          type: "success",
          title: "Note saved",
          message: "AI note updated.",
          duration: 3000,
        });
      } finally {
        setSavingNote(false);
      }
    },
    [conversation, showToast],
  );

  const startTitleEdit = useCallback(() => {
    if (!conversation) return;
    setIsEditingTitle(true);
    setTitleDraft(conversation.title || `Conversation ${conversation.id}`);
  }, [conversation]);

  const cancelTitleEdit = useCallback(() => {
    setIsEditingTitle(false);
    setTitleDraft("");
    setIsRenamingTitle(false);
  }, []);

  const commitTitleEdit = useCallback(async () => {
    if (!conversation) return;
    const trimmed = titleDraft.trim();
    if (!trimmed || trimmed === conversation.title) {
      cancelTitleEdit();
      return;
    }
    try {
      setIsRenamingTitle(true);
      await feedMeApi.updateConversation(conversation.id, { title: trimmed });
      setConversation((prev) => (prev ? { ...prev, title: trimmed } : prev));
      // Broadcast rename so open lists can update immediately
      document.dispatchEvent(
        new CustomEvent("feedme:conversation-renamed", {
          detail: { id: conversation.id, title: trimmed },
        }),
      );
      showToast({
        type: "success",
        title: "Title updated",
        message: "Conversation name saved.",
        duration: 3000,
      });
    } catch (error) {
      console.error("Failed to rename conversation", error);
      showToast({
        type: "error",
        title: "Rename failed",
        message: "Please try again.",
        duration: 4000,
      });
    } finally {
      cancelTitleEdit();
    }
  }, [conversation, titleDraft, cancelTitleEdit, showToast]);

  const handleMarkReady = useCallback(async () => {
    if (!conversation) return;

    // Check if folder is assigned
    if (!conversation.folder_id) {
      showToast({
        type: "warning",
        title: "Assign folder first",
        message: "Select a folder before marking ready.",
        duration: 4000,
      });
      return;
    }

    try {
      setMarkingReady(true);

      // Update metadata: mark as ready for knowledge base
      const metadata = {
        ...(conversation.metadata || {}),
        review_status: "ready",
        approval_status: "approved",
      };
      await feedMeApi.updateConversation(conversation.id, { metadata });

      showToast({
        type: "success",
        title: "Conversation marked ready",
        message: "Conversation flagged for knowledge base.",
        duration: 4000,
      });
      await fetchConversation();
    } catch (error) {
      console.error("Failed to mark ready", error);
      showToast({
        type: "error",
        title: "Failed to update conversation",
        message: "Please try again.",
        duration: 5000,
      });
    } finally {
      setMarkingReady(false);
    }
  }, [conversation, showToast, fetchConversation]);

  const handleTagUpdate = useCallback(
    async (tags: string[]) => {
      if (!conversation) return;

      try {
        const metadata = {
          ...(conversation.metadata || {}),
          tags: tags, // Single source of truth - no redundant platform_tag
        };

        await feedMeApi.updateConversation(conversation.id, { metadata });
        setConversation((prev) => (prev ? { ...prev, metadata } : prev));

        // Extract platform tag for toast message (with correct casing)
        const platformTag = tags.find(
          (t) => t.toLowerCase() === "windows" || t.toLowerCase() === "macos",
        );
        const displayTag = platformTag
          ? platformTag.toLowerCase() === "macos"
            ? "macOS"
            : "Windows"
          : null;

        showToast({
          type: "success",
          title: "Tags updated",
          message: displayTag
            ? `Platform tag set to ${displayTag}`
            : "Platform tag cleared",
          duration: 3000,
        });
      } catch (error) {
        console.error("Failed to update tags", error);
        showToast({
          type: "error",
          title: "Failed to update tags",
          message: error instanceof Error ? error.message : "Please try again",
          duration: 5000,
        });
        throw error;
      }
    },
    [conversation, showToast],
  );

  if (!conversationId) {
    return (
      <div className="flex h-screen items-center justify-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="ml-3 text-lg">Invalid conversation id.</p>
      </div>
    );
  }

  if (loading && !conversation) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="flex h-screen flex-col items-center justify-center space-y-3">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-sm text-muted-foreground">Conversation not found.</p>
        <Button variant="outline" onClick={handleBack}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back
        </Button>
      </div>
    );
  }

  const canEdit = conversation.processing_status === "completed";

  // Simple event dispatch - no need for useCallback
  const triggerEdit = () => {
    if (!canEdit || !conversation) return;
    document.dispatchEvent(
      new CustomEvent("feedme:toggle-edit", {
        detail: { conversationId: conversation.id, action: "start" as const },
      }),
    );
  };

  const statusIcon =
    conversation.processing_status === "completed" ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    ) : conversation.processing_status === "processing" ? (
      <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
    ) : conversation.processing_status === "failed" ? (
      <AlertCircle className="h-4 w-4 text-rose-500" />
    ) : conversation.processing_status === "pending" ? (
      <Clock className="h-4 w-4 text-amber-500" />
    ) : (
      <Clock className="h-4 w-4 text-muted-foreground" />
    );

  return (
    <ErrorBoundary>
      <div className="flex h-screen flex-col bg-background">
        <header className="border-b border-border/60 bg-card">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <Button variant="ghost" size="sm" onClick={handleBack}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <div className="space-y-1">
                    {isEditingTitle ? (
                      <Input
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        onBlur={() => {
                          if (!isRenamingTitle) void commitTitleEdit();
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void commitTitleEdit();
                          }
                          if (e.key === "Escape") {
                            e.preventDefault();
                            cancelTitleEdit();
                          }
                        }}
                        disabled={isRenamingTitle}
                        autoFocus
                        className="h-9 text-sm bg-background/70"
                      />
                    ) : (
                      <h1
                        className="text-lg font-semibold leading-tight"
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          startTitleEdit();
                        }}
                        title="Double-click to rename"
                      >
                        {conversation.title ||
                          `Conversation ${conversation.id}`}
                      </h1>
                    )}
                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1 text-emerald-600">
                        {statusIcon}
                      </span>
                      <span className="text-muted-foreground">
                        #{conversation.id}
                      </span>
                      {uploadedRelative && (
                        <span>Uploaded {uploadedRelative}</span>
                      )}
                      {updatedRelative && (
                        <span>Updated {updatedRelative}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {canEdit && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => triggerEdit()}
                  >
                    <Pencil className="mr-2 h-4 w-4" /> Edit
                  </Button>
                )}
                {canEdit && (
                  <PlatformTagSelector
                    conversationId={conversation.id}
                    currentTags={conversation.metadata?.tags || []}
                    onTagUpdate={handleTagUpdate}
                    disabled={conversation.processing_status !== "completed"}
                  />
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchConversation()}
                >
                  <RefreshCcw className="mr-2 h-4 w-4" /> Refresh
                </Button>
              </div>
            </div>
          </div>
        </header>

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="mx-auto grid h-full w-full max-w-6xl grid-cols-1 gap-8 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_360px]">
            <main className="relative min-h-0 overflow-hidden rounded-lg border border-border/60 bg-card shadow-sm">
              <div className="h-full overflow-hidden">
                {canEdit ? (
                  <UnifiedTextCanvas
                    conversationId={conversation.id}
                    title={conversation.title}
                    ticketId={conversation.metadata?.ticket_id}
                    extractedText={conversation.extracted_text || ""}
                    metadata={conversation.metadata}
                    processingMetadata={{
                      processing_method: (conversation.processing_method ||
                        "pdf_ai") as
                        | "pdf_ai"
                        | "pdf_ocr"
                        | "manual_text"
                        | "text_paste",
                      extraction_confidence:
                        conversation.metadata?.extraction_confidence,
                    }}
                    approvalStatus={conversation.approval_status || "pending"}
                    folderId={conversation.folder_id ?? null}
                    onTextUpdate={handleTextUpdate}
                    readOnly={false}
                    showApprovalControls={false}
                    fullPageMode
                    showProcessingSummary={false}
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center space-y-3 text-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      This conversation is still processing. You can edit once
                      processing completes.
                    </p>
                  </div>
                )}
              </div>
            </main>

            <aside className={cn("hidden min-h-0 lg:flex")}>
              <ConversationSidebar
                folderId={conversation.folder_id}
                aiNote={aiNote}
                onFolderChange={handleFolderChange}
                onSaveNote={handleSaveAiNote}
                onRegenerateNote={undefined}
                onMarkReady={handleMarkReady}
                isSavingFolder={savingFolder}
                isSavingNote={savingNote}
                isMarkingReady={markingReady}
              />
            </aside>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}
