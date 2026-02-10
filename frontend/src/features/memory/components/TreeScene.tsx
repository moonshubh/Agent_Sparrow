"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject,
} from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type {
  EntityType,
  GraphNode,
  TreeEdge,
  TreeTransformResult,
  TreeViewMode,
} from "../types";
import { useTree3DLayout } from "../hooks/useTree3DLayout";
import { CycleConnection } from "./CycleConnection";
import { GroundPlane } from "./GroundPlane";
import { NodeCluster } from "./NodeCluster";
import { OrphanScatter } from "./OrphanScatter";
import { SkeletonTree } from "./SkeletonTree";
import { TreeBranch } from "./TreeBranch";
import { TreeNode } from "./TreeNode";
import { TreeTrunk } from "./TreeTrunk";
import { getLeafTexture } from "../lib/textureLoader";
import { useLOD } from "../hooks/useLOD";

function toTimeMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function isRelationshipReviewed(input: {
  acknowledgedAt?: string | null;
  lastModifiedAt?: string | null;
}): boolean {
  const acknowledgedMs = toTimeMs(input.acknowledgedAt ?? null);
  if (!acknowledgedMs) return false;

  const modifiedMs = toTimeMs(input.lastModifiedAt ?? null);
  if (!modifiedMs) return true;

  return acknowledgedMs >= modifiedMs;
}

