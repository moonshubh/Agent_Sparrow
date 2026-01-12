'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Check,
  FileText,
  Minus,
  RefreshCw,
  Sparkles,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import {
  useAcknowledgeRelationship,
  useEntityRelatedMemories,
  useMergeRelationships,
  useUpdateRelationship,
} from '../hooks';
import { RELATIONSHIP_LABELS } from '../types';
import type {
  RelationshipType,
  TreeEdge,
  TreeNodeData,
  UpdateRelationshipRequest,
} from '../types';
import { ClusterPreview } from './ClusterPreview';
import { RelationshipAnalysisPanel } from './RelationshipAnalysisPanel';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function toTimeMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function formatRelationshipLabel(type: RelationshipType): string {
  return RELATIONSHIP_LABELS[type] ?? type;
}

function formatShortId(id: string): string {
  if (id.length <= 16) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

type RelationshipEditorTab = 'edit' | 'ai' | 'evidence';

export function RelationshipEditor({
  edge,
  nodeById,
  open,
  initialRelationshipId,
  initialTab,
  onClose,
  onPreviewChange,
  onPreviewClear,
  onNavigateToEntityId,
  onInspectMemoryId,
}: {
  edge: TreeEdge;
  nodeById: Map<string, TreeNodeData>;
  open: boolean;
  initialRelationshipId?: string | null;
  initialTab?: RelationshipEditorTab;
  onClose: () => void;
  onPreviewChange: (relationshipId: string, request: UpdateRelationshipRequest) => void;
  onPreviewClear: () => void;
  onNavigateToEntityId?: (entityId: string) => void;
  onInspectMemoryId?: (memoryId: string, relationshipId: string) => void;
}) {
  const updateRelationship = useUpdateRelationship();
  const acknowledgeRelationship = useAcknowledgeRelationship();
  const mergeRelationships = useMergeRelationships();

  const [minimized, setMinimized] = useState(false);
  const [activeTab, setActiveTab] = useState<RelationshipEditorTab>(initialTab ?? 'edit');

  const defaultRelationshipId = edge.relationships[0]?.id ?? null;
  const initialSelectedRelationshipId =
    initialRelationshipId && edge.relationships.some((r) => r.id === initialRelationshipId)
      ? initialRelationshipId
      : defaultRelationshipId;
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<string | null>(
    initialSelectedRelationshipId
  );
  const [analysisKeepAliveRelationshipId, setAnalysisKeepAliveRelationshipId] = useState<
    string | null
  >(initialTab === 'ai' ? initialSelectedRelationshipId : null);
  const [mergeSelection, setMergeSelection] = useState<Set<string>>(
    () => new Set(defaultRelationshipId ? [defaultRelationshipId] : [])
  );
  const [splitOpen, setSplitOpen] = useState(false);
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<Set<string>>(() => new Set());

  const selectedRelationship = useMemo(() => {
    if (!selectedRelationshipId) return null;
    return edge.relationships.find((r) => r.id === selectedRelationshipId) ?? null;
  }, [edge.relationships, selectedRelationshipId]);

  const [draft, setDraft] = useState<UpdateRelationshipRequest | null>(null);

  const baseDraft = useMemo<UpdateRelationshipRequest | null>(() => {
    if (!selectedRelationship) return null;
    return {
      source_entity_id: selectedRelationship.sourceId,
      target_entity_id: selectedRelationship.targetId,
      relationship_type: selectedRelationship.relationshipType,
      weight: selectedRelationship.weight,
    };
  }, [selectedRelationship]);

  const isReviewed = useMemo(() => {
    if (!selectedRelationship?.acknowledgedAt) return false;
    const acknowledgedMs = toTimeMs(selectedRelationship.acknowledgedAt);
    if (!acknowledgedMs) return false;

    const modifiedMs = toTimeMs(selectedRelationship.lastModifiedAt);
    if (!modifiedMs) return true;

    return acknowledgedMs >= modifiedMs;
  }, [selectedRelationship?.acknowledgedAt, selectedRelationship?.lastModifiedAt]);

  useEffect(() => {
    setDraft(baseDraft);
  }, [baseDraft]);

  useEffect(() => {
    if (!selectedRelationshipId) return;
    setMergeSelection((prev) => {
      if (prev.has(selectedRelationshipId)) return prev;
      const next = new Set(prev);
      next.add(selectedRelationshipId);
      return next;
    });
  }, [selectedRelationshipId]);

  useEffect(() => {
    setExpandedEvidenceIds(new Set());
  }, [selectedRelationshipId]);

  useEffect(() => {
    if (!selectedRelationshipId || !draft || !baseDraft) return;

    const isDirty =
      draft.source_entity_id !== baseDraft.source_entity_id ||
      draft.target_entity_id !== baseDraft.target_entity_id ||
      draft.relationship_type !== baseDraft.relationship_type ||
      draft.weight !== baseDraft.weight;

    if (!isDirty) {
      onPreviewClear();
      return;
    }

    onPreviewChange(selectedRelationshipId, draft);
  }, [baseDraft, draft, onPreviewChange, onPreviewClear, selectedRelationshipId]);

  const sourceLabel = draft
    ? nodeById.get(draft.source_entity_id)?.node.displayLabel ?? draft.source_entity_id
    : '';
  const targetLabel = draft
    ? nodeById.get(draft.target_entity_id)?.node.displayLabel ?? draft.target_entity_id
    : '';

  const relationshipTypeOptions = useMemo(() => {
    return Object.keys(RELATIONSHIP_LABELS) as RelationshipType[];
  }, []);

  const sourceEvidenceQuery = useEntityRelatedMemories(draft?.source_entity_id ?? '', {
    enabled: open && !minimized && activeTab === 'evidence' && Boolean(draft),
    limit: 40,
  });

  const targetEvidenceQuery = useEntityRelatedMemories(draft?.target_entity_id ?? '', {
    enabled: open && !minimized && activeTab === 'evidence' && Boolean(draft),
    limit: 40,
  });

  const sharedEvidence = useMemo(() => {
    const source = sourceEvidenceQuery.data ?? [];
    const target = targetEvidenceQuery.data ?? [];
    if (!source.length || !target.length) return [];
    const targetIds = new Set(target.map((m) => m.id));
    return source.filter((m) => targetIds.has(m.id)).slice(0, 12);
  }, [sourceEvidenceQuery.data, targetEvidenceQuery.data]);

  const isDirty = useMemo(() => {
    if (!draft || !baseDraft) return false;
    return (
      draft.source_entity_id !== baseDraft.source_entity_id ||
      draft.target_entity_id !== baseDraft.target_entity_id ||
      draft.relationship_type !== baseDraft.relationship_type ||
      draft.weight !== baseDraft.weight
    );
  }, [baseDraft, draft]);

  const canSubmit = Boolean(draft && selectedRelationshipId && isDirty);

  const mergeIds = useMemo(() => Array.from(mergeSelection), [mergeSelection]);
  const canMerge = Boolean(draft && mergeIds.length >= 2);

  const handleClose = () => {
    onPreviewClear();
    setSplitOpen(false);
    setMinimized(false);
    setActiveTab('edit');
    setExpandedEvidenceIds(new Set());
    onClose();
  };

  return (
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            key="relationship-editor-overlay"
            className="relationship-editor-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: minimized ? 0 : 1 }}
            exit={{ opacity: 0 }}
            style={{ pointerEvents: minimized ? 'none' : 'auto' }}
            aria-hidden={minimized}
            onClick={handleClose}
          >
            <motion.div
              className="relationship-editor"
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 420, damping: 36 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relationship-editor__header">
                <div className="relationship-editor__title">Relationship</div>
                <div className="relationship-editor__header-actions">
                  <button
                    className="relationship-editor__close"
                    onClick={() => {
                      setSplitOpen(false);
                      setMinimized(true);
                    }}
                    title="Minimize"
                    type="button"
                  >
                    <Minus size={16} />
                  </button>
                  <button
                    className="relationship-editor__close"
                    onClick={handleClose}
                    title="Close"
                    type="button"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>

              {draft ? (
                <div className="relationship-editor__layout">
                  <aside className="relationship-editor__nav">
                    <button
                      type="button"
                      className={`relationship-editor__nav-item ${activeTab === 'edit' ? 'is-active' : ''}`}
                      onClick={() => setActiveTab('edit')}
                    >
                      <SlidersHorizontal size={16} />
                      Edit
                    </button>
                    <button
                      type="button"
                      className={`relationship-editor__nav-item ${activeTab === 'ai' ? 'is-active' : ''}`}
                      onClick={() => {
                        if (!selectedRelationshipId) return;
                        setAnalysisKeepAliveRelationshipId(selectedRelationshipId);
                        setActiveTab('ai');
                      }}
                      disabled={!selectedRelationshipId}
                    >
                      <Sparkles size={16} />
                      AI Analyze
                    </button>
                    <button
                      type="button"
                      className={`relationship-editor__nav-item ${activeTab === 'evidence' ? 'is-active' : ''}`}
                      onClick={() => setActiveTab('evidence')}
                      disabled={!draft}
                    >
                      <FileText size={16} />
                      Evidence
                    </button>

                    <div className="relationship-editor__nav-divider" />

                    <button
                      type="button"
                      className="relationship-editor__nav-item relationship-editor__nav-item--tertiary"
                      onClick={() => setSplitOpen(true)}
                      disabled={!selectedRelationshipId}
                      title="Preview an AI-assisted split for this edge"
                    >
                      <Sparkles size={16} />
                      Split (Preview)
                    </button>
                  </aside>

                  <section className="relationship-editor__content">
                    {edge.relationships.length > 1 && (
                      <div className="relationship-editor__row">
                        <label className="relationship-editor__label" htmlFor="relationship-id">
                          Edge
                        </label>
                        <select
                          id="relationship-id"
                          className="relationship-editor__select"
                          value={selectedRelationshipId ?? ''}
                          onChange={(e) => {
                            const nextId = e.target.value;
                            setSelectedRelationshipId(nextId);
                            if (activeTab === 'ai') setAnalysisKeepAliveRelationshipId(nextId);
                          }}
                        >
                          {edge.relationships.map((r) => (
                            <option key={r.id} value={r.id}>
                              {formatRelationshipLabel(r.relationshipType)} · {r.occurrenceCount} memories · w{' '}
                              {r.weight.toFixed(1)}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="relationship-editor__endpoints">
                      <div className="relationship-editor__endpoint">
                        <span className="relationship-editor__endpoint-label">Source</span>
                        <span className="relationship-editor__endpoint-value" title={sourceLabel}>
                          {sourceLabel}
                        </span>
                      </div>
                      <button
                        className="relationship-editor__swap"
                        onClick={() =>
                          setDraft((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  source_entity_id: prev.target_entity_id,
                                  target_entity_id: prev.source_entity_id,
                                }
                              : prev
                          )
                        }
                        title="Swap direction"
                        type="button"
                      >
                        <RefreshCw size={16} />
                      </button>
                      <div className="relationship-editor__endpoint">
                        <span className="relationship-editor__endpoint-label">Target</span>
                        <span className="relationship-editor__endpoint-value" title={targetLabel}>
                          {targetLabel}
                        </span>
                      </div>
                    </div>

                    {activeTab === 'edit' ? (
                      <>
                        <div className="relationship-editor__row">
                          <label className="relationship-editor__label" htmlFor="relationship-type">
                            Type
                          </label>
                          <select
                            id="relationship-type"
                            className="relationship-editor__select"
                            value={draft.relationship_type}
                            onChange={(e) =>
                              setDraft((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      relationship_type: e.target.value as RelationshipType,
                                    }
                                  : prev
                              )
                            }
                          >
                            {relationshipTypeOptions.map((type) => (
                              <option key={type} value={type}>
                                {formatRelationshipLabel(type)}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="relationship-editor__row">
                          <label className="relationship-editor__label" htmlFor="relationship-weight">
                            Weight
                          </label>
                          <div className="relationship-editor__slider">
                            <input
                              id="relationship-weight"
                              type="range"
                              min={0}
                              max={10}
                              step={0.1}
                              value={draft.weight}
                              onChange={(e) => {
                                const next = clamp(Number(e.target.value), 0, 10);
                                setDraft((prev) => (prev ? { ...prev, weight: next } : prev));
                              }}
                            />
                            <span className="relationship-editor__slider-value">{draft.weight.toFixed(1)}</span>
                          </div>
                        </div>

                        <div className="relationship-editor__actions">
                          <button
                            className="relationship-editor__btn"
                            onClick={handleClose}
                            disabled={updateRelationship.isPending || acknowledgeRelationship.isPending}
                            type="button"
                          >
                            Close
                          </button>
                          <button
                            className="relationship-editor__btn relationship-editor__btn--secondary"
                            onClick={async () => {
                              if (!selectedRelationshipId || !draft) return;
                              await acknowledgeRelationship.mutateAsync(selectedRelationshipId);
                              handleClose();
                            }}
                            disabled={!selectedRelationshipId || acknowledgeRelationship.isPending || isReviewed}
                            title={isReviewed ? 'Already reviewed' : 'Mark relationship as reviewed'}
                            type="button"
                          >
                            <Check size={16} />
                            {isReviewed ? 'Reviewed' : 'Mark Reviewed'}
                          </button>
                          <button
                            className="relationship-editor__btn relationship-editor__btn--primary"
                            onClick={async () => {
                              if (!selectedRelationshipId || !draft) return;
                              await updateRelationship.mutateAsync({
                                relationshipId: selectedRelationshipId,
                                request: draft,
                              });
                              handleClose();
                            }}
                            disabled={!canSubmit || updateRelationship.isPending}
                            type="button"
                          >
                            Apply
                          </button>
                        </div>

                        {edge.relationships.length > 1 && (
                          <div className="relationship-editor__merge">
                            <div className="relationship-editor__merge-header">
                              <div className="relationship-editor__merge-title">Merge relationships</div>
                              <div className="relationship-editor__merge-meta">{mergeIds.length} selected</div>
                            </div>
                            <div className="relationship-editor__merge-list">
                              {edge.relationships.map((r) => (
                                <label key={r.id} className="relationship-editor__merge-item">
                                  <input
                                    type="checkbox"
                                    checked={mergeSelection.has(r.id)}
                                    onChange={(e) =>
                                      setMergeSelection((prev) => {
                                        const next = new Set(prev);
                                        if (e.target.checked) next.add(r.id);
                                        else next.delete(r.id);
                                        return next;
                                      })
                                    }
                                  />
                                  <span className="relationship-editor__merge-label">
                                    {formatRelationshipLabel(r.relationshipType)}
                                  </span>
                                  <span className="relationship-editor__merge-id">
                                    {r.occurrenceCount} mem · w {r.weight.toFixed(1)}
                                  </span>
                                </label>
                              ))}
                            </div>
                            <button
                              className="relationship-editor__btn relationship-editor__btn--danger"
                              onClick={async () => {
                                if (!draft || mergeIds.length < 2) return;
                                try {
                                  await mergeRelationships.mutateAsync({
                                    relationship_ids: mergeIds,
                                    source_entity_id: draft.source_entity_id,
                                    target_entity_id: draft.target_entity_id,
                                    relationship_type: draft.relationship_type,
                                    weight: draft.weight,
                                  });
                                  handleClose();
                                } catch (err) {
                                  console.error('Failed to merge relationships', err);
                                }
                              }}
                              disabled={!canMerge || mergeRelationships.isPending}
                              title="Destructively merge selected relationships into the current draft"
                              type="button"
                            >
                              Merge Selected
                            </button>
                          </div>
                        )}
                      </>
                    ) : null}

                    {activeTab === 'evidence' ? (
                      <div className="relationship-editor__evidence">
                        {(sourceEvidenceQuery.isLoading || targetEvidenceQuery.isLoading) && (
                          <div className="relationship-editor__evidence-empty">Loading evidence…</div>
                        )}

                        {(sourceEvidenceQuery.error || targetEvidenceQuery.error) && (
                          <div className="relationship-editor__evidence-empty">
                            Failed to load evidence memories.
                          </div>
                        )}

                        {!sourceEvidenceQuery.isLoading &&
                          !targetEvidenceQuery.isLoading &&
                          !sourceEvidenceQuery.error &&
                          !targetEvidenceQuery.error &&
                          (sharedEvidence.length ? (
                            <div className="relationship-editor__evidence-list" role="list">
                              {sharedEvidence.map((memory) => (
                                <div
                                  key={memory.id}
                                  className={`relationship-editor__evidence-card ${expandedEvidenceIds.has(memory.id) ? 'is-expanded' : ''}`}
                                >
                                  <div className="relationship-editor__evidence-card-header">
                                    <div className="relationship-editor__evidence-card-title">
                                      Memory {formatShortId(memory.id)}
                                    </div>
                                    <button
                                      className="relationship-editor__evidence-card-toggle"
                                      type="button"
                                      aria-expanded={expandedEvidenceIds.has(memory.id)}
                                      onClick={() => {
                                        setExpandedEvidenceIds((prev) => {
                                          const next = new Set(prev);
                                          if (next.has(memory.id)) next.delete(memory.id);
                                          else next.add(memory.id);
                                          return next;
                                        });
                                      }}
                                    >
                                      {expandedEvidenceIds.has(memory.id) ? 'Collapse' : 'Expand'}
                                    </button>
                                  </div>
                                  <div className="relationship-editor__evidence-card-body">
                                    {memory.content}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="relationship-editor__evidence-empty">
                              No shared evidence found for this pair yet. Try Split (Preview) or ensure relationship provenance is available.
                            </div>
                          ))}
                      </div>
                    ) : null}

                    {selectedRelationshipId ? (
                      <RelationshipAnalysisPanel
                        key={`analysis-${selectedRelationshipId}`}
                        variant="modal"
                        open={open && activeTab === 'ai' && !minimized}
                        queryEnabled={
                          Boolean(selectedRelationshipId) &&
                          (activeTab === 'ai' ||
                            analysisKeepAliveRelationshipId === selectedRelationshipId)
                        }
                        relationshipId={selectedRelationshipId}
                        draft={draft}
                        baseWeight={baseDraft?.weight ?? draft?.weight ?? 0}
                        getEntityLabel={(entityId) => {
                          return (
                            nodeById.get(entityId)?.node.displayLabel ??
                            nodeById.get(entityId)?.node.entityName ??
                            entityId
                          );
                        }}
                        onPreviewWeightChange={(weight) => {
                          setDraft((prev) => (prev ? { ...prev, weight } : prev));
                        }}
                        onClose={() => setActiveTab('edit')}
                        onApplied={handleClose}
                        onMinimize={() => {
                          setMinimized(true);
                        }}
                        onNavigateToEntityId={(entityId) => {
                          onNavigateToEntityId?.(entityId);
                          setMinimized(true);
                        }}
                        onInspectMemoryId={(memoryId, inspectedRelationshipId) => {
                          onInspectMemoryId?.(memoryId, inspectedRelationshipId);
                          setMinimized(true);
                        }}
                      />
                    ) : null}
                  </section>
                </div>
              ) : (
                <div className="relationship-editor__empty">No relationship selected</div>
              )}

              {selectedRelationshipId && (
                <ClusterPreview
                  open={splitOpen}
                  relationshipId={selectedRelationshipId}
                  nodeById={nodeById}
                  onClose={() => setSplitOpen(false)}
                  onCommitted={handleClose}
                />
              )}
            </motion.div>
          </motion.div>
          {minimized ? (
            <motion.button
              key="relationship-editor-fab"
              className="relationship-editor-fab"
              initial={{ opacity: 0, scale: 0.92, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 10 }}
              transition={{ type: 'spring', stiffness: 520, damping: 34 }}
              onClick={() => setMinimized(false)}
              type="button"
              title="Restore relationship editor"
            >
              <Sparkles size={18} />
            </motion.button>
          ) : null}
        </>
      ) : null}
    </AnimatePresence>
  );
}
