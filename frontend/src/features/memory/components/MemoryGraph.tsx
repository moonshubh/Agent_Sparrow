'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';
import {
  ArrowLeft,
  Check,
  CheckSquare,
  ChevronDown,
  Eye,
  Filter,
  Hash,
  Layers,
  Link2,
  Maximize2,
  Pencil,
  RotateCcw,
  Sparkles,
  Square,
  Type,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  useAcknowledgeEntity,
  useEntityRelatedMemories,
  useMemory,
  useMemoryGraph,
  useTreeState,
} from '../hooks';
import type { TreeCameraState } from '../hooks/useTreeState';
import { ALL_ENTITY_TYPES, ENTITY_COLORS, ENTITY_LABELS } from '../types';
import type { EntityType, GraphNode, Memory, RelationshipType, TreeEdge } from '../types';
import { buildRadialTree } from '../lib/treeTransform';
import { isMemoryEdited } from '../lib/memoryFlags';
import { ConfidenceBadge } from './ConfidenceBadge';
import { SourceBadge } from './source-badge';
import { OrphanSidebar } from './OrphanSidebar';
import { ChildrenPopover } from './children-popover';
import { type TreeTransformResult } from '../types';

const MemoryTableFallback = React.lazy(() => import('./MemoryTable'));
const MemoryForm = React.lazy(() =>
  import('./MemoryForm').then((module) => ({ default: module.MemoryForm }))
);
const RelationshipEditor = React.lazy(() =>
  import('./RelationshipEditor').then((module) => ({ default: module.RelationshipEditor }))
);
const MemoryMarkdown = React.lazy(() => import('./MemoryMarkdown'));
const loadMemoryTree3D = () => import('./MemoryTree3D');
const MemoryTree3D = React.lazy(loadMemoryTree3D);

const MAX_CHILDREN_VISIBLE = 15;
const MAX_DEPTH = 6;

interface RelationshipPreviewOverride {
  source: string;
  target: string;
  relationshipType: RelationshipType;
  weight: number;
}

interface MemoryGraphProps {
  entityFilter?: readonly EntityType[];
  availableEntityTypes?: readonly EntityType[];
  searchQuery?: string;
  onNodeClick?: (node: GraphNode) => void;
  onEntityFilterChange?: (type: EntityType) => void;
  onSelectAllEntities?: () => void;
  onDeselectAllEntities?: () => void;
  onInspectMemoryFromRelationship?: (memoryId: string, relationshipId: string) => void;
  pendingRelationshipOpen?: { relationshipId: string; tab?: 'edit' | 'ai' | 'evidence' } | null;
  onPendingRelationshipOpenHandled?: () => void;
}

