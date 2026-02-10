"use client";

import React, { useMemo, useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
  Trash2,
  Pencil,
} from "lucide-react";
import { MemoryTipTapEditor } from "./MemoryTipTapEditor";
import { normalizeLegacyMemoryContent } from "../lib/legacyMemoryFormatting";
import {
  useMemories,
  useMemory,
  useMemorySearch,
  useSubmitFeedback,
  useDeleteMemory,
} from "../hooks";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/ui/tooltip";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { SourceBadge } from "./SourceBadge";
import { MemoryForm } from "./MemoryForm";
import { getMemoryEditorDisplayName, isMemoryEdited } from "../lib/memoryFlags";
import type { Memory, MemoryFilters, FeedbackType } from "../types";

interface MemoryTableProps {
  searchQuery?: string;
  filters?: MemoryFilters;
  onSortChange?: (
    sortBy: MemoryFilters["sortBy"],
    sortOrder: MemoryFilters["sortOrder"],
  ) => void;
  focusMemoryId?: string | null;
  onClearFocus?: () => void;
  isAdmin?: boolean;
  onMemoryUpdated?: (memoryId?: string) => void;
}

function toMemorySortField(sortBy: MemoryFilters["sortBy"]): keyof Memory {
  switch (sortBy) {
    case "confidence":
      return "confidence_score";
    case "retrieval_count":
      return "retrieval_count";
    default:
      return "created_at";
  }
}

function toFiltersSortBy(field: keyof Memory): MemoryFilters["sortBy"] | null {
  switch (field) {
    case "confidence_score":
      return "confidence";
    case "retrieval_count":
      return "retrieval_count";
    case "created_at":
      return "created_at";
    default:
      return null;
  }
}

type PaginationItem = number | "ellipsis";
const EMPTY_MEMORIES: Memory[] = [];

function buildPaginationItems(
  totalPages: number,
  currentPage: number,
): PaginationItem[] {
  const pages = new Set<number>();
  const current = currentPage + 1;
  const lastPage = Math.max(1, totalPages);

  for (
    let pageNumber = 1;
    pageNumber <= Math.min(3, lastPage);
    pageNumber += 1
  ) {
    pages.add(pageNumber);
  }

  pages.add(lastPage);
  pages.add(current);
  pages.add(Math.max(1, current - 1));
  pages.add(Math.min(lastPage, current + 1));

  const sorted = Array.from(pages)
    .filter((pageNumber) => pageNumber >= 1 && pageNumber <= lastPage)
    .sort((a, b) => a - b);
  const items: PaginationItem[] = [];
  let previous = 0;

  sorted.forEach((pageNumber) => {
    if (previous && pageNumber - previous > 1) {
      items.push("ellipsis");
    }
    items.push(pageNumber);
    previous = pageNumber;
  });

  return items;
}