export function TreeScene({
  tree,
  selectedNodeId,
  viewMode,
  showAllLabels,
  expandedNodeIdSet,
  maxChildrenVisible,
  entityTypeFilter,
  searchMatchIds,
  activeSearchMatchId,
  onNodeClick,
  onToggleExpanded,
  onShowChildren,
  onEdgeClick,
  orbitControlsRef,
  htmlPortal,
  loading,
  lastExpansionEvent,
}: {
  tree: TreeTransformResult | null;
  selectedNodeId: string | null;
  viewMode: TreeViewMode;
  showAllLabels: boolean;
  expandedNodeIdSet: Set<string>;
  maxChildrenVisible: number;
  entityTypeFilter?: ReadonlySet<EntityType> | null;
  searchMatchIds?: readonly string[];
  activeSearchMatchId?: string | null;
  onNodeClick?: (node: GraphNode) => void;
  onToggleExpanded?: (nodeId: string) => void;
  onShowChildren?: (nodeId: string) => void;
  onEdgeClick?: (edge: TreeEdge) => void;
  orbitControlsRef?: MutableRefObject<{
    target: THREE.Vector3;
    minDistance?: number;
    maxDistance?: number;
    update: () => void;
  } | null>;
  htmlPortal?: RefObject<HTMLElement>;
  loading?: boolean;
  lastExpansionEvent?: {
    nodeId: string;
    action: "expand" | "collapse";
    at: number;
  } | null;
}) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const hoverClearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastExpansionHandledRef = useRef<number>(0);

  const cancelHoverClear = useCallback(() => {
    if (hoverClearTimerRef.current) {
      clearTimeout(hoverClearTimerRef.current);
      hoverClearTimerRef.current = null;
    }
  }, []);

  const scheduleHoverClear = useCallback(
    (nodeId: string) => {
      cancelHoverClear();
      hoverClearTimerRef.current = setTimeout(() => {
        setHoveredNodeId((prev) => (prev === nodeId ? null : prev));
      }, 90);
    },
    [cancelHoverClear],
  );

  const leafTexture = useMemo(() => getLeafTexture(), []);
  const camera = useThree((state) => state.camera);

  const flightRef = useRef<{
    startAt: number | null;
    duration: number;
    fromCamera: THREE.Vector3;
    toCamera: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
  } | null>(null);

  const layout = useTree3DLayout(tree, {
    expandedNodeIdSet,
    selectedNodeId,
    maxChildrenVisible,
    showAllLabels,
  });

  const reviewedEntityIdSet = useMemo(() => {
    if (!tree) return null;

    const reviewed = new Set<string>();
    for (const edge of tree.treeEdges) {
      if (!edge.relationships.length) continue;
      if (
        edge.relationships.some((rel) =>
          isRelationshipReviewed({
            acknowledgedAt: rel.acknowledgedAt ?? null,
            lastModifiedAt: rel.lastModifiedAt ?? null,
          }),
        )
      ) {
        reviewed.add(edge.sourceId);
        reviewed.add(edge.targetId);
      }
    }
    return reviewed;
  }, [tree]);

  const lodById = useLOD(layout.nodes, {
    highDistance: 14,
    mediumDistance: 42,
    updateIntervalSeconds: 0.2,
  });

  const ghostedById = useMemo(() => {
    if (entityTypeFilter == null) return null;

    const out = new Map<string, boolean>();
    for (const node of layout.nodes) {
      if (node.kind === "entity") {
        out.set(node.id, !entityTypeFilter.has(node.data.node.entityType));
        continue;
      }

      const hasAnyMatchingType = Array.from(node.memberTypes.values()).some(
        (t) => entityTypeFilter.has(t),
      );
      out.set(node.id, !hasAnyMatchingType);
    }
    return out;
  }, [entityTypeFilter, layout.nodes]);

  const focusNodeIdSet = useMemo(() => {
    if (!selectedNodeId) return null;
    const selected = layout.renderableById.get(selectedNodeId);
    if (!selected) return null;

    const focus = new Set<string>();
    focus.add(selectedNodeId);

    let cursorId = selected.parentId;
    while (cursorId) {
      focus.add(cursorId);
      const cursor = layout.renderableById.get(cursorId);
      cursorId = cursor?.parentId ?? null;
    }

    layout.nodes.forEach((node) => {
      if (node.parentId === selectedNodeId) focus.add(node.id);
    });

    return focus;
  }, [layout.nodes, layout.renderableById, selectedNodeId]);

  const cyclesToShow = useMemo(() => {
    if (!selectedNodeId) return [];
    return layout.cycles.filter(
      (cycle) =>
        cycle.edge.sourceId === selectedNodeId ||
        cycle.edge.targetId === selectedNodeId,
    );
  }, [layout.cycles, selectedNodeId]);

  const groundSize = useMemo(() => {
    return Math.max(30, layout.layoutRadius * 1.5);
  }, [layout.layoutRadius]);

  const hasTree = Boolean(tree) && layout.nodes.length > 0;

  const searchMarkers = useMemo(() => {
    if (!searchMatchIds || searchMatchIds.length === 0) return [];
    const max = Math.min(9, searchMatchIds.length);
    const out: Array<{ id: string; label: string; position: THREE.Vector3 }> =
      [];
    for (let idx = 0; idx < max; idx += 1) {
      const id = searchMatchIds[idx];
      if (!id) continue;
      const node = layout.nodeById.get(id);
      if (!node) continue;
      out.push({ id, label: String(idx + 1), position: node.position });
    }
    return out;
  }, [layout.nodeById, searchMatchIds]);

  useEffect(() => {
    if (!selectedNodeId) return;
    const selected = layout.nodeById.get(selectedNodeId);
    if (!selected) return;
    const controls = orbitControlsRef?.current;
    if (!controls) return;
    if (!(camera instanceof THREE.PerspectiveCamera)) return;

    const fromTarget = controls.target.clone();
    const fromCamera = camera.position.clone();
    const toTarget = selected.position.clone();

    const dir = new THREE.Vector3().subVectors(fromCamera, fromTarget);
    const currentDistance = dir.length() || 10;
    const minDistance = controls.minDistance ?? 0;
    const maxDistance = controls.maxDistance ?? Number.POSITIVE_INFINITY;
    dir.setLength(
      Math.min(maxDistance, Math.max(minDistance, currentDistance)),
    );

    const toCamera = toTarget.clone().add(dir);

    flightRef.current = {
      startAt: null,
      duration: 1.35,
      fromCamera,
      toCamera,
      fromTarget,
      toTarget,
    };
  }, [camera, layout.nodeById, orbitControlsRef, selectedNodeId]);

  useEffect(() => {
    if (!lastExpansionEvent) return;
    if (lastExpansionEvent.action !== "expand") return;
    if (lastExpansionHandledRef.current === lastExpansionEvent.at) return;
    lastExpansionHandledRef.current = lastExpansionEvent.at;

    const expandedRoot = layout.renderableById.get(lastExpansionEvent.nodeId);
    if (!expandedRoot) return;

    const controls = orbitControlsRef?.current;
    if (!controls) return;
    if (!(camera instanceof THREE.PerspectiveCamera)) return;

    const childrenByParentId = new Map<string, string[]>();
    for (const node of layout.nodes) {
      const parentId = node.parentId;
      if (!parentId) continue;
      const existing = childrenByParentId.get(parentId);
      if (existing) {
        existing.push(node.id);
      } else {
        childrenByParentId.set(parentId, [node.id]);
      }
    }

    const ids = new Set<string>();
    const queue: string[] = [expandedRoot.id];
    while (queue.length) {
      const id = queue.shift();
      if (!id) break;
      if (ids.has(id)) continue;
      ids.add(id);
      const children = childrenByParentId.get(id);
      if (children) queue.push(...children);
    }

    if (ids.size < 2) return;

    const box = new THREE.Box3();
    ids.forEach((id) => {
      const node = layout.renderableById.get(id);
      if (!node) return;
      box.expandByPoint(node.position);
    });

    if (box.isEmpty()) return;

    box.expandByScalar(2.2);

    const corners = [
      new THREE.Vector3(box.min.x, box.min.y, box.min.z),
      new THREE.Vector3(box.min.x, box.min.y, box.max.z),
      new THREE.Vector3(box.min.x, box.max.y, box.min.z),
      new THREE.Vector3(box.min.x, box.max.y, box.max.z),
      new THREE.Vector3(box.max.x, box.min.y, box.min.z),
      new THREE.Vector3(box.max.x, box.min.y, box.max.z),
      new THREE.Vector3(box.max.x, box.max.y, box.min.z),
      new THREE.Vector3(box.max.x, box.max.y, box.max.z),
    ];

    camera.updateMatrixWorld();
    const bounds = corners.reduce(
      (acc, corner) => {
        const projected = corner.clone().project(camera);
        acc.minX = Math.min(acc.minX, projected.x);
        acc.maxX = Math.max(acc.maxX, projected.x);
        acc.minY = Math.min(acc.minY, projected.y);
        acc.maxY = Math.max(acc.maxY, projected.y);
        return acc;
      },
      {
        minX: Number.POSITIVE_INFINITY,
        maxX: Number.NEGATIVE_INFINITY,
        minY: Number.POSITIVE_INFINITY,
        maxY: Number.NEGATIVE_INFINITY,
      },
    );

    const margin = 0.92;
    const alreadyFits =
      bounds.minX >= -margin &&
      bounds.maxX <= margin &&
      bounds.minY >= -margin &&
      bounds.maxY <= margin;

    if (alreadyFits) return;

    const sphere = new THREE.Sphere();
    box.getBoundingSphere(sphere);

    const fov = (camera.fov * Math.PI) / 180;
    const aspect = camera.aspect || 1;
    const hFov = 2 * Math.atan(Math.tan(fov / 2) * aspect);
    const distV = sphere.radius / Math.sin(fov / 2);
    const distH = sphere.radius / Math.sin(hFov / 2);
    const desiredDistance = Math.max(distV, distH);
    const minDistance = controls.minDistance ?? 0;
    const maxDistance = controls.maxDistance ?? Number.POSITIVE_INFINITY;
    const distance = Math.min(
      maxDistance,
      Math.max(minDistance, desiredDistance),
    );

    const fromTarget = controls.target.clone();
    const fromCamera = camera.position.clone();
    const toTarget = sphere.center.clone();

    const dir = new THREE.Vector3().subVectors(fromCamera, fromTarget);
    if (dir.lengthSq() < 1e-4) dir.set(0, 0.35, 1);
    dir.normalize().multiplyScalar(distance);
    const toCamera = toTarget.clone().add(dir);

    flightRef.current = {
      startAt: null,
      duration: 1.05,
      fromCamera,
      toCamera,
      fromTarget,
      toTarget,
    };
  }, [
    camera,
    lastExpansionEvent,
    layout.nodes,
    layout.renderableById,
    orbitControlsRef,
  ]);

  useFrame((state) => {
    const flight = flightRef.current;
    const controls = orbitControlsRef?.current;
    if (!flight || !controls) return;
    if (!(camera instanceof THREE.PerspectiveCamera)) return;

    if (flight.startAt === null) {
      flight.startAt = state.clock.elapsedTime;
    }

    const t = (state.clock.elapsedTime - flight.startAt) / flight.duration;
    const clamped = Math.min(1, Math.max(0, t));
    const eased =
      clamped < 0.5
        ? 4 * clamped * clamped * clamped
        : 1 - Math.pow(-2 * clamped + 2, 3) / 2;

    camera.position.lerpVectors(flight.fromCamera, flight.toCamera, eased);
    controls.target.lerpVectors(flight.fromTarget, flight.toTarget, eased);
    controls.update();

    if (clamped >= 1) {
      flightRef.current = null;
    }
  });

  useEffect(() => {
    return () => {
      cancelHoverClear();
    };
  }, [cancelHoverClear]);

  return (
    <>
      <GroundPlane size={groundSize} />

      {tree?.orphans?.length ? (
        <OrphanScatter
          orphans={tree.orphans}
          groundSize={groundSize}
          htmlPortal={htmlPortal}
          onSelect={onNodeClick}
        />
      ) : null}

      {loading && !hasTree ? <SkeletonTree /> : null}

      {hasTree ? (
        <>
          <TreeTrunk height={layout.trunkHeight} />

          {layout.links.map((link) => {
            const isDimmed =
              Boolean(focusNodeIdSet) &&
              !(
                focusNodeIdSet?.has(link.source.id) &&
                focusNodeIdSet?.has(link.target.id)
              );

            return (
              <TreeBranch
                key={link.key}
                link={link}
                maxDepth={layout.maxDepth}
                viewMode={viewMode}
                isDimmed={isDimmed}
                isGhosted={Boolean(
                  ghostedById?.get(link.source.id) ||
                  ghostedById?.get(link.target.id),
                )}
                onClick={(edge) => onEdgeClick?.(edge)}
              />
            );
          })}

          {cyclesToShow.map((cycle) => (
            <CycleConnection
              key={cycle.key}
              points={[
                [
                  cycle.source.position.x,
                  cycle.source.position.y + 0.2,
                  cycle.source.position.z,
                ],
                [
                  cycle.target.position.x,
                  cycle.target.position.y + 0.2,
                  cycle.target.position.z,
                ],
              ]}
            />
          ))}

          {layout.nodes.map((node) => {
            const selected = node.id === selectedNodeId;
            const hovered = node.id === hoveredNodeId;
            const isRoot = node.id === tree!.rootId;
            const showLabel = showAllLabels || selected || isRoot;

            const dimmed =
              Boolean(focusNodeIdSet) && !focusNodeIdSet?.has(node.id);

            const ghosted = ghostedById?.get(node.id) ?? false;

            const lod = lodById.get(node.id) ?? "high";

            return (
              <group
                key={`node-${node.id}`}
                onPointerOver={(e) => {
                  e.stopPropagation();
                  cancelHoverClear();
                  setHoveredNodeId(node.id);
                }}
                onPointerOut={(e) => {
                  e.stopPropagation();
                  scheduleHoverClear(node.id);
                }}
              >
                {node.kind === "cluster" ? (
                  <NodeCluster
                    cluster={node}
                    hovered={hovered}
                    dimmed={dimmed}
                    ghosted={ghosted}
                    lod={lod}
                    showLabel={showAllLabels || hovered}
                    htmlPortal={htmlPortal}
                    onToggleExpanded={onToggleExpanded}
                    onControlsHoverChange={(isHovering) => {
                      if (isHovering) {
                        cancelHoverClear();
                        setHoveredNodeId(node.id);
                      } else {
                        scheduleHoverClear(node.id);
                      }
                    }}
                  />
                ) : (
                  <TreeNode
                    node={node}
                    hovered={hovered}
                    selected={selected}
                    reviewed={reviewedEntityIdSet?.has(node.id) ?? false}
                    editedInfluenced={Boolean(node.data.node.hasEditedMemory)}
                    dimmed={dimmed}
                    ghosted={ghosted}
                    lod={lod}
                    showLabel={showLabel}
                    leafTexture={leafTexture}
                    viewMode={viewMode}
                    htmlPortal={htmlPortal}
                    onClick={onNodeClick}
                    onToggleExpanded={onToggleExpanded}
                    onShowChildren={onShowChildren}
                    onControlsHoverChange={(isHovering) => {
                      if (isHovering) {
                        cancelHoverClear();
                        setHoveredNodeId(node.id);
                      } else {
                        scheduleHoverClear(node.id);
                      }
                    }}
                  />
                )}
              </group>
            );
          })}

          {searchMarkers.map((marker) => (
            <Html
              key={`search-marker-${marker.id}`}
              position={[
                marker.position.x,
                marker.position.y + 2.2,
                marker.position.z,
              ]}
              center
              portal={htmlPortal}
            >
              <div
                className={`particle-tree-search-marker ${
                  marker.id === activeSearchMatchId ? "is-active" : ""
                }`}
              >
                {marker.label}
              </div>
            </Html>
          ))}
        </>
      ) : null}
    </>
  );
}
