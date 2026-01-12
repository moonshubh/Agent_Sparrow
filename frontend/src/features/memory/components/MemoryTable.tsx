'use client';

import React, { useMemo, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, ThumbsUp, ThumbsDown, Eye, Trash2, Pencil, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import {
  useApproveMemory,
  useDeleteMemory,
  useMemories,
  useMemory,
  useMemorySearch,
  useSubmitFeedback,
} from '../hooks';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip';
import { ConfidenceBadge } from './ConfidenceBadge';
import { SourceBadge } from './source-badge';
import { MemoryForm } from './MemoryForm';
import { isMemoryEdited } from '../lib/memoryFlags';
import type { Memory, MemoryFilters, FeedbackType } from '../types';

interface MemoryTableProps {
  searchQuery?: string;
  filters?: MemoryFilters;
  isAdmin?: boolean;
  onSortChange?: (sortBy: MemoryFilters['sortBy'], sortOrder: MemoryFilters['sortOrder']) => void;
  focusMemoryId?: string | null;
  onClearFocus?: () => void;
}

function toMemorySortField(sortBy: MemoryFilters['sortBy']): keyof Memory {
  switch (sortBy) {
    case 'confidence':
      return 'confidence_score';
    case 'retrieval_count':
      return 'retrieval_count';
    default:
      return 'created_at';
  }
}

function toFiltersSortBy(field: keyof Memory): MemoryFilters['sortBy'] | null {
  switch (field) {
    case 'confidence_score':
      return 'confidence';
    case 'retrieval_count':
      return 'retrieval_count';
    case 'created_at':
      return 'created_at';
    default:
      return null;
  }
}

export default function MemoryTable({
  searchQuery,
  filters,
  isAdmin = false,
  onSortChange,
  focusMemoryId,
  onClearFocus,
}: MemoryTableProps) {
  const [localSortField, setLocalSortField] = useState<keyof Memory>('created_at');
  const [localSortOrder, setLocalSortOrder] = useState<'asc' | 'desc'>('desc');
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const isControlledSort = Boolean(filters && onSortChange);
  const sortField = isControlledSort
    ? toMemorySortField(filters?.sortBy ?? 'created_at')
    : localSortField;
  const sortOrder = isControlledSort ? (filters?.sortOrder ?? 'desc') : localSortOrder;

  // Use search when query exists, otherwise list
  const { data: searchResults, isLoading: searchLoading, error: searchError } = useMemorySearch(
    searchQuery || '',
    {
      enabled: Boolean(searchQuery && searchQuery.length >= 2),
      reviewStatus: filters?.reviewStatus,
    }
  );

  const { data: listResults, isLoading: listLoading, error: listError } = useMemories({
    limit: pageSize,
    offset: page * pageSize,
    source_type: filters?.sourceType || undefined,
    review_status: filters?.reviewStatus,
    sort_order: sortField === 'created_at' ? sortOrder : 'desc',
  });

  // Use search when query is at least 2 characters, otherwise use list
  const isUsingSearch = Boolean(searchQuery && searchQuery.length >= 2);
  const memories = isUsingSearch ? searchResults : listResults;
  const isLoading = isUsingSearch ? searchLoading : listLoading;
  const loadError = isUsingSearch ? searchError : listError;

  const focusedMemoryQuery = useMemory(focusMemoryId ?? '', {
    enabled: Boolean(focusMemoryId),
  });

  const effectiveSelectedMemory =
    focusMemoryId && focusedMemoryQuery.data ? focusedMemoryQuery.data : selectedMemory;

  // Mutations
  const submitFeedback = useSubmitFeedback();
  const deleteMemory = useDeleteMemory();
  const approveMemory = useApproveMemory();

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
      if (aVal == null) return sortOrder === 'asc' ? 1 : -1;
      if (bVal == null) return sortOrder === 'asc' ? -1 : 1;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortOrder === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortOrder === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });
  }, [focusMemoryId, memoriesWithFocus, sortField, sortOrder]);

  // Toggle sort
  const handleSort = useCallback(
    (field: keyof Memory) => {
      setPage(0);

      if (isControlledSort && filters && onSortChange) {
        const sortBy = toFiltersSortBy(field);
        if (!sortBy) return;
        const nextOrder = sortField === field ? (sortOrder === 'asc' ? 'desc' : 'asc') : 'desc';
        onSortChange(sortBy, nextOrder);
        return;
      }

      if (localSortField === field) {
        setLocalSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      } else {
        setLocalSortField(field);
        setLocalSortOrder('desc');
      }
    },
    [filters, isControlledSort, localSortField, onSortChange, sortField, sortOrder]
  );

  const handleSortKeyDown = useCallback(
    (field: keyof Memory) => (event: React.KeyboardEvent<HTMLTableCellElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handleSort(field);
      }
    },
    [handleSort]
  );

  // Feedback handler
  const handleFeedback = useCallback(
    async (memoryId: string, type: FeedbackType) => {
      try {
        await submitFeedback.mutateAsync({
          memoryId,
          request: { feedback_type: type },
        });
      } catch (error) {
        console.error('Failed to submit feedback:', error);
        toast.error('Failed to submit feedback');
      }
    },
    [submitFeedback]
  );

  // Delete handler
  const handleDelete = useCallback(
    async (memoryId: string) => {
      if (confirm('Are you sure you want to delete this memory?')) {
        try {
          await deleteMemory.mutateAsync(memoryId);
        } catch (error) {
          console.error('Failed to delete memory:', error);
          toast.error('Failed to delete memory');
        }
      }
    },
    [deleteMemory]
  );

  const handleApprove = useCallback(
    async (memoryId: string) => {
      try {
        const result = await approveMemory.mutateAsync(memoryId);
        if (result.mem0_written) {
          toast.success('Approved and written to mem0');
        } else {
          toast.success('Approved');
        }
      } catch (error: unknown) {
        toast.error(error instanceof Error ? error.message : 'Failed to approve memory');
      }
    },
    [approveMemory]
  );

  // Format date
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Sort icon
  const renderSortIcon = (field: keyof Memory) => {
    if (sortField !== field) return null;
    return sortOrder === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />;
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
    const message = loadError instanceof Error ? loadError.message : 'Unknown error';
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
        {searchQuery && <p className="memory-empty-hint">Try a different search term</p>}
      </div>
    );
  }

  return (
    <div className="memory-table-container">
      <TooltipProvider delayDuration={150}>
        <table className="memory-table">
          <thead>
            <tr>
              <th className="memory-th-content">Content</th>
              <th
                className="memory-th-confidence"
                onClick={() => handleSort('confidence_score')}
                onKeyDown={handleSortKeyDown('confidence_score')}
                tabIndex={0}
                role="button"
                aria-sort={
                  sortField === 'confidence_score'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : undefined
                }
              >
                Confidence {renderSortIcon('confidence_score')}
              </th>
              <th className="memory-th-source">Source</th>
              <th
                className="memory-th-retrievals"
                onClick={() => handleSort('retrieval_count')}
                onKeyDown={handleSortKeyDown('retrieval_count')}
                tabIndex={0}
                role="button"
                aria-sort={
                  sortField === 'retrieval_count'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : undefined
                }
              >
                <span
                  title="Times this memory has been retrieved by the agent. This counter increments when the Unified Agent retrieves memories via the Memory UI store (ENABLE_MEMORY_UI_RETRIEVAL)."
                >
                  Retrievals {renderSortIcon('retrieval_count')}
                </span>
              </th>
              <th
                className="memory-th-date"
                onClick={() => handleSort('created_at')}
                onKeyDown={handleSortKeyDown('created_at')}
                tabIndex={0}
                role="button"
                aria-sort={
                  sortField === 'created_at'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : undefined
                }
              >
                Created {renderSortIcon('created_at')}
              </th>
              <th className="memory-th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence>
              {sortedMemories.map((memory, index) => (
                <motion.tr
                  key={memory.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ delay: index * 0.03 }}
                  className={`memory-row ${isMemoryEdited(memory) ? 'is-edited' : ''} ${focusMemoryId === memory.id ? 'is-focused' : ''}`}
                >
                  <td className="memory-td-content">
                    <p className="memory-content-text">{memory.content}</p>
                  </td>
                  <td className="memory-td-confidence">
                    <ConfidenceBadge score={memory.confidence_score} />
                  </td>
                  <td className="memory-td-source">
                    <SourceBadge sourceType={memory.source_type} />
                  </td>
                  <td className="memory-td-retrievals">
                    <span className="memory-retrieval-count">{memory.retrieval_count}</span>
                  </td>
                  <td className="memory-td-date">
                    <span className="memory-date">{formatDate(memory.created_at)}</span>
                  </td>
                  <td className="memory-td-actions">
                    <div className="memory-actions">
                      {isAdmin && filters?.reviewStatus === 'pending_review' && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              className="memory-action-icon memory-action-success"
                              onClick={() => handleApprove(memory.id)}
                              aria-label="Approve memory"
                              disabled={approveMemory.isPending}
                              title="Approve (also writes to mem0 and updates linked entries)"
                            >
                              <Check size={14} />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent className="memory-tooltip-content" side="top">
                            Approve
                          </TooltipContent>
                        </Tooltip>
                      )}

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            className="memory-action-icon memory-action-success"
                            onClick={() => handleFeedback(memory.id, 'thumbs_up')}
                            aria-label="Mark as helpful"
                            disabled={submitFeedback.isPending}
                          >
                            <ThumbsUp size={14} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="memory-tooltip-content" side="top">
                          👍 {memory.feedback_positive} · 👎 {memory.feedback_negative}
                        </TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            className="memory-action-icon memory-action-danger"
                            onClick={() => handleFeedback(memory.id, 'thumbs_down')}
                            aria-label="Mark as not helpful"
                            disabled={submitFeedback.isPending}
                          >
                            <ThumbsDown size={14} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="memory-tooltip-content" side="top">
                          👍 {memory.feedback_positive} · 👎 {memory.feedback_negative}
                        </TooltipContent>
                      </Tooltip>

                      <button
                        className="memory-action-icon"
                        onClick={() => {
                          onClearFocus?.();
                          setSelectedMemory(memory);
                        }}
                        title="View details"
                      >
                        <Eye size={14} />
                      </button>
                      {isAdmin && (
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
              ))}
            </AnimatePresence>
          </tbody>
        </table>
      </TooltipProvider>

      {/* Pagination */}
      {!searchQuery && (
        <div className="memory-pagination">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="memory-pagination-btn"
          >
            Previous
          </button>
          <span className="memory-pagination-info">Page {page + 1}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!memories || memories.length < pageSize}
            className="memory-pagination-btn"
          >
            Next
          </button>
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
              if (focusMemoryId && effectiveSelectedMemory.id === focusMemoryId) {
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
                  {isAdmin && (
                    <button
                      className="memory-action-icon"
                      onClick={() => {
                        if (focusMemoryId && effectiveSelectedMemory.id === focusMemoryId) {
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
                      if (focusMemoryId && effectiveSelectedMemory.id === focusMemoryId) {
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
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{effectiveSelectedMemory.content}</ReactMarkdown>
                  </div>
                </div>
                <div className="memory-detail-grid">
                  <div className="memory-detail-item">
                    <label>Confidence</label>
                    <ConfidenceBadge score={effectiveSelectedMemory.confidence_score} />
                  </div>
                  <div className="memory-detail-item">
                    <label>Source</label>
                    <SourceBadge sourceType={effectiveSelectedMemory.source_type} />
                  </div>
                  <div className="memory-detail-item">
                    <label>Retrievals</label>
                    <span>{effectiveSelectedMemory.retrieval_count}</span>
                  </div>
                  <div className="memory-detail-item">
                    <label>Created</label>
                    <span>{formatDate(effectiveSelectedMemory.created_at)}</span>
                  </div>
                </div>
                {effectiveSelectedMemory.metadata &&
                  Object.keys(effectiveSelectedMemory.metadata).length > 0 && (
                  <div className="memory-detail-section">
                    <label>Metadata</label>
                    <pre className="memory-detail-metadata">
                      {JSON.stringify(effectiveSelectedMemory.metadata, null, 2)}
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
        {editingMemory && (
          <MemoryForm
            memory={editingMemory}
            onClose={() => setEditingMemory(null)}
            onSuccess={() => setEditingMemory(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