export default function MemoryTable({
  searchQuery,
  filters,
  onSortChange,
  focusMemoryId,
  onClearFocus,
  isAdmin = false,
  onMemoryUpdated,
}: MemoryTableProps) {
  const [localSortField, setLocalSortField] =
    useState<keyof Memory>("created_at");
  const [localSortOrder, setLocalSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [expandedPreviewById, setExpandedPreviewById] = useState<
    Record<string, boolean>
  >({});
  const [listPage, setListPage] = useState(0);
  const pageSize = 20;

  const isControlledSort = Boolean(filters && onSortChange);
  const sortField = isControlledSort
    ? toMemorySortField(filters?.sortBy ?? "created_at")
    : localSortField;
  const sortOrder = isControlledSort
    ? (filters?.sortOrder ?? "desc")
    : localSortOrder;

  // Use search when query exists, otherwise list
  const {
    data: searchResults,
    isLoading: searchLoading,
    error: searchError,
  } = useMemorySearch(searchQuery || "", {
    enabled: Boolean(searchQuery && searchQuery.length >= 2),
  });

  const isUsingSearch = Boolean(searchQuery && searchQuery.length >= 2);

  const {
    data: listResults,
    isLoading: listLoading,
    error: listError,
  } = useMemories(
    {
      limit: pageSize,
      offset: listPage * pageSize,
      source_type: filters?.sourceType || undefined,
      sort_order: sortField === "created_at" ? sortOrder : "desc",
    },
    {
      enabled: !isUsingSearch,
    },
  );

  useEffect(() => {
    if (!listResults) return;
    const nextTotalPages = Math.max(1, Math.ceil(listResults.total / pageSize));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setListPage((current) => Math.min(current, nextTotalPages - 1));
  }, [listResults, pageSize]);

  // Use search when query is at least 2 characters, otherwise use list
  const searchMemories = searchResults ?? EMPTY_MEMORIES;
  const listMemories = listResults?.items ?? EMPTY_MEMORIES;
  const listTotal = listResults?.total ?? listMemories.length;
  const totalCount = isUsingSearch ? searchMemories.length : listTotal;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const page = isUsingSearch ? 0 : Math.min(listPage, totalPages - 1);
  const memories = useMemo(
    () => (isUsingSearch ? searchMemories : listMemories),
    [isUsingSearch, listMemories, searchMemories],
  );
  const isLoading = isUsingSearch ? searchLoading : listLoading;
  const loadError = isUsingSearch ? searchError : listError;
  const pageOffset = isUsingSearch ? 0 : page * pageSize;

  const focusedMemoryQuery = useMemory(focusMemoryId ?? "", {
    enabled: Boolean(focusMemoryId),
  });

  const effectiveSelectedMemory =
    focusMemoryId && focusedMemoryQuery.data
      ? focusedMemoryQuery.data
      : selectedMemory;
  const canEdit = Boolean(isAdmin);

  // Mutations
  const submitFeedback = useSubmitFeedback();
  const deleteMemory = useDeleteMemory();

  const memoriesWithFocus = useMemo(() => {
    const base = memories ? [...memories] : [];
    const focused = focusedMemoryQuery.data;
    if (!focusMemoryId || !focused) return base;
    const exists = base.some((m) => m.id === focused.id);
    if (!exists) base.push(focused);
    return base;
  }, [focusMemoryId, focusedMemoryQuery.data, memories]);

  // Sort memories
  const sortedMemories = useMemo(() => {
    if (!memoriesWithFocus) return [];
    return [...memoriesWithFocus].sort((a, b) => {
      if (focusMemoryId) {
        if (a.id === focusMemoryId && b.id !== focusMemoryId) return -1;
        if (b.id === focusMemoryId && a.id !== focusMemoryId) return 1;
      }
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal == null) return sortOrder === "asc" ? 1 : -1;
      if (bVal == null) return sortOrder === "asc" ? -1 : 1;
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortOrder === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }
      return sortOrder === "asc"
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });
  }, [focusMemoryId, memoriesWithFocus, sortField, sortOrder]);

  const paginationItems = useMemo(
    () => buildPaginationItems(totalPages, page),
    [page, totalPages],
  );

  // Toggle sort
  const handleSort = useCallback(
    (field: keyof Memory) => {
      setListPage(0);

      if (isControlledSort && filters && onSortChange) {
        const sortBy = toFiltersSortBy(field);
        if (!sortBy) return;
        const nextOrder =
          sortField === field ? (sortOrder === "asc" ? "desc" : "asc") : "desc";
        onSortChange(sortBy, nextOrder);
        return;
      }

      if (localSortField === field) {
        setLocalSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setLocalSortField(field);
        setLocalSortOrder("desc");
      }
    },
    [
      filters,
      isControlledSort,
      localSortField,
      onSortChange,
      sortField,
      sortOrder,
    ],
  );

  // Feedback handler
  const handleFeedback = useCallback(
    async (memoryId: string, type: FeedbackType) => {
      const response = await submitFeedback.mutateAsync({
        memoryId,
        request: { feedback_type: type },
      });

      const parsed = Number(response.new_confidence_score);
      const fallbackDelta =
        type === "thumbs_up" ? 0.05 : type === "thumbs_down" ? -0.05 : 0;

      setSelectedMemory((prev) => {
        if (!prev || prev.id !== memoryId) return prev;
        const safeCurrent = Number.isFinite(Number(prev.confidence_score))
          ? Number(prev.confidence_score)
          : 0.5;
        const nextConfidence = Number.isFinite(parsed)
          ? parsed
          : Math.min(1, Math.max(0, safeCurrent + fallbackDelta));

        return {
          ...prev,
          confidence_score: nextConfidence,
          feedback_positive:
            type === "thumbs_up"
              ? Number(prev.feedback_positive || 0) + 1
              : prev.feedback_positive,
          feedback_negative:
            type === "thumbs_down"
              ? Number(prev.feedback_negative || 0) + 1
              : prev.feedback_negative,
        };
      });
    },
    [submitFeedback],
  );

  // Delete handler
  const handleDelete = useCallback(
    async (memoryId: string) => {
      if (confirm("Are you sure you want to delete this memory?")) {
        await deleteMemory.mutateAsync(memoryId);
      }
    },
    [deleteMemory],
  );

  const openMemoryFromContent = useCallback(
    (memory: Memory) => {
      onClearFocus?.();
      if (canEdit) {
        setEditingMemory(memory);
        setSelectedMemory(null);
        return;
      }
      setSelectedMemory(memory);
    },
    [canEdit, onClearFocus],
  );

  const getContentFallback = useCallback((content: string) => {
    const plain = (content || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[#>*_~\-[\]()]|\|/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return plain;
  }, []);

  const hasExpandablePreview = useCallback(
    (memory: Memory) => {
      const fallback = getContentFallback(memory.content);
      const lineCount = (memory.content.match(/\n/g) || []).length + 1;
      return fallback.length > 220 || lineCount > 3;
    },
    [getContentFallback],
  );

  // Format date
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Sort icon
  const renderSortIcon = (field: keyof Memory) => {
    if (sortField !== field) return null;
    return sortOrder === "asc" ? (
      <ChevronUp size={14} />
    ) : (
      <ChevronDown size={14} />
    );
  };

  if (isLoading) {
    return (
      <div className="memory-loading">
        <div className="memory-loading-spinner" />
        <p>Loading memories...</p>
      </div>
    );
  }

  if (loadError) {
    const message =
      loadError instanceof Error ? loadError.message : "Unknown error";
    return (
      <div className="memory-error">
        <p>Error loading memories</p>
        <p className="memory-empty-hint">{message}</p>
      </div>
    );
  }

  if (sortedMemories.length === 0) {
    return (
      <div className="memory-empty">
        <p>No memories found</p>
        {searchQuery && (
          <p className="memory-empty-hint">Try a different search term</p>
        )}
      </div>
    );
  }

  return (
    <div className="memory-table-container">
      <TooltipProvider delayDuration={150}>
        <table className="memory-table">
          <thead>
            <tr>
              <th className="memory-th-index">#</th>
              <th className="memory-th-content">Content</th>
              <th
                className="memory-th-confidence"
                onClick={() => handleSort("confidence_score")}
              >
                Confidence {renderSortIcon("confidence_score")}
              </th>
              <th className="memory-th-source">Source</th>
              <th
                className="memory-th-retrievals"
                onClick={() => handleSort("retrieval_count")}
              >
                <span title="Times this memory has been retrieved by the agent. This counter increments when the Unified Agent retrieves memories via the Memory UI store (ENABLE_MEMORY_UI_RETRIEVAL).">
                  Retrievals {renderSortIcon("retrieval_count")}
                </span>
              </th>
              <th
                className="memory-th-date"
                onClick={() => handleSort("created_at")}
              >
                Created {renderSortIcon("created_at")}
              </th>
              <th className="memory-th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence>
              {sortedMemories.map((memory, index) => {
                const isEdited = isMemoryEdited(memory);
                const editedBy = getMemoryEditorDisplayName(memory);
                const editedLabel = editedBy
                  ? `Edited by ${editedBy}`
                  : "Edited by admin";

                return (
                  <motion.tr
                    key={memory.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ delay: index * 0.03 }}
                    className={`memory-row ${isEdited ? "is-edited" : ""} ${focusMemoryId === memory.id ? "is-focused" : ""}`}
                  >
                    <td className="memory-td-index">
                      <span className="memory-index-number">
                        {pageOffset + index + 1}
                      </span>
                    </td>
                    <td className="memory-td-content">
                      {(() => {
                        const fallbackText = getContentFallback(memory.content);
                        const isExpanded = Boolean(expandedPreviewById[memory.id]);
                        const canExpand = hasExpandablePreview(memory);

                        return (
                          <div className="memory-content-cell">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  className={`memory-content-click-target ${isEdited ? "is-edited" : ""}`}
                                  onClick={() => openMemoryFromContent(memory)}
                                  title={
                                    canEdit
                                      ? "Open editor"
                                      : "Open memory details"
                                  }
                                >
                                  {isEdited && (
                                    <div className="memory-content-header">
                                      <span className="memory-edited-badge">
                                        Edited
                                      </span>
                                    </div>
                                  )}

                                  {isExpanded ? (
                                    <div className="memory-content-rich-preview">
                                      <MemoryTipTapEditor
                                        content={normalizeLegacyMemoryContent(
                                          memory.content,
                                        )}
                                        readOnly
                                        className="memory-content-inline-tiptap"
                                      />
                                    </div>
                                  ) : (
                                    <p className="memory-content-text">
                                      {fallbackText ||
                                        "No content preview available"}
                                    </p>
                                  )}
                                </button>
                              </TooltipTrigger>
                              {isEdited ? (
                                <TooltipContent
                                  className="memory-tooltip-content"
                                  side="top"
                                >
                                  {editedLabel}
                                </TooltipContent>
                              ) : null}
                            </Tooltip>

                            {canExpand ? (
                              <button
                                type="button"
                                className="memory-content-expand-btn"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setExpandedPreviewById((prev) => ({
                                    ...prev,
                                    [memory.id]: !prev[memory.id],
                                  }));
                                }}
                              >
                                {isExpanded ? "Show less" : "Show more"}
                              </button>
                            ) : null}
                          </div>
                        );
                      })()}
                    </td>
                    <td className="memory-td-confidence">
                      <ConfidenceBadge score={memory.confidence_score} />
                    </td>
                    <td className="memory-td-source">
                      <SourceBadge sourceType={memory.source_type} />
                    </td>
                    <td className="memory-td-retrievals">
                      <span className="memory-retrieval-count">
                        {memory.retrieval_count}
                      </span>
                    </td>
                    <td className="memory-td-date">
                      <span className="memory-date">
                        {formatDate(memory.created_at)}
                      </span>
                    </td>
                    <td className="memory-td-actions">
                      <div className="memory-actions">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              className="memory-action-icon memory-action-success"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleFeedback(memory.id, "thumbs_up");
                              }}
                              aria-label="Mark as helpful"
                              title="Increase confidence by 5%"
                              disabled={submitFeedback.isPending}
                            >
                              <ThumbsUp size={14} />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent
                            className="memory-tooltip-content"
                            side="top"
                          >
                            Weightage:{" "}
                            {Math.round(memory.confidence_score * 100)}% · 👍{" "}
                            {memory.feedback_positive} · 👎{" "}
                            {memory.feedback_negative}
                          </TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              className="memory-action-icon memory-action-danger"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleFeedback(memory.id, "thumbs_down");
                              }}
                              aria-label="Mark as not helpful"
                              title="Decrease confidence by 5%"
                              disabled={submitFeedback.isPending}
                            >
                              <ThumbsDown size={14} />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent
                            className="memory-tooltip-content"
                            side="top"
                          >
                            Weightage:{" "}
                            {Math.round(memory.confidence_score * 100)}% · 👍{" "}
                            {memory.feedback_positive} · 👎{" "}
                            {memory.feedback_negative}
                          </TooltipContent>
                        </Tooltip>
                        {canEdit && (
                          <button
                            className="memory-action-icon memory-action-danger"
                            onClick={() => handleDelete(memory.id)}
                            title="Delete memory"
                            disabled={deleteMemory.isPending}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                );
              })}
            </AnimatePresence>
          </tbody>
        </table>
      </TooltipProvider>

      {/* Pagination */}
      {!isUsingSearch && (
        <div className="memory-pagination">
          <button
            onClick={() => setListPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="memory-pagination-btn"
            aria-label="Previous page"
          >
            Previous
          </button>
          <div className="memory-pagination-pages">
            {paginationItems.map((item, idx) => {
              if (item === "ellipsis") {
                return (
                  <span
                    key={`ellipsis-${idx}`}
                    className="memory-pagination-ellipsis"
                  >
                    ...
                  </span>
                );
              }

              const isActive = item === page + 1;
              return (
                <button
                  key={`page-${item}`}
                  onClick={() => setListPage(item - 1)}
                  className={`memory-pagination-page ${isActive ? "is-active" : ""}`}
                  aria-current={isActive ? "page" : undefined}
                >
                  {item}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setListPage((p) => p + 1)}
            disabled={page >= totalPages - 1}
            className="memory-pagination-btn"
            aria-label="Next page"
          >
            Next
          </button>
          <span className="memory-pagination-info">
            Page {page + 1} of {totalPages}
          </span>
        </div>
      )}

      {/* Detail Panel */}
      <AnimatePresence>
        {effectiveSelectedMemory && (
          <motion.div
            className="memory-detail-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => {
              if (
                focusMemoryId &&
                effectiveSelectedMemory.id === focusMemoryId
              ) {
                onClearFocus?.();
              }
              setSelectedMemory(null);
            }}
          >
            <motion.div
              className="memory-detail-panel"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="memory-detail-header">
                <h3>Memory Details</h3>
                <div className="memory-detail-header-actions">
                  {canEdit && (
                    <button
                      className="memory-action-icon"
                      onClick={() => {
                        if (
                          focusMemoryId &&
                          effectiveSelectedMemory.id === focusMemoryId
                        ) {
                          onClearFocus?.();
                        }
                        setEditingMemory(effectiveSelectedMemory);
                        setSelectedMemory(null);
                      }}
                      title="Edit memory"
                    >
                      <Pencil size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (
                        focusMemoryId &&
                        effectiveSelectedMemory.id === focusMemoryId
                      ) {
                        onClearFocus?.();
                      }
                      setSelectedMemory(null);
                    }}
                  >
                    &times;
                  </button>
                </div>
              </div>
              <div className="memory-detail-content">
                <div className="memory-detail-section">
                  <label>Content</label>
                  <div className="memory-detail-markdown">
                    <MemoryTipTapEditor
                      content={normalizeLegacyMemoryContent(
                        effectiveSelectedMemory.content,
                      )}
                      readOnly
                      className="memory-detail-tiptap"
                    />
                  </div>
                </div>
                <div className="memory-detail-grid">
                  <div className="memory-detail-item">
                    <label>Confidence</label>
                    <ConfidenceBadge
                      score={effectiveSelectedMemory.confidence_score}
                    />
                  </div>
                  <div className="memory-detail-item">
                    <label>Source</label>
                    <SourceBadge
                      sourceType={effectiveSelectedMemory.source_type}
                    />
                  </div>
                  <div className="memory-detail-item">
                    <label>Retrievals</label>
                    <span>{effectiveSelectedMemory.retrieval_count}</span>
                  </div>
                  <div className="memory-detail-item">
                    <label>Created</label>
                    <span>
                      {formatDate(effectiveSelectedMemory.created_at)}
                    </span>
                  </div>
                </div>
                {effectiveSelectedMemory.metadata &&
                  Object.keys(effectiveSelectedMemory.metadata).length > 0 && (
                    <div className="memory-detail-section">
                      <label>Metadata</label>
                      <pre className="memory-detail-metadata">
                        {JSON.stringify(
                          effectiveSelectedMemory.metadata,
                          null,
                          2,
                        )}
                      </pre>
                    </div>
                  )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Modal */}
      <AnimatePresence>
        {editingMemory && canEdit && (
          <MemoryForm
            key={editingMemory.id}
            memory={editingMemory}
            onClose={() => setEditingMemory(null)}
            onSuccess={(memoryId) => {
              setEditingMemory(null);
              onMemoryUpdated?.(memoryId);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
