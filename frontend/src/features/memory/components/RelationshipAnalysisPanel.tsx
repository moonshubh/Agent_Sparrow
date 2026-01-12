'use client';

import React, { useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Minus, RefreshCw, Sparkles, Wand2, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useQuery } from '@tanstack/react-query';
import { memoryAPI } from '../lib/api';
import {
  useAcknowledgeRelationship,
  useDeleteMemory,
  useDeleteRelationship,
  useMemoryMe,
  useMergeMemoriesArbitrary,
  useMergeRelationships,
  useSplitRelationshipCommit,
  useUpdateMemory,
  useUpdateRelationship,
} from '../hooks';
import type {
  MergeMemoriesArbitraryRequest,
  RelationshipAnalysisRequest,
  RelationshipAnalysisResponse,
  RelationshipChecklistItem,
  RelationshipSuggestedAction,
  RelationshipType,
  UpdateRelationshipRequest,
} from '../types';

const EMPTY_CHECKLIST: RelationshipChecklistItem[] = [];

type ApplyActionResult = {
  actionId: string;
  title: string;
  kind: string;
  status: 'applied' | 'failed' | 'skipped';
  error?: string;
};

const UUID_RE =
  /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatShortId(id: string): string {
  if (id.length <= 16) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

function extractPrefixedIds(text: string, prefix: 'memory_id' | 'entity_id'): string[] {
  const ids = new Set<string>();
  const re = new RegExp(`\\b${prefix}=(${UUID_RE.source})\\b`, 'g');
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    ids.add(match[1]);
  }
  return Array.from(ids);
}

function getChecklistWeight(item: RelationshipChecklistItem): number {
  switch (item.category) {
    case 'evidence':
      return 2.2;
    case 'type':
      return 1.6;
    case 'direction':
      return 1.2;
    case 'entities':
      return 1.4;
    case 'hygiene':
      return 1.1;
    case 'merge':
      return 1;
    case 'split':
      return 1.3;
    case 'scope':
      return 1.2;
    default:
      return 1;
  }
}

function computeSuggestedWeight(
  baseWeight: number,
  checklist: RelationshipChecklistItem[],
  checkedIds: Set<string>
): number {
  if (checklist.length === 0) return baseWeight;
  const total = checklist.reduce((sum, item) => sum + getChecklistWeight(item), 0);
  const checked = checklist.reduce(
    (sum, item) => sum + (checkedIds.has(item.id) ? getChecklistWeight(item) : 0),
    0
  );
  const confidence = total > 0 ? checked / total : 0;
  const maxBoost = Math.min(4, Math.max(0, 10 - baseWeight));
  return Math.round(clamp(baseWeight + maxBoost * confidence, 0, 10) * 10) / 10;
}

