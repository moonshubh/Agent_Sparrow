'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles, X } from 'lucide-react';
import {
  useSplitRelationshipCommit,
  useSplitRelationshipPreview,
} from '../hooks';
import { RELATIONSHIP_LABELS } from '../types';
import { deriveMemoryTitleFromContent } from '../lib/memoryTitle';
import type {
  RelationshipType,
  SplitRelationshipClusterSuggestion,
  SplitRelationshipPreviewResponse,
  SplitRelationshipCommitCluster,
  TreeNodeData,
} from '../types';

type EditableCluster = {
  cluster_id: number;
  name: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  weight: number;
  memory_ids: string[];
  samples: SplitRelationshipClusterSuggestion['samples'];
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatRelationshipLabel(type: RelationshipType): string {
  return RELATIONSHIP_LABELS[type] ?? type;
}

export function ClusterPreview({
  open,
  relationshipId,
  nodeById,
  onClose,
  onCommitted,
}: {
  open: boolean;
  relationshipId: string;
  nodeById: Map<string, TreeNodeData>;
  onClose: () => void;
  onCommitted?: () => void;
}) {
  const previewMutation = useSplitRelationshipPreview();
  const commitMutation = useSplitRelationshipCommit();

  const [preview, setPreview] = useState<SplitRelationshipPreviewResponse | null>(null);
  const [clusters, setClusters] = useState<EditableCluster[]>([]);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const entityLabelById = useMemo(() => {
    const getLabel = (id: string) =>
      nodeById.get(id)?.node.displayLabel ?? nodeById.get(id)?.node.entityName ?? id;
    return { getLabel };
  }, [nodeById]);

  const relationshipTypeOptions = useMemo(() => {
    return Object.keys(RELATIONSHIP_LABELS) as RelationshipType[];
  }, []);

  useEffect(() => {
    if (!open) return;

    requestIdRef.current += 1;
    const requestId = requestIdRef.current;

    previewMutation.mutate(
      {
        relationshipId,
        request: {
          max_memories: 60,
          max_clusters: 4,
          samples_per_cluster: 3,
          use_ai: true,
        },
      },
      {
        onMutate: () => {
          if (requestIdRef.current !== requestId) return;
          setError(null);
          setPreview(null);
          setClusters([]);
        },
        onSuccess: (data) => {
          if (requestIdRef.current !== requestId) return;
          setError(null);
          setPreview(data);
          setClusters(
            (data.clusters ?? []).map((cluster) => ({
              cluster_id: cluster.cluster_id,
              name: cluster.name,
              source_entity_id: cluster.source_entity_id,
              target_entity_id: cluster.target_entity_id,
              relationship_type: cluster.relationship_type,
              weight: cluster.weight,
              memory_ids: cluster.memory_ids ?? [],
              samples: cluster.samples ?? [],
            }))
          );
        },
        onError: (err: unknown) => {
          if (requestIdRef.current !== requestId) return;
          setError(err instanceof Error ? err.message : 'Failed to load split preview');
        },
      }
    );
  }, [open, previewMutation, relationshipId]);

  const existingRelationshipCount = preview?.existing_relationship_ids?.length ?? 0;

  const canCommit =
    clusters.length > 0 &&
    clusters.every((c) => c.memory_ids.length > 0) &&
    !commitMutation.isPending;

  const handleCommit = async () => {
    setError(null);
    const payloadClusters: SplitRelationshipCommitCluster[] = clusters.map((c) => ({
      name: c.name,
      source_entity_id: c.source_entity_id,
      target_entity_id: c.target_entity_id,
      relationship_type: c.relationship_type,
      weight: c.weight,
      memory_ids: c.memory_ids,
    }));

    try {
      await commitMutation.mutateAsync({
        relationshipId,
        request: { clusters: payloadClusters },
      });
      handleClose();
      onCommitted?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to commit relationship split');
    }
  };

  const handleClose = () => {
    requestIdRef.current += 1;
    setError(null);
    setPreview(null);
    setClusters([]);
    onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="cluster-preview-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={handleClose}
        >
          <motion.div
            className="cluster-preview-modal"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ type: 'spring', stiffness: 420, damping: 36 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="cluster-preview__header">
              <div className="cluster-preview__title">
                <Sparkles size={16} />
                Split Preview
              </div>
              <button
                className="cluster-preview__close"
                onClick={handleClose}
                title="Close"
              >
                <X size={16} />
              </button>
            </div>

            <div className="cluster-preview__meta">
              <div className="cluster-preview__meta-line">
                Replaces <strong>{existingRelationshipCount}</strong> existing relationship
                {existingRelationshipCount === 1 ? '' : 's'} between these entities.
              </div>
              <div className="cluster-preview__meta-line">
                {previewMutation.isPending && !preview
                  ? 'Generating preview…'
                  : preview?.used_ai
                    ? `AI-assisted labels enabled · ${preview.ai_model_id ?? 'Gemini'}`
                    : preview?.ai_error
                      ? preview.ai_error
                      : 'Heuristic labels (AI unavailable)'}
              </div>
            </div>

            <AnimatePresence>
              {!previewMutation.isPending && error && (
                <motion.div
                  className="cluster-preview__error"
                  initial={{ opacity: 0, y: -6, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: 'auto' }}
                  exit={{ opacity: 0, y: -6, height: 0 }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            {previewMutation.isPending ? (
              <div className="cluster-preview__loading">Generating preview…</div>
            ) : clusters.length === 0 ? (
              <div className="cluster-preview__empty">
                No clusterable memories found for this edge (missing provenance).
              </div>
            ) : (
              <div className="cluster-preview__list">
                {clusters.map((cluster) => {
                  const sourceLabel = entityLabelById.getLabel(cluster.source_entity_id);
                  const targetLabel = entityLabelById.getLabel(cluster.target_entity_id);

                  return (
                    <div key={cluster.cluster_id} className="cluster-preview__card">
                      <div className="cluster-preview__card-header">
                        <input
                          className="cluster-preview__name"
                          value={cluster.name}
                          onChange={(e) =>
                            setClusters((prev) =>
                              prev.map((c) =>
                                c.cluster_id === cluster.cluster_id
                                  ? { ...c, name: e.target.value }
                                  : c
                              )
                            )
                          }
                        />
                        <div className="cluster-preview__count">
                          {cluster.memory_ids.length} memory
                          {cluster.memory_ids.length === 1 ? '' : 'ies'}
                        </div>
                      </div>

                      <div className="cluster-preview__row">
                        <label className="cluster-preview__label">Type</label>
                        <select
                          className="cluster-preview__select"
                          value={cluster.relationship_type}
                          onChange={(e) =>
                            setClusters((prev) =>
                              prev.map((c) =>
                                c.cluster_id === cluster.cluster_id
                                  ? {
                                      ...c,
                                      relationship_type: e.target.value as RelationshipType,
                                    }
                                  : c
                              )
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

                      <div className="cluster-preview__row">
                        <label className="cluster-preview__label">Direction</label>
                        <div className="cluster-preview__direction">
                          <span className="cluster-preview__direction-label" title={sourceLabel}>
                            {sourceLabel}
                          </span>
                          <button
                            className="cluster-preview__swap"
                            type="button"
                            onClick={() =>
                              setClusters((prev) =>
                                prev.map((c) =>
                                  c.cluster_id === cluster.cluster_id
                                    ? {
                                        ...c,
                                        source_entity_id: c.target_entity_id,
                                        target_entity_id: c.source_entity_id,
                                      }
                                    : c
                                )
                              )
                            }
                            title="Swap direction"
                          >
                            ↔
                          </button>
                          <span className="cluster-preview__direction-label" title={targetLabel}>
                            {targetLabel}
                          </span>
                        </div>
                      </div>

                      <div className="cluster-preview__row">
                        <label className="cluster-preview__label">Weight</label>
                        <div className="cluster-preview__slider">
                          <input
                            type="range"
                            min={0}
                            max={10}
                            step={0.1}
                            value={cluster.weight}
                            onChange={(e) => {
                              const next = clamp(Number(e.target.value), 0, 10);
                              setClusters((prev) =>
                                prev.map((c) =>
                                  c.cluster_id === cluster.cluster_id
                                    ? { ...c, weight: next }
                                    : c
                                )
                              );
                            }}
                          />
                          <span className="cluster-preview__slider-value">
                            {cluster.weight.toFixed(1)}
                          </span>
                        </div>
                      </div>

                      {cluster.samples.length > 0 && (
                        <div className="cluster-preview__samples">
                          {cluster.samples.map((sample) => {
                            const title = deriveMemoryTitleFromContent(
                              sample.content_preview,
                              84
                            );

                            return (
                              <div
                                key={sample.id}
                                className="cluster-preview__sample"
                                title={sample.content_preview}
                              >
                                <div className="cluster-preview__sample-title">
                                  {title}
                                </div>
                                <div className="cluster-preview__sample-body">
                                  {sample.content_preview}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="cluster-preview__actions">
              <button
                className="cluster-preview__btn"
                onClick={handleClose}
                disabled={commitMutation.isPending}
              >
                Cancel
              </button>
              <button
                className="cluster-preview__btn cluster-preview__btn--primary"
                onClick={handleCommit}
                disabled={!canCommit}
              >
                {commitMutation.isPending ? 'Committing…' : 'Commit Split'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