export default function MemoryGraph({
  entityFilter,
  availableEntityTypes,
  searchQuery,
  onNodeClick,
  onEntityFilterChange,
  onSelectAllEntities,
  onDeselectAllEntities,
  onInspectMemoryFromRelationship,
  pendingRelationshipOpen,
  onPendingRelationshipOpenHandled,
}: MemoryGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const htmlPortalRef = useRef<HTMLDivElement>(null!);
  const particleControlsRef = useRef<{
    zoomIn: () => void;
    zoomOut: () => void;
    reset: () => void;
  } | null>(null);
  const nodeDetailDragControls = useDragControls();
  const [inspectedMemoryId, setInspectedMemoryId] = useState<string | null>(null);
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    let cancelled = false;
    const preload = () => {
      if (cancelled) return;
      void loadMemoryTree3D();
    };

    const win = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (handle: number) => void;
    };

    if (win.requestIdleCallback) {
      const idleId = win.requestIdleCallback(preload, { timeout: 1200 });
      return () => {
        cancelled = true;
        win.cancelIdleCallback?.(idleId);
      };
    }

    const timeoutId = window.setTimeout(preload, 500);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, []);

  const treeState = useTreeState();
  const acknowledgeEntity = useAcknowledgeEntity();

  const selectedNodeId = treeState.selectedNodeId;
  const setSelectedNodeId = treeState.setSelectedNodeId;
  const setRootNodeId = treeState.setRootNodeId;
  const setViewMode = treeState.setViewMode;
  const setCamera = treeState.setCamera;
  const persistTreeState = treeState.persist;

  const [nodePanelView, setNodePanelView] = useState<'details' | 'related'>(
    'details'
  );
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [filterPanelExpanded, setFilterPanelExpanded] = useState(false);
  const [orphansOpen, setOrphansOpen] = useState(false);
  const [modeLegendExpanded, setModeLegendExpanded] = useState(false);
  const [childrenPopoverNodeId, setChildrenPopoverNodeId] = useState<string | null>(null);
  const [lastExpansionEvent, setLastExpansionEvent] = useState<{
    nodeId: string;
    action: 'expand' | 'collapse';
    at: number;
  } | null>(null);

  const [relationshipEditorEdge, setRelationshipEditorEdge] = useState<TreeEdge | null>(null);
  const [relationshipEditorSeed, setRelationshipEditorSeed] = useState<
    { relationshipId: string; tab?: 'edit' | 'ai' | 'evidence' } | null
  >(null);
  const [relationshipPreviewOverrides, setRelationshipPreviewOverrides] = useState<
    Record<string, RelationshipPreviewOverride>
  >({});

  const filterEntityTypes = useMemo(() => {
    if (availableEntityTypes && availableEntityTypes.length > 0) {
      return availableEntityTypes;
    }
    return ALL_ENTITY_TYPES;
  }, [availableEntityTypes]);

  // Calculate filter counts (relative to visible entity types)
  const selectedEntityCount = useMemo(() => {
    if (!entityFilter) return 0;
    const selected = new Set(entityFilter);
    return filterEntityTypes.filter((type) => selected.has(type)).length;
  }, [entityFilter, filterEntityTypes]);

  const isAllSelected =
    filterEntityTypes.length > 0 && selectedEntityCount === filterEntityTypes.length;

  // Fetch graph data with polling
  const { data, isLoading, error, refetch } = useMemoryGraph();

  const webglAvailable = useMemo(() => {
    if (typeof window === 'undefined') return true;
    try {
      const canvas = document.createElement('canvas');
      return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
    } catch {
      return false;
    }
  }, []);

  const entityTypeFilterSet = useMemo(() => {
    if (!entityFilter) return null;
    return new Set(entityFilter);
  }, [entityFilter]);

  const visualData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const overrideById = relationshipPreviewOverrides;
    if (!Object.keys(overrideById).length) return data;

    return {
      nodes: data.nodes,
      links: data.links.map((link) => {
        const override = overrideById[link.id];
        if (!override) return link;
        return {
          ...link,
          source: override.source,
          target: override.target,
          relationshipType: override.relationshipType,
          weight: override.weight,
        };
      }),
    };
  }, [data, relationshipPreviewOverrides]);

  const resolvedSelectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return visualData.nodes.find((n) => n.id === selectedNodeId) ?? null;
  }, [selectedNodeId, visualData.nodes]);

  const treeResult: TreeTransformResult | null = useMemo(() => {
    return buildRadialTree(visualData, {
      rootId: treeState.rootNodeId ?? undefined,
      maxDepth: MAX_DEPTH,
    });
  }, [treeState.rootNodeId, visualData]);

  const searchMatchIds = useMemo(() => {
    if (!treeResult) return [];
    if (!searchQuery || searchQuery.length < 2) return [];
    const query = searchQuery.toLowerCase();

    return visualData.nodes
      .filter((n) => {
        if (!treeResult.byId.has(n.id)) return false;
        return (
          n.entityName.toLowerCase().includes(query) ||
          n.displayLabel.toLowerCase().includes(query)
        );
      })
      .sort((a, b) => a.displayLabel.localeCompare(b.displayLabel))
      .map((n) => n.id);
  }, [searchQuery, treeResult, visualData.nodes]);

  const activeSearchMatchId = useMemo(() => {
    if (!selectedNodeId) return null;
    return searchMatchIds.includes(selectedNodeId) ? selectedNodeId : null;
  }, [searchMatchIds, selectedNodeId]);

  const childrenPopoverTitle = useMemo(() => {
    if (!treeResult || !childrenPopoverNodeId) return 'Connections';
    const nodeLabel = treeResult.byId.get(childrenPopoverNodeId)?.node.displayLabel;
    return nodeLabel ? `Connections · ${nodeLabel}` : 'Connections';
  }, [childrenPopoverNodeId, treeResult]);

  const handleRelationshipPreviewChange = useCallback(
    (relationshipId: string, request: { source_entity_id: string; target_entity_id: string; relationship_type: RelationshipType; weight: number }) => {
      setRelationshipPreviewOverrides((prev) => ({
        ...prev,
        [relationshipId]: {
          source: request.source_entity_id,
          target: request.target_entity_id,
          relationshipType: request.relationship_type,
          weight: request.weight,
        },
      }));
    },
    []
  );

  const handleRelationshipPreviewClear = useCallback(() => {
    setRelationshipPreviewOverrides((prev) => {
      if (Object.keys(prev).length === 0) return prev;
      return {};
    });
  }, []);

  const isEntityReviewed = useMemo(() => {
    if (!resolvedSelectedNode?.acknowledgedAt) return false;
    if (!resolvedSelectedNode.lastModifiedAt) return true;

    const acknowledgedMs = Date.parse(resolvedSelectedNode.acknowledgedAt);
    const modifiedMs = Date.parse(resolvedSelectedNode.lastModifiedAt);
    if (!Number.isFinite(acknowledgedMs) || !Number.isFinite(modifiedMs)) return true;

    return acknowledgedMs >= modifiedMs;
  }, [resolvedSelectedNode]);

  const relatedMemoriesQuery = useEntityRelatedMemories(resolvedSelectedNode?.id ?? '', {
    enabled: Boolean(resolvedSelectedNode) && nodePanelView === 'related',
    limit: 25,
  });

  const inspectedMemoryQuery = useMemory(inspectedMemoryId ?? '', {
    enabled: Boolean(inspectedMemoryId),
  });

  const formatDateTime = useCallback((dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, []);

  const handleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => { });
      return;
    }

    el.requestFullscreen?.().catch(() => { });
  }, []);

  const handleCameraStateChange = useCallback(
    (next: TreeCameraState) => {
      setCamera(next);
      persistTreeState();
    },
    [persistTreeState, setCamera]
  );

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      setSelectedNodeId(node.id);
      setNodePanelView('details');
      setRelationshipEditorSeed(null);
      setRelationshipEditorEdge(null);
      setRelationshipPreviewOverrides({});
      onNodeClick?.(node);
    },
    [onNodeClick, setSelectedNodeId]
  );

  const selectNodeById = useCallback(
    (nodeId: string) => {
      const node = visualData.nodes.find((n) => n.id === nodeId);
      if (!node) return;
      handleNodeClick(node);
    },
    [handleNodeClick, visualData.nodes]
  );

  useEffect(() => {
    if (searchMatchIds.length !== 1) return;
    const matchId = searchMatchIds[0];
    if (!matchId) return;
    if (matchId === selectedNodeId) return;

    const timeoutId = window.setTimeout(() => {
      selectNodeById(matchId);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [searchMatchIds, selectNodeById, selectedNodeId]);

  const pendingRelationshipEdge = useMemo(() => {
    if (!pendingRelationshipOpen?.relationshipId || !treeResult) return null;
    return (
      treeResult.treeEdges.find((edge) =>
        edge.relationships.some((rel) => rel.id === pendingRelationshipOpen.relationshipId)
      ) ?? null
    );
  }, [pendingRelationshipOpen?.relationshipId, treeResult]);

  const effectiveRelationshipEditorEdge = relationshipEditorEdge ?? pendingRelationshipEdge;
  const effectiveRelationshipEditorSeed = relationshipEditorEdge
    ? relationshipEditorSeed
    : pendingRelationshipOpen ?? relationshipEditorSeed;

  const toggleViewMode = useCallback(() => {
    setViewMode((prev) =>
      prev === 'celebrate_strengths' ? 'surface_gaps' : 'celebrate_strengths'
    );
  }, [setViewMode]);

  const showEmptyOverlay = !isLoading && data && data.nodes.length === 0;
  const showLoadingOverlay = isLoading && !data;

  const resetCurrentView = useCallback(() => {
    particleControlsRef.current?.reset();
  }, []);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) => {
      if (!target) return false;
      if (!(target instanceof HTMLElement)) return false;
      return Boolean(
        target.closest('input, textarea, select, [contenteditable="true"]')
      );
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;

      if (event.key === 'Escape') {
        event.preventDefault();
        setEditingMemory(null);
        setRelationshipEditorEdge(null);
        setChildrenPopoverNodeId(null);
        setRelationshipPreviewOverrides({});
        setSelectedNodeId(null);
        setNodePanelView('details');
        setOrphansOpen(false);
        setFilterPanelExpanded(false);
        return;
      }

      if (searchQuery && searchQuery.length >= 2 && searchMatchIds.length > 0) {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          if (isEditableTarget(event.target)) return;
          event.preventDefault();
          const direction = event.key === 'ArrowDown' ? 1 : -1;
          const currentIndex = selectedNodeId ? searchMatchIds.indexOf(selectedNodeId) : -1;
          const baseIndex = currentIndex >= 0 ? currentIndex : 0;
          const nextIndex =
            (baseIndex + direction + searchMatchIds.length) % searchMatchIds.length;
          const nextId = searchMatchIds[nextIndex];
          if (nextId) selectNodeById(nextId);
          return;
        }

        if (/^[1-9]$/.test(event.key)) {
          if (isEditableTarget(event.target)) return;
          const idx = Number(event.key) - 1;
          const nextId = searchMatchIds[idx];
          if (!nextId) return;
          event.preventDefault();
          selectNodeById(nextId);
          return;
        }
      }

      if (event.key.toLowerCase() === 'r') {
        if (isEditableTarget(event.target)) return;
        if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
        event.preventDefault();
        resetCurrentView();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    resetCurrentView,
    searchMatchIds,
    searchQuery,
    selectNodeById,
    selectedNodeId,
    setSelectedNodeId,
  ]);

  if (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return (
      <div className="memory-error">
        <p>Error loading graph data</p>
        <p className="memory-empty-hint">{message}</p>
        <button onClick={() => refetch()} className="memory-retry-btn">
          Retry
        </button>
      </div>
    );
  }

  if (!webglAvailable) {
    return (
      <div className="memory-table-container">
        <div className="memory-empty" style={{ marginBottom: 16 }}>
          <h3>WebGL not available</h3>
          <p className="memory-empty-hint">
            Showing the Memory Table fallback. To use the 3D visualization, enable WebGL / hardware acceleration or try a different browser.
          </p>
        </div>
        <React.Suspense
          fallback={
            <div className="memory-loading">
              <div className="memory-loading-spinner" />
              <p>Loading table…</p>
            </div>
          }
        >
          <MemoryTableFallback searchQuery={searchQuery} />
        </React.Suspense>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`memory-graph-container ${
        treeState.viewMode === 'surface_gaps'
          ? 'memory-graph-container--surface-gaps'
          : 'memory-graph-container--celebrate'
      }`}
    >
      {/* Loading overlay */}
      {showLoadingOverlay && (
        <div className="memory-graph-loading memory-graph-loading--transparent">
          <div className="memory-loading-spinner" />
          <p>Building knowledge tree...</p>
        </div>
      )}

      {/* 3D Tree View */}
      <React.Suspense
        fallback={
          <div className="memory-graph-loading memory-graph-loading--transparent">
            <div className="memory-loading-spinner" />
            <p>Loading 3D view...</p>
          </div>
        }
      >
        <MemoryTree3D
          tree={treeResult}
          selectedNodeId={resolvedSelectedNode?.id ?? null}
          viewMode={treeState.viewMode}
          showAllLabels={treeState.showAllLabels}
          expandedNodeIdSet={treeState.expandedNodeIdSet}
          maxChildrenVisible={MAX_CHILDREN_VISIBLE}
          entityTypeFilter={entityTypeFilterSet}
          searchMatchIds={searchMatchIds}
          activeSearchMatchId={activeSearchMatchId}
          initialCameraState={treeState.initialCamera}
          onCameraStateChange={handleCameraStateChange}
          onBackgroundClick={() => {
            setSelectedNodeId(null);
            setNodePanelView('details');
            setRelationshipEditorSeed(null);
            setRelationshipEditorEdge(null);
            onPendingRelationshipOpenHandled?.();
            setRelationshipPreviewOverrides({});
          }}
          htmlPortal={htmlPortalRef as React.RefObject<HTMLElement>}
          onNodeClick={handleNodeClick}
          lastExpansionEvent={lastExpansionEvent}
          onToggleExpanded={(nodeId) => {
            const action = treeState.expandedNodeIdSet.has(nodeId) ? 'collapse' : 'expand';
            treeState.toggleExpandedNode(nodeId);
            setLastExpansionEvent({ nodeId, action, at: Date.now() });
          }}
          onShowChildren={(nodeId) => setChildrenPopoverNodeId(nodeId)}
          onEdgeClick={(edge) => {
            setRelationshipEditorEdge(edge);
            setRelationshipEditorSeed(null);
            onPendingRelationshipOpenHandled?.();
            setRelationshipPreviewOverrides({});
            setChildrenPopoverNodeId(null);
          }}
          onControlsReady={(api) => {
            particleControlsRef.current = api;
          }}
          loading={showLoadingOverlay}
        />
      </React.Suspense>

      <div ref={htmlPortalRef} className="particle-tree-html-portal" />

      {/* Empty state overlay */}
      {showEmptyOverlay && (
        <div className="memory-graph-empty-overlay" onClick={(e) => e.stopPropagation()}>
          <div className="memory-graph-empty-content">
            <p>No entities yet</p>
            <p className="memory-empty-hint">
              Add a memory or run real interactions to populate the graph. If you just imported memories and this stays
              empty, verify the Supabase entity-extraction trigger + Edge Function secrets are configured.
            </p>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="memory-graph-controls" onClick={(e) => e.stopPropagation()}>
        <button onClick={() => particleControlsRef.current?.zoomIn()} title="Zoom in">
          <ZoomIn size={18} />
        </button>
        <button onClick={() => particleControlsRef.current?.zoomOut()} title="Zoom out">
          <ZoomOut size={18} />
        </button>
        <button onClick={() => particleControlsRef.current?.reset()} title="Reset view">
          <RotateCcw size={18} />
        </button>
        <button onClick={handleFullscreen} title="Fullscreen">
          <Maximize2 size={18} />
        </button>
        <div className="memory-graph-controls-divider" />
        <button
          onClick={toggleViewMode}
          title={
            treeState.viewMode === 'celebrate_strengths' ? 'Surface gaps' : 'Celebrate strengths'
          }
          className={treeState.viewMode === 'surface_gaps' ? 'active' : ''}
        >
          <Sparkles size={18} />
        </button>
        <button
          onClick={() => treeState.setShowAllLabels((prev) => !prev)}
          title={treeState.showAllLabels ? 'Hide all labels' : 'Show all labels'}
          className={treeState.showAllLabels ? 'active' : ''}
        >
          <Type size={18} />
        </button>
      </div>

      {(() => {
        const items =
          treeState.viewMode === 'celebrate_strengths'
            ? [
                { dot: 'memory-graph-mode-legend__dot--gold', label: 'Strongest connections' },
                { dot: 'memory-graph-mode-legend__dot--reviewed', label: 'Reviewed / edited' },
              ]
            : [
                { dot: 'memory-graph-mode-legend__dot--review', label: 'Needs review / updated' },
                { dot: 'memory-graph-mode-legend__dot--confidence', label: 'Low confidence (weight)' },
                { dot: 'memory-graph-mode-legend__dot--weak', label: 'Weak relationships' },
                { dot: 'memory-graph-mode-legend__dot--reviewed', label: 'Reviewed / edited' },
              ];

        const primary = items[0];
        const secondary = items.slice(1);

        return (
          <div
            className={`memory-graph-mode-legend ${modeLegendExpanded ? 'is-expanded' : 'is-collapsed'}`}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="memory-graph-mode-legend__toggle"
              onClick={(e) => {
                e.stopPropagation();
                setModeLegendExpanded((prev) => !prev);
              }}
              title={modeLegendExpanded ? 'Collapse legend' : 'Expand legend'}
            >
              <span className={`memory-graph-mode-legend__dot ${primary.dot}`} />
              <span className="memory-graph-mode-legend__toggle-label">{primary.label}</span>
              <ChevronDown
                size={14}
                className={`memory-graph-mode-legend__toggle-icon ${
                  modeLegendExpanded ? 'is-rotated' : ''
                }`}
              />
            </button>

            {modeLegendExpanded ? (
              <div className="memory-graph-mode-legend__list">
                {secondary.map((item) => (
                  <div key={item.dot} className="memory-graph-mode-legend__item">
                    <span className={`memory-graph-mode-legend__dot ${item.dot}`} />
                    {item.label}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        );
      })()}

      {/* Orphans */}
      {treeResult && treeResult.orphans.length > 0 && (
        <div onClick={(e) => e.stopPropagation()}>
          <OrphanSidebar
            orphans={treeResult.orphans}
            open={orphansOpen}
            onToggle={() => setOrphansOpen((prev) => !prev)}
            onSelect={(entityId) => {
              const node = visualData.nodes.find((n) => n.id === entityId);
              const isOrphan = treeResult.orphans.some((orphan) => orphan.id === entityId);
              if (isOrphan) {
                setRootNodeId(entityId);
              }
              if (node) {
                handleNodeClick(node);
              } else {
                setRootNodeId(entityId);
              }
              setOrphansOpen(false);
            }}
          />
        </div>
      )}

      {/* Children popover */}
      {treeResult && childrenPopoverNodeId && (
        <ChildrenPopover
          open={Boolean(childrenPopoverNodeId)}
          title={childrenPopoverTitle}
          childrenNodes={
            treeResult.byId
              .get(childrenPopoverNodeId)
              ?.children.map((c) => c.node) ?? []
          }
          onClose={() => setChildrenPopoverNodeId(null)}
          onSelectNode={(node) => {
            handleNodeClick(node);
            setChildrenPopoverNodeId(null);
          }}
        />
      )}

      {/* Relationship editor */}
      {treeResult && effectiveRelationshipEditorEdge && (
        <React.Suspense fallback={null}>
          <div onClick={(e) => e.stopPropagation()}>
            <RelationshipEditor
              key={
                effectiveRelationshipEditorEdge.relationships[0]?.id ??
                `${effectiveRelationshipEditorEdge.sourceId}-${effectiveRelationshipEditorEdge.targetId}`
              }
              open={Boolean(effectiveRelationshipEditorEdge)}
              edge={effectiveRelationshipEditorEdge}
              nodeById={treeResult.byId}
              initialRelationshipId={effectiveRelationshipEditorSeed?.relationshipId ?? null}
              initialTab={effectiveRelationshipEditorSeed?.tab}
              onClose={() => {
                setRelationshipEditorSeed(null);
                setRelationshipEditorEdge(null);
                onPendingRelationshipOpenHandled?.();
              }}
              onPreviewChange={handleRelationshipPreviewChange}
              onPreviewClear={handleRelationshipPreviewClear}
              onNavigateToEntityId={(entityId) => {
                const node = visualData.nodes.find((n) => n.id === entityId);
                if (!node) return;
                setSelectedNodeId(node.id);
                setNodePanelView('details');
                setRelationshipPreviewOverrides({});
                onNodeClick?.(node);
              }}
              onInspectMemoryId={(memoryId, inspectedRelationshipId) => {
                if (onInspectMemoryFromRelationship) {
                  onInspectMemoryFromRelationship(memoryId, inspectedRelationshipId);
                  return;
                }
                setInspectedMemoryId(memoryId);
              }}
            />
          </div>
        </React.Suspense>
      )}

      {/* Memory detail overlay (used by AI reference clicks) */}
      <AnimatePresence>
        {inspectedMemoryId && (
          <motion.div
            className="memory-detail-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setInspectedMemoryId(null)}
          >
            <motion.div
              className="memory-detail-panel"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="memory-detail-header">
                <h3>Memory</h3>
                <div className="memory-detail-header-actions">
                  {inspectedMemoryQuery.data ? (
                    <button
                      className="memory-action-icon"
                      onClick={() => {
                        const memory = inspectedMemoryQuery.data;
                        if (!memory) return;
                        setEditingMemory(memory);
                        setInspectedMemoryId(null);
                      }}
                      title="Edit memory"
                      type="button"
                    >
                      <Pencil size={14} />
                    </button>
                  ) : null}
                  <button onClick={() => setInspectedMemoryId(null)} type="button">
                    &times;
                  </button>
                </div>
              </div>

              <div className="memory-detail-content">
                {inspectedMemoryQuery.isLoading ? (
                  <div className="memory-loading">
                    <div className="memory-loading-spinner" />
                    <p>Loading memory…</p>
                  </div>
                ) : inspectedMemoryQuery.error ? (
                  <div className="memory-error">
                    <p>Error loading memory</p>
                    <p className="memory-empty-hint">
                      {inspectedMemoryQuery.error instanceof Error
                        ? inspectedMemoryQuery.error.message
                        : 'Unknown error'}
                    </p>
                  </div>
                ) : inspectedMemoryQuery.data ? (
                  <>
                    <div className="memory-detail-section">
                      <label>Content</label>
                      <div className="memory-detail-markdown">
                        <React.Suspense
                          fallback={
                            <div className="memory-loading">
                              <div className="memory-loading-spinner" />
                              <p>Loading preview…</p>
                            </div>
                          }
                        >
                          <MemoryMarkdown content={inspectedMemoryQuery.data.content} />
                        </React.Suspense>
                      </div>
                    </div>
                    <div className="memory-detail-grid">
                      <div className="memory-detail-item">
                        <label>Confidence</label>
                        <ConfidenceBadge score={inspectedMemoryQuery.data.confidence_score} />
                      </div>
                      <div className="memory-detail-item">
                        <label>Source</label>
                        <SourceBadge sourceType={inspectedMemoryQuery.data.source_type} />
                      </div>
                      <div className="memory-detail-item">
                        <label>Retrievals</label>
                        <span>{inspectedMemoryQuery.data.retrieval_count}</span>
                      </div>
                      <div className="memory-detail-item">
                        <label>Created</label>
                        <span>{formatDateTime(inspectedMemoryQuery.data.created_at)}</span>
                      </div>
                    </div>
                    {inspectedMemoryQuery.data.metadata &&
                    Object.keys(inspectedMemoryQuery.data.metadata).length > 0 ? (
                      <div className="memory-detail-section">
                        <label>Metadata</label>
                        <pre className="memory-detail-metadata">
                          {JSON.stringify(inspectedMemoryQuery.data.metadata, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="memory-empty">
                    <p>Memory not found</p>
                    <p className="memory-empty-hint">{inspectedMemoryId}</p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Collapsible Entity Filter Panel */}
      <motion.div
        className={`graph-filter-panel ${filterPanelExpanded ? 'expanded' : 'collapsed'}`}
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.3 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Panel Header - Always Visible */}
        <motion.button
          className="graph-filter-header"
          onClick={() => setFilterPanelExpanded(!filterPanelExpanded)}
          whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}
          whileTap={{ scale: 0.99 }}
        >
          <div className="graph-filter-header-left">
            <Filter size={16} />
            <span className="graph-filter-title">Entity Filters</span>
            {selectedEntityCount > 0 && (
              <span className="graph-filter-count">{selectedEntityCount}</span>
            )}
          </div>
          <motion.div
            animate={{ rotate: filterPanelExpanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronDown size={16} />
          </motion.div>
        </motion.button>

        {/* Expanded Panel Content */}
        <AnimatePresence>
          {filterPanelExpanded && (
            <motion.div
              className="graph-filter-content"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
            >
              {/* Quick Actions */}
              {onSelectAllEntities && onDeselectAllEntities && (
                <div className="graph-filter-actions">
                  <motion.button
                    className="graph-filter-action-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectAllEntities();
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    disabled={isAllSelected}
                  >
                    <CheckSquare size={14} />
                    <span>All</span>
                  </motion.button>
                  <motion.button
                    className="graph-filter-action-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeselectAllEntities();
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    disabled={selectedEntityCount === 0}
                  >
                    <Square size={14} />
                    <span>None</span>
                  </motion.button>
                </div>
              )}

              {/* Entity Checkboxes */}
              <div className="graph-filter-list">
                {filterEntityTypes.map((type, index) => {
                  const isSelected = entityFilter?.includes(type) || false;
                  const color = ENTITY_COLORS[type];
                  return (
                    <motion.button
                      key={type}
                      className={`graph-filter-item ${isSelected ? 'selected' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onEntityFilterChange?.(type);
                      }}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.02 }}
                      whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.05)' }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {/* Custom Checkbox */}
                      <div
                        className="graph-filter-checkbox"
                        style={{
                          borderColor: color,
                          backgroundColor: isSelected ? color : 'transparent',
                        }}
                      >
                        <AnimatePresence>
                          {isSelected && (
                            <motion.div
                              initial={{ scale: 0, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              exit={{ scale: 0, opacity: 0 }}
                              transition={{ duration: 0.15 }}
                            >
                              <Check size={12} color="#fff" strokeWidth={3} />
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                      <span className="graph-filter-label">
                        {ENTITY_LABELS[type] || type}
                      </span>
                    </motion.button>
                  );
                })}
              </div>

              {/* Footer Hint */}
              <div className="graph-filter-hint">
                {selectedEntityCount === 0
                  ? 'Showing all entities'
                  : `Filtering ${selectedEntityCount} type${selectedEntityCount > 1 ? 's' : ''}`}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Stats */}
      <div className="memory-graph-stats" onClick={(e) => e.stopPropagation()}>
        <span>{visualData.nodes.length} nodes</span>
        <span className="memory-graph-stats-separator">|</span>
        <span>{visualData.links.length} connections</span>
      </div>

      {/* Selected node info - Modern floating card */}
      <AnimatePresence>
        {resolvedSelectedNode && (
          <motion.div
            className={`node-detail-card ${nodePanelView === 'related' ? 'node-detail-card-related' : ''}`}
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            drag
            dragControls={nodeDetailDragControls}
            dragListener={false}
            dragMomentum={false}
            dragElastic={0.12}
            dragConstraints={containerRef}
          >
            {/* Glowing accent bar */}
            <div
              className="node-detail-accent"
              style={{
                background: `linear-gradient(90deg, ${ENTITY_COLORS[resolvedSelectedNode.entityType]}, ${ENTITY_COLORS[resolvedSelectedNode.entityType]}80)`,
              }}
            />

            {/* Header with close button */}
            <div
              className="node-detail-header"
              onPointerDown={(e) => {
                nodeDetailDragControls.start(e);
              }}
              title="Drag"
            >
              {nodePanelView === 'related' && (
                <motion.button
                  className="node-detail-back"
                  onClick={(e) => {
                    e.stopPropagation();
                    setNodePanelView('details');
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                >
                  <ArrowLeft size={16} />
                </motion.button>
              )}
              <motion.button
                className="node-detail-close"
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedNodeId(null);
                  setNodePanelView('details');
                }}
                onPointerDown={(e) => e.stopPropagation()}
                whileHover={{ scale: 1.1, rotate: 90 }}
                whileTap={{ scale: 0.9 }}
              >
                <X size={16} />
              </motion.button>
            </div>

            {nodePanelView === 'details' ? (
              <>
                {/* Entity type badge */}
                <div className="node-detail-type">
                  <span
                    className="node-detail-badge"
                    style={{
                      backgroundColor: `${ENTITY_COLORS[resolvedSelectedNode.entityType]}20`,
                      color: ENTITY_COLORS[resolvedSelectedNode.entityType],
                      borderColor: `${ENTITY_COLORS[resolvedSelectedNode.entityType]}40`,
                    }}
                  >
                    <Layers size={12} />
                    {ENTITY_LABELS[resolvedSelectedNode.entityType]}
                  </span>
                </div>

                {/* Entity name */}
                <h3 className="node-detail-name">{resolvedSelectedNode.entityName}</h3>

                {/* Stats grid */}
                <div className="node-detail-stats">
                  <div className="node-detail-stat">
                    <div className="node-detail-stat-icon">
                      <Hash size={14} />
                    </div>
                    <div className="node-detail-stat-content">
                      <span className="node-detail-stat-value">
                        {resolvedSelectedNode.occurrenceCount}
                      </span>
                      <span className="node-detail-stat-label">Occurrences</span>
                    </div>
                  </div>
                  <div className="node-detail-stat">
                    <div className="node-detail-stat-icon">
                      <Link2 size={14} />
                    </div>
                    <div className="node-detail-stat-content">
                      <span className="node-detail-stat-value">
                        {
                          visualData.links.filter(
                            (l) =>
                              l.source === resolvedSelectedNode.id ||
                              l.target === resolvedSelectedNode.id
                          ).length
                        }
                      </span>
                      <span className="node-detail-stat-label">Connections</span>
                    </div>
                  </div>
                </div>

                {/* Action button */}
                <motion.button
                  className="node-detail-action"
                  onClick={(e) => {
                    e.stopPropagation();
                    setNodePanelView('related');
                  }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Eye size={14} />
                  View Related Memories
                </motion.button>

                <motion.button
                  className={`node-detail-action ${isEntityReviewed ? 'is-acknowledged' : ''}`}
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!resolvedSelectedNode) return;
                    await acknowledgeEntity.mutateAsync(resolvedSelectedNode.id);
                  }}
                  whileHover={{ scale: isEntityReviewed ? 1 : 1.02 }}
                  whileTap={{ scale: isEntityReviewed ? 1 : 0.98 }}
                  disabled={isEntityReviewed || acknowledgeEntity.isPending}
                  title={isEntityReviewed ? 'Already reviewed' : 'Mark entity as reviewed'}
                >
                  <Check size={14} />
                  {isEntityReviewed ? 'Reviewed' : 'Mark Reviewed'}
                </motion.button>
              </>
            ) : (
              <>
                <div className="node-related-header">
                  <div className="node-related-title">
                    <span
                      className="node-detail-badge"
                      style={{
                        backgroundColor: `${ENTITY_COLORS[resolvedSelectedNode.entityType]}20`,
                        color: ENTITY_COLORS[resolvedSelectedNode.entityType],
                        borderColor: `${ENTITY_COLORS[resolvedSelectedNode.entityType]}40`,
                      }}
                    >
                      <Layers size={12} />
                      {ENTITY_LABELS[resolvedSelectedNode.entityType]}
                    </span>
                    <h3 className="node-related-entity">{resolvedSelectedNode.entityName}</h3>
                  </div>
                  <div className="node-related-meta">
                    <span className="node-related-count">
                      {relatedMemoriesQuery.data?.length ?? 0}
                    </span>
                    <span className="node-related-count-label">memories</span>
                  </div>
                </div>

                <div className="node-related-list">
                  {relatedMemoriesQuery.isLoading && (
                    <div className="node-related-loading">
                      <div className="memory-loading-spinner" />
                      <span>Loading…</span>
                    </div>
                  )}

                  {relatedMemoriesQuery.error && (
                    <div className="node-related-error">
                      <p>Failed to load related memories</p>
                      <button
                        className="memory-retry-btn"
                        onClick={() => relatedMemoriesQuery.refetch()}
                      >
                        Retry
                      </button>
                    </div>
                  )}

                  {!relatedMemoriesQuery.isLoading &&
                    !relatedMemoriesQuery.error &&
                    (relatedMemoriesQuery.data?.length ? (
                      <div className="node-related-items">
                        {relatedMemoriesQuery.data.map((memory) => (
                          <div
                            key={memory.id}
                            className={`node-related-item ${isMemoryEdited(memory) ? 'is-edited' : ''}`}
                          >
                            <div className="node-related-item-top">
                              <div className="node-related-item-badges">
                                <ConfidenceBadge score={memory.confidence_score} />
                                <SourceBadge sourceType={memory.source_type} />
                              </div>
                              <button
                                className="node-related-item-action"
                                onClick={() => setEditingMemory(memory)}
                                title="Edit memory"
                              >
                                <Pencil size={14} />
                              </button>
                            </div>
                            <p className="node-related-item-content">
                              {memory.content}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="node-related-empty">
                        <p>No related memories yet</p>
                        <p className="memory-empty-hint">
                          Related memories appear after the entity extractor links memories to entities.
                        </p>
                      </div>
                    ))}
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Memory Modal */}
      <AnimatePresence>
        {editingMemory && (
          <React.Suspense fallback={null}>
            <MemoryForm
              memory={editingMemory}
              onClose={() => setEditingMemory(null)}
              onSuccess={() => setEditingMemory(null)}
            />
          </React.Suspense>
        )}
      </AnimatePresence>
    </div>
  );
}