export function RelationshipAnalysisPanel({
  open,
  queryEnabled,
  relationshipId,
  draft,
  baseWeight,
  variant = 'modal',
  getEntityLabel,
  onPreviewWeightChange,
  onClose,
  onApplied,
  onMinimize,
  onNavigateToEntityId,
  onInspectMemoryId,
}: {
  open: boolean;
  queryEnabled: boolean;
  relationshipId: string;
  draft: UpdateRelationshipRequest | null;
  baseWeight: number;
  variant?: 'modal' | 'embedded';
  getEntityLabel?: (entityId: string) => string;
  onPreviewWeightChange?: (weight: number) => void;
  onClose: () => void;
  onApplied?: () => void;
  onMinimize?: () => void;
  onNavigateToEntityId?: (entityId: string) => void;
  onInspectMemoryId?: (memoryId: string, relationshipId: string) => void;
}) {
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => new Set());
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedActionIds, setSelectedActionIds] = useState<Set<string>>(() => new Set());
  const [actionsError, setActionsError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<RelationshipSuggestedAction | null>(null);
  const [applyingActionId, setApplyingActionId] = useState<string | null>(null);
  const [applyResults, setApplyResults] = useState<ApplyActionResult[]>([]);

  const destructiveQueueRef = useRef<RelationshipSuggestedAction[]>([]);
  const destructiveQueueIndexRef = useRef(0);
  const appliedActionIdsRef = useRef<Set<string>>(new Set());

  const updateRelationship = useUpdateRelationship();
  const acknowledgeRelationship = useAcknowledgeRelationship();
  const updateMemory = useUpdateMemory();
  const deleteMemory = useDeleteMemory();
  const deleteRelationship = useDeleteRelationship();
  const mergeRelationships = useMergeRelationships();
  const splitCommit = useSplitRelationshipCommit();
  const mergeMemoriesArbitrary = useMergeMemoriesArbitrary();
  const meQuery = useMemoryMe();

  const request = useMemo<RelationshipAnalysisRequest>(
    () => ({
      max_direct_memories: 40,
      max_neighbor_edges: 6,
      max_neighbor_memories: 18,
      use_ai: true,
    }),
    []
  );

  const analysisQuery = useQuery<RelationshipAnalysisResponse>({
    queryKey: ['memory', 'relationship-analysis', relationshipId],
    queryFn: () => memoryAPI.analyzeRelationship(relationshipId, request),
    enabled: queryEnabled && Boolean(relationshipId),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 60 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const effectiveResult =
    analysisQuery.data && analysisQuery.data.relationship_id === relationshipId
      ? analysisQuery.data
      : null;

  const checklist = useMemo(
    () => effectiveResult?.checklist ?? EMPTY_CHECKLIST,
    [effectiveResult?.checklist]
  );

  const suggestedActions = useMemo<RelationshipSuggestedAction[]>(
    () => effectiveResult?.actions ?? [],
    [effectiveResult?.actions]
  );

  const referencedMemoryIds = useMemo(() => {
    const ids = new Set<string>();
    checklist.forEach((item) => {
      item.memory_ids?.forEach((mid) => ids.add(mid));
    });
    extractPrefixedIds(effectiveResult?.analysis_markdown ?? '', 'memory_id').forEach((mid) =>
      ids.add(mid)
    );
    return Array.from(ids).slice(0, 24);
  }, [checklist, effectiveResult?.analysis_markdown]);

  const referencedEntityIds = useMemo(() => {
    const ids = new Set<string>();
    checklist.forEach((item) => {
      item.entity_ids?.forEach((eid) => ids.add(eid));
    });
    extractPrefixedIds(effectiveResult?.analysis_markdown ?? '', 'entity_id').forEach((eid) =>
      ids.add(eid)
    );
    return Array.from(ids).slice(0, 24);
  }, [checklist, effectiveResult?.analysis_markdown]);

  const checklistTotals = useMemo(() => {
    if (checklist.length === 0) return { total: 0, checked: 0, confidence: 0 };

    const total = checklist.reduce((sum, item) => sum + getChecklistWeight(item), 0);
    const checked = checklist.reduce(
      (sum, item) => sum + (checkedIds.has(item.id) ? getChecklistWeight(item) : 0),
      0
    );
    const confidence = total > 0 ? checked / total : 0;
    return { total, checked, confidence };
  }, [checklist, checkedIds]);

  const recommendedWeight = useMemo(() => {
    return computeSuggestedWeight(baseWeight, checklist, checkedIds);
  }, [baseWeight, checklist, checkedIds]);

  const selectedActions = useMemo(() => {
    return suggestedActions.filter((action) => selectedActionIds.has(action.id));
  }, [selectedActionIds, suggestedActions]);

  const hasDestructiveSelected = useMemo(() => {
    return selectedActions.some((action) => action.destructive);
  }, [selectedActions]);

  const applySummary = useMemo(() => {
    const summary = { applied: 0, failed: 0, skipped: 0 };
    applyResults.forEach((result) => {
      if (result.status === 'applied') summary.applied += 1;
      if (result.status === 'failed') summary.failed += 1;
      if (result.status === 'skipped') summary.skipped += 1;
    });
    return summary;
  }, [applyResults]);

  const error = analysisQuery.error
    ? analysisQuery.error instanceof Error
      ? analysisQuery.error.message
      : 'Failed to analyze relationship'
    : null;

  const isApplyingChecklist = updateRelationship.isPending || acknowledgeRelationship.isPending;
  const isApplyingActions =
    Boolean(applyingActionId) ||
    updateRelationship.isPending ||
    updateMemory.isPending ||
    deleteMemory.isPending ||
    deleteRelationship.isPending ||
    mergeRelationships.isPending ||
    splitCommit.isPending ||
    mergeMemoriesArbitrary.isPending;

  const isLocalBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true';
  const isAdmin = isLocalBypass ? true : meQuery.data?.is_admin ?? false;
  const isBusy = analysisQuery.isFetching || isApplyingChecklist || isApplyingActions;

  const handleInspectMemory = (memoryId: string) => {
    onInspectMemoryId?.(memoryId, relationshipId);
    onMinimize?.();
  };

  const handleNavigateEntity = (entityId: string) => {
    onNavigateToEntityId?.(entityId);
    onMinimize?.();
  };

  const isRelationshipType = (value: unknown): value is RelationshipType => {
    return (
      typeof value === 'string' &&
      [
        'RESOLVED_BY',
        'AFFECTS',
        'REQUIRES',
        'CAUSED_BY',
        'REPORTED_BY',
        'WORKS_ON',
        'RELATED_TO',
        'SUPERSEDES',
      ].includes(value)
    );
  };

  const isRecord = (value: unknown): value is Record<string, unknown> => {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  };

  const parseUuidList = (value: unknown): string[] | null => {
    if (!Array.isArray(value)) return null;
    const out: string[] = [];
    value.forEach((item) => {
      if (typeof item === 'string' && item.trim()) out.push(item.trim());
    });
    return out;
  };

  const applyAction = async (action: RelationshipSuggestedAction) => {
    if (!isRecord(action.payload)) {
      throw new Error(`Invalid payload for action ${action.id}`);
    }

    switch (action.kind) {
      case 'update_relationship': {
        const relationshipId = action.payload.relationship_id;
        const source_entity_id = action.payload.source_entity_id;
        const target_entity_id = action.payload.target_entity_id;
        const relationship_type = action.payload.relationship_type;
        const weight = action.payload.weight;

        if (
          typeof relationshipId !== 'string' ||
          typeof source_entity_id !== 'string' ||
          typeof target_entity_id !== 'string' ||
          !isRelationshipType(relationship_type) ||
          typeof weight !== 'number'
        ) {
          throw new Error(`Invalid update_relationship payload for action ${action.id}`);
        }

        await updateRelationship.mutateAsync({
          relationshipId,
          request: {
            source_entity_id,
            target_entity_id,
            relationship_type,
            weight,
          },
        });
        return;
      }

      case 'merge_relationships': {
        const relationship_ids = parseUuidList(action.payload.relationship_ids);
        const source_entity_id = action.payload.source_entity_id;
        const target_entity_id = action.payload.target_entity_id;
        const relationship_type = action.payload.relationship_type;
        const weight = action.payload.weight;

        if (
          !relationship_ids ||
          typeof source_entity_id !== 'string' ||
          typeof target_entity_id !== 'string' ||
          !isRelationshipType(relationship_type) ||
          typeof weight !== 'number'
        ) {
          throw new Error(`Invalid merge_relationships payload for action ${action.id}`);
        }

        await mergeRelationships.mutateAsync({
          relationship_ids,
          source_entity_id,
          target_entity_id,
          relationship_type,
          weight,
        });
        return;
      }

      case 'delete_relationship': {
        const relationshipId = action.payload.relationship_id;
        if (typeof relationshipId !== 'string') {
          throw new Error(`Invalid delete_relationship payload for action ${action.id}`);
        }
        await deleteRelationship.mutateAsync(relationshipId);
        return;
      }

      case 'update_memory': {
        const memoryId = action.payload.memory_id;
        const content = action.payload.content;
        const metadata = action.payload.metadata;

        if (typeof memoryId !== 'string') {
          throw new Error(`Invalid update_memory payload for action ${action.id}`);
        }
        if (content !== undefined && typeof content !== 'string') {
          throw new Error(`Invalid update_memory content for action ${action.id}`);
        }
        if (metadata !== undefined && !isRecord(metadata)) {
          throw new Error(`Invalid update_memory metadata for action ${action.id}`);
        }

        await updateMemory.mutateAsync({
          memoryId,
          request: {
            content: typeof content === 'string' ? content : undefined,
            metadata: isRecord(metadata) ? metadata : undefined,
          },
        });
        return;
      }

      case 'delete_memory': {
        const memoryId = action.payload.memory_id;
        if (typeof memoryId !== 'string') {
          throw new Error(`Invalid delete_memory payload for action ${action.id}`);
        }
        await deleteMemory.mutateAsync(memoryId);
        return;
      }

      case 'merge_memories_arbitrary': {
        const keep_memory_id = action.payload.keep_memory_id;
        const merge_memory_ids = parseUuidList(action.payload.merge_memory_ids);
        const merge_content = action.payload.merge_content;

        if (typeof keep_memory_id !== 'string' || !merge_memory_ids) {
          throw new Error(`Invalid merge_memories_arbitrary payload for action ${action.id}`);
        }
        if (merge_content !== undefined && typeof merge_content !== 'string') {
          throw new Error(`Invalid merge_content for action ${action.id}`);
        }

        const request: MergeMemoriesArbitraryRequest = {
          keep_memory_id,
          merge_memory_ids,
          merge_content: typeof merge_content === 'string' ? merge_content : undefined,
        };

        await mergeMemoriesArbitrary.mutateAsync(request);
        return;
      }

      case 'split_relationship_commit': {
        const relationshipId = action.payload.relationship_id;
        const clusters = action.payload.clusters;
        if (typeof relationshipId !== 'string' || !Array.isArray(clusters)) {
          throw new Error(`Invalid split_relationship_commit payload for action ${action.id}`);
        }

        const parsedClusters = clusters
          .map((cluster) => {
            if (!isRecord(cluster)) return null;
            const source_entity_id = cluster.source_entity_id;
            const target_entity_id = cluster.target_entity_id;
            const relationship_type = cluster.relationship_type;
            const weight = cluster.weight;
            const memory_ids = parseUuidList(cluster.memory_ids);
            const name = cluster.name;

            if (
              typeof source_entity_id !== 'string' ||
              typeof target_entity_id !== 'string' ||
              !isRelationshipType(relationship_type) ||
              typeof weight !== 'number' ||
              !memory_ids
            ) {
              return null;
            }

            return {
              name: typeof name === 'string' && name.trim() ? name.trim() : null,
              source_entity_id,
              target_entity_id,
              relationship_type,
              weight,
              memory_ids,
            };
          })
          .filter((cluster): cluster is NonNullable<typeof cluster> => Boolean(cluster));

        if (parsedClusters.length === 0) {
          throw new Error(`No valid clusters provided for action ${action.id}`);
        }

        await splitCommit.mutateAsync({
          relationshipId,
          request: { clusters: parsedClusters },
        });
        return;
      }

      default: {
        const exhaustive: never = action.kind;
        throw new Error(`Unsupported action kind: ${exhaustive}`);
      }
    }
  };

  const getErrorMessage = (err: unknown): string => {
    if (err instanceof Error) return err.message;
    return 'Unknown error';
  };

  const recordApplyResult = (
    action: RelationshipSuggestedAction,
    status: ApplyActionResult['status'],
    errorMessage?: string
  ) => {
    setApplyResults((prev) => [
      ...prev,
      {
        actionId: action.id,
        title: action.title,
        kind: action.kind,
        status,
        error: errorMessage,
      },
    ]);
  };

  const applyActionSafely = async (action: RelationshipSuggestedAction) => {
    setApplyingActionId(action.id);
    try {
      await applyAction(action);
      appliedActionIdsRef.current.add(action.id);
      recordApplyResult(action, 'applied');
    } catch (err: unknown) {
      recordApplyResult(action, 'failed', getErrorMessage(err));
    } finally {
      setApplyingActionId(null);
    }
  };

  const finishApplyRun = () => {
    destructiveQueueRef.current = [];
    destructiveQueueIndexRef.current = 0;
    setConfirmAction(null);

    setSelectedActionIds((prev) => {
      const next = new Set(prev);
      appliedActionIdsRef.current.forEach((id) => next.delete(id));
      return next;
    });
  };

  const applySelectedActions = async () => {
    if (!isAdmin) {
      setActionsError('Admin access required to apply changes.');
      return;
    }

    if (selectedActions.length === 0) return;

    setActionsError(null);
    setApplyResults([]);
    appliedActionIdsRef.current = new Set();
    destructiveQueueRef.current = [];
    destructiveQueueIndexRef.current = 0;
    setConfirmAction(null);

    try {
      const nonDestructive = selectedActions.filter((action) => !action.destructive);
      const destructive = selectedActions.filter((action) => action.destructive);

      for (const action of nonDestructive) {
        await applyActionSafely(action);
      }

      if (destructive.length > 0) {
        destructiveQueueRef.current = destructive;
        destructiveQueueIndexRef.current = 0;
        setConfirmAction(destructive[0]);
        return;
      }

      finishApplyRun();
    } catch (err: unknown) {
      setActionsError(getErrorMessage(err));
      finishApplyRun();
    }
  };

  const applyNextDestructive = async () => {
    if (!confirmAction) return;

    // Apply current confirmed action
    await applyActionSafely(confirmAction);

    destructiveQueueIndexRef.current += 1;
    const next = destructiveQueueRef.current[destructiveQueueIndexRef.current] ?? null;
    if (next) {
      setConfirmAction(next);
      return;
    }
    finishApplyRun();
  };

  const skipCurrentDestructive = () => {
    if (!confirmAction) return;

    recordApplyResult(confirmAction, 'skipped');
    destructiveQueueIndexRef.current += 1;
    const next = destructiveQueueRef.current[destructiveQueueIndexRef.current] ?? null;
    if (next) {
      setConfirmAction(next);
      return;
    }
    finishApplyRun();
  };

  const cancelDestructiveQueue = () => {
    setActionsError('Stopped applying destructive actions.');
    finishApplyRun();
  };

  const panel = (
    <motion.div
      className={variant === 'embedded' ? 'relationship-analysis-embedded' : 'relationship-analysis-modal'}
      initial={
        variant === 'embedded'
          ? { opacity: 0, y: 10 }
          : { opacity: 0, scale: 0.96, y: 16 }
      }
      animate={
        variant === 'embedded' ? { opacity: 1, y: 0 } : { opacity: 1, scale: 1, y: 0 }
      }
      exit={
        variant === 'embedded'
          ? { opacity: 0, y: 10 }
          : { opacity: 0, scale: 0.96, y: 16 }
      }
      transition={{ type: 'spring', stiffness: 420, damping: 36 }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="relationship-analysis__header">
        <div className="relationship-analysis__title">
          <Sparkles size={16} />
          AI Relationship Analysis
        </div>
        <div className="relationship-analysis__header-actions">
          <button
            className="relationship-analysis__icon-btn"
            onClick={() => {
              setActionError(null);
              setCheckedIds(new Set());
              setSelectedActionIds(new Set());
              setActionsError(null);
              setApplyResults([]);
              appliedActionIdsRef.current = new Set();
              destructiveQueueRef.current = [];
              destructiveQueueIndexRef.current = 0;
              setConfirmAction(null);
              onPreviewWeightChange?.(baseWeight);
              void analysisQuery.refetch();
            }}
            disabled={isBusy}
            title="Regenerate"
            type="button"
          >
            <RefreshCw size={16} />
          </button>
          {onMinimize ? (
            <button
              className="relationship-analysis__icon-btn"
              onClick={onMinimize}
              disabled={isBusy}
              title="Minimize"
              type="button"
            >
              <Minus size={16} />
            </button>
          ) : null}
          <button
            className="relationship-analysis__icon-btn"
            onClick={onClose}
            title="Close"
            type="button"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {effectiveResult ? (
        <div className="relationship-analysis__meta">
          <div className="relationship-analysis__meta-line">
            Evidence: <strong>{effectiveResult.direct_memory_count}</strong> direct ·{' '}
            <strong>{effectiveResult.neighbor_edge_count}</strong> neighbor edges ·{' '}
            <strong>{effectiveResult.neighbor_memory_count}</strong> neighbor memories
          </div>
          <div className="relationship-analysis__meta-line">
            {effectiveResult.used_ai
              ? `Model: ${effectiveResult.ai_model_id ?? 'Gemini'}`
              : effectiveResult.ai_error
                ? effectiveResult.ai_error
                : 'AI not used.'}
          </div>
        </div>
      ) : null}

      {!analysisQuery.isFetching && error ? (
        <div className="relationship-analysis__error">{error}</div>
      ) : null}

      {!analysisQuery.isFetching && !isBusy && actionError ? (
        <div className="relationship-analysis__error">{actionError}</div>
      ) : null}

      {!analysisQuery.isFetching && !isBusy && actionsError ? (
        <div className="relationship-analysis__error">{actionsError}</div>
      ) : null}

      {applyResults.length > 0 ? (
        <div className="relationship-analysis__apply-report">
          <div className="relationship-analysis__apply-report-title">
            Apply results: {applySummary.applied} applied · {applySummary.failed} failed ·{' '}
            {applySummary.skipped} skipped
          </div>
          {applySummary.failed > 0 ? (
            <ul className="relationship-analysis__apply-report-list">
              {applyResults
                .filter((result) => result.status === 'failed')
                .map((result) => (
                  <li key={`apply-fail-${result.actionId}`}>
                    {result.title} · <code>{result.kind}</code> · {result.error ?? 'Failed'}
                  </li>
                ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {analysisQuery.isFetching ? (
        <div className="relationship-analysis__loading">Analyzing…</div>
      ) : effectiveResult ? (
        <div className="relationship-analysis__content">
          {referencedMemoryIds.length > 0 || referencedEntityIds.length > 0 ? (
            <div className="relationship-analysis__refs">
              <div className="relationship-analysis__refs-title">References</div>
              <div className="relationship-analysis__refs-list" role="list">
                {referencedEntityIds.map((entityId) => (
                  <button
                    key={`entity-${entityId}`}
                    type="button"
                    className="relationship-analysis__ref-chip relationship-analysis__ref-chip--entity"
                    onClick={() => handleNavigateEntity(entityId)}
                    disabled={!onNavigateToEntityId}
                    title={entityId}
                  >
                    {getEntityLabel ? getEntityLabel(entityId) : `Entity ${formatShortId(entityId)}`}
                  </button>
                ))}
                {referencedMemoryIds.map((memoryId) => (
                  <button
                    key={`memory-${memoryId}`}
                    type="button"
                    className="relationship-analysis__ref-chip relationship-analysis__ref-chip--memory"
                    onClick={() => handleInspectMemory(memoryId)}
                    disabled={!onInspectMemoryId}
                    title={memoryId}
                  >
                    Memory {formatShortId(memoryId)}
                  </button>
                ))}
              </div>
              <div className="relationship-analysis__refs-hint">
                Click a reference to jump, then restore from the floating button.
              </div>
            </div>
          ) : null}

          {checklist.length > 0 ? (
            <div className="relationship-analysis__checklist">
              <div className="relationship-analysis__checklist-header">
                <div className="relationship-analysis__checklist-title">Review checklist</div>
                <div className="relationship-analysis__checklist-meta">
                  Confidence {(checklistTotals.confidence * 100).toFixed(0)}% · Suggested weight{' '}
                  {recommendedWeight.toFixed(1)}
                </div>
              </div>

              <div className="relationship-analysis__checklist-list" role="list">
                {checklist.map((item) => {
                  const entityIds = item.entity_ids ?? [];
                  const memoryIds = item.memory_ids ?? [];

                  return (
                    <label key={item.id} className="relationship-analysis__checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedIds.has(item.id)}
                        onChange={() => {
                          setActionError(null);
                          const next = new Set(checkedIds);
                          if (next.has(item.id)) next.delete(item.id);
                          else next.add(item.id);
                          setCheckedIds(next);
                          onPreviewWeightChange?.(computeSuggestedWeight(baseWeight, checklist, next));
                        }}
                        disabled={isBusy}
                      />
                      <div className="relationship-analysis__checklist-text">
                        <div className="relationship-analysis__checklist-item-title">{item.title}</div>
                        {item.why ? (
                          <div className="relationship-analysis__checklist-item-why">{item.why}</div>
                        ) : null}

                        {entityIds.length > 0 || memoryIds.length > 0 ? (
                          <div className="relationship-analysis__checklist-item-refs">
                            {entityIds.map((entityId) => (
                              <button
                                key={`${item.id}-entity-${entityId}`}
                                type="button"
                                className="relationship-analysis__ref-chip relationship-analysis__ref-chip--entity"
                                onClick={() => handleNavigateEntity(entityId)}
                                disabled={!onNavigateToEntityId}
                                title={entityId}
                              >
                                {getEntityLabel ? getEntityLabel(entityId) : `Entity ${formatShortId(entityId)}`}
                              </button>
                            ))}
                            {memoryIds.map((memoryId) => (
                              <button
                                key={`${item.id}-memory-${memoryId}`}
                                type="button"
                                className="relationship-analysis__ref-chip relationship-analysis__ref-chip--memory"
                                onClick={() => handleInspectMemory(memoryId)}
                                disabled={!onInspectMemoryId}
                                title={memoryId}
                              >
                                Memory {formatShortId(memoryId)}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </label>
                  );
                })}
              </div>

              <div className="relationship-analysis__checklist-actions">
                <button
                  className="relationship-analysis__btn"
                  onClick={() => {
                    setCheckedIds(new Set());
                    setActionError(null);
                    onPreviewWeightChange?.(baseWeight);
                  }}
                  disabled={isBusy}
                  type="button"
                >
                  Reset
                </button>
                <button
                  className="relationship-analysis__btn relationship-analysis__btn--primary"
                  onClick={async () => {
                    if (!draft) return;
                    setActionError(null);
                    try {
                      await updateRelationship.mutateAsync({
                        relationshipId,
                        request: { ...draft, weight: recommendedWeight },
                      });
                      await acknowledgeRelationship.mutateAsync(relationshipId);
                      onApplied?.();
                    } catch (err: unknown) {
                      setActionError(
                        err instanceof Error ? err.message : 'Failed to apply checklist changes'
                      );
                    }
                  }}
                  disabled={!isAdmin || !draft || isBusy}
                  type="button"
                  title="Apply the suggested weight and mark this relationship as reviewed"
                >
                  <Check size={16} />
                  {isApplyingChecklist ? 'Applying…' : 'Apply & Mark Reviewed'}
                </button>
              </div>
            </div>
          ) : null}

          {suggestedActions.length > 0 ? (
            <div className="relationship-analysis__checklist relationship-analysis__checklist--actions">
              <div className="relationship-analysis__checklist-header">
                <div className="relationship-analysis__checklist-title">Suggested changes</div>
                <div className="relationship-analysis__checklist-meta">
                  {selectedActions.length} selected
                  {hasDestructiveSelected ? ' · Destructive included' : ''}
                  {!isAdmin ? ' · Admin required' : ''}
                </div>
              </div>

              <div className="relationship-analysis__checklist-list" role="list">
                {suggestedActions.map((action) => (
                  <label
                    key={action.id}
                    className="relationship-analysis__checklist-item relationship-analysis__action-item"
                  >
                    <input
                      type="checkbox"
                      checked={selectedActionIds.has(action.id)}
                      onChange={() => {
                        setActionsError(null);
                        setSelectedActionIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(action.id)) next.delete(action.id);
                          else next.add(action.id);
                          return next;
                        });
                      }}
                      disabled={!isAdmin || isBusy}
                    />
                    <div className="relationship-analysis__checklist-text">
                      <div className="relationship-analysis__checklist-item-title">
                        {action.title}
                        {applyingActionId === action.id ? (
                          <span className="relationship-analysis__action-status">Applying…</span>
                        ) : null}
                      </div>
                      <div className="relationship-analysis__checklist-item-why">
                        <code>{action.kind}</code> · Confidence{' '}
                        {(action.confidence * 100).toFixed(0)}%
                        {action.destructive ? ' · Destructive' : ''}
                      </div>

                      {action.entity_ids.length > 0 || action.memory_ids.length > 0 ? (
                        <div className="relationship-analysis__checklist-item-refs">
                          {action.entity_ids.map((entityId) => (
                            <button
                              key={`${action.id}-entity-${entityId}`}
                              type="button"
                              className="relationship-analysis__ref-chip relationship-analysis__ref-chip--entity"
                              onClick={() => handleNavigateEntity(entityId)}
                              disabled={!onNavigateToEntityId}
                              title={entityId}
                            >
                              {getEntityLabel
                                ? getEntityLabel(entityId)
                                : `Entity ${formatShortId(entityId)}`}
                            </button>
                          ))}
                          {action.memory_ids.map((memoryId) => (
                            <button
                              key={`${action.id}-memory-${memoryId}`}
                              type="button"
                              className="relationship-analysis__ref-chip relationship-analysis__ref-chip--memory"
                              onClick={() => handleInspectMemory(memoryId)}
                              disabled={!onInspectMemoryId}
                              title={memoryId}
                            >
                              Memory {formatShortId(memoryId)}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </label>
                ))}
              </div>

              <div className="relationship-analysis__checklist-actions">
                <button
                  className="relationship-analysis__btn"
                  onClick={() => {
                    setSelectedActionIds(new Set());
                    setActionsError(null);
                  }}
                  disabled={!isAdmin || isBusy}
                  type="button"
                >
                  Reset
                </button>
                <button
                  className="relationship-analysis__btn relationship-analysis__btn--primary"
                  onClick={() => {
                    if (!isAdmin) return;
                    if (selectedActions.length === 0) return;
                    setActionsError(null);
                    void applySelectedActions();
                  }}
                  disabled={!isAdmin || isBusy || selectedActions.length === 0}
                  type="button"
                  title="Apply selected changes"
                >
                  <Wand2 size={16} />
                  {isApplyingActions ? 'Applying…' : 'Apply Selected'}
                </button>
              </div>
            </div>
          ) : null}

          <div className="relationship-analysis__markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{effectiveResult.analysis_markdown}</ReactMarkdown>
          </div>
        </div>
      ) : (
        <div className="relationship-analysis__empty">No analysis available.</div>
      )}

      <AnimatePresence>
        {confirmAction ? (
          <motion.div
            className="relationship-analysis-confirm-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={cancelDestructiveQueue}
          >
            <motion.div
              className="relationship-analysis-confirm-modal"
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 420, damping: 36 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relationship-analysis-confirm__header">
                <div className="relationship-analysis-confirm__title">Confirm destructive change</div>
                <button
                  className="relationship-analysis__icon-btn"
                  onClick={cancelDestructiveQueue}
                  type="button"
                  title="Close"
                  disabled={isBusy}
                >
                  <X size={16} />
                </button>
              </div>
              <div className="relationship-analysis-confirm__body">
                <p>Confirm to apply this change (destructive).</p>
                <div>
                  <strong>{confirmAction.title}</strong>
                </div>
                <div className="relationship-analysis-confirm__meta">
                  <code>{confirmAction.kind}</code> · Confidence {(confirmAction.confidence * 100).toFixed(0)}%
                </div>
              </div>
              <div className="relationship-analysis-confirm__actions">
                <button
                  className="relationship-analysis__btn"
                  onClick={skipCurrentDestructive}
                  disabled={isBusy}
                  type="button"
                >
                  Skip
                </button>
                <button
                  className="relationship-analysis__btn relationship-analysis__btn--primary"
                  onClick={() => void applyNextDestructive()}
                  disabled={isBusy || !isAdmin}
                  type="button"
                >
                  <Wand2 size={16} />
                  Confirm & Apply
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );

  if (variant === 'embedded') {
    return <AnimatePresence>{open ? panel : null}</AnimatePresence>;
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="relationship-analysis-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          {panel}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
