import { hierarchy, tree as d3Tree } from 'd3-hierarchy';
import { useMemo } from 'react';
import { Vector3 } from 'three';
import type { CycleEdge, EntityType, TreeEdge, TreeNodeData, TreeTransformResult } from '../types';
import { clamp, getParticleCount, hashStringToUint32, mulberry32 } from '../lib/tree3DGeometry';
import { spatialKMeans, type Vec3 } from '../lib/spatialClustering';

export type NodeFreshness = 'fresh' | 'stale';

export type RenderNodeKind = 'entity' | 'cluster';

export interface TreeNode3D {
  kind: 'entity';
  id: string;
  data: TreeNodeData;
  position: Vector3;
  depth: number;
  parentId: string | null;
  childCount: number;
  isExpanded: boolean;
  overflowCount: number;
  connectionCount: number;
  foliageCount: number;
  freshness: NodeFreshness;
}

export interface TreeCluster3D {
  kind: 'cluster';
  id: string;
  position: Vector3;
  depth: number;
  parentId: string | null;
  memberCount: number;
  memberNodeIds: readonly string[];
  memberTypes: ReadonlySet<EntityType>;
  isExpanded: boolean;
}

export type TreeRenderableNode3D = TreeNode3D | TreeCluster3D;

export type BranchStrengthTier = 'weak' | 'medium' | 'strong';

export type GapReason = 'review' | 'confidence' | 'weak' | null;

export interface TreeLink3D {
  key: string;
  source: TreeRenderableNode3D;
  target: TreeRenderableNode3D;
  edge: TreeEdge | null;
  occurrenceCount: number;
  weight: number;
  strength: BranchStrengthTier;
  strengthScore: number;
  needsReview: boolean;
  gapReason: GapReason;
}

export interface TreeCycle3D {
  key: string;
  edge: CycleEdge;
  source: TreeNode3D;
  target: TreeNode3D;
}

export interface TreeLayout3D {
  nodes: TreeRenderableNode3D[];
  links: TreeLink3D[];
  cycles: TreeCycle3D[];
  nodeById: Map<string, TreeNode3D>;
  renderableById: Map<string, TreeRenderableNode3D>;
  maxDepth: number;
  levelHeight: number;
  layoutRadius: number;
  trunkHeight: number;
}

function toTimeMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function getFreshness(node: TreeNodeData['node']): NodeFreshness {
  const acknowledgedMs = toTimeMs(node.acknowledgedAt);
  if (!acknowledgedMs) return 'fresh';

  const lastModifiedMs = toTimeMs(node.lastModifiedAt);
  if (!lastModifiedMs) return 'stale';

  return lastModifiedMs > acknowledgedMs ? 'fresh' : 'stale';
}

function toRankTier(rank: number, total: number): BranchStrengthTier {
  if (total <= 1) return 'medium';
  if (total === 2) return rank === 0 ? 'weak' : 'strong';

  const percentile = rank / (total - 1);
  if (percentile <= 0.25) return 'weak';
  if (percentile >= 0.75) return 'strong';
  return 'medium';
}

function getRelationshipNeedsReview(input: {
  acknowledgedAt?: string | null;
  lastModifiedAt?: string | null;
}): boolean {
  const acknowledgedMs = toTimeMs(input.acknowledgedAt ?? null);
  if (!acknowledgedMs) return true;

  const modifiedMs = toTimeMs(input.lastModifiedAt ?? null);
  if (!modifiedMs) return false;

  return modifiedMs > acknowledgedMs;
}

const DENSE_CHILDREN_THRESHOLD = 50;

function getClusterCount(childCount: number): number {
  return Math.min(7, Math.max(5, Math.ceil(childCount / 15)));
}

function makePseudoPoint(childId: string): Vec3 {
  const rng = mulberry32(hashStringToUint32(`cluster:${childId}`));
  const angle = rng() * Math.PI * 2;
  const y = (rng() - 0.5) * 0.4;
  return [Math.cos(angle), y, Math.sin(angle)];
}

type LayoutItem =
  | {
      kind: 'entity';
      id: string;
      treeNode: TreeNodeData;
      children: LayoutItem[];
    }
  | {
      kind: 'cluster';
      id: string;
      parentEntityId: string;
      memberNodes: readonly TreeNodeData[];
      memberNodeIds: readonly string[];
      memberTypes: ReadonlySet<EntityType>;
      children: LayoutItem[];
    };

export function useTree3DLayout(
  treeResult: TreeTransformResult | null,
  options: {
    expandedNodeIdSet: Set<string>;
    selectedNodeId: string | null;
    maxChildrenVisible: number;
    showAllLabels: boolean;
  }
): TreeLayout3D {
  const { expandedNodeIdSet, selectedNodeId, maxChildrenVisible, showAllLabels } = options;

  return useMemo((): TreeLayout3D => {
    if (!treeResult) {
      return {
        nodes: [],
        links: [],
        cycles: [],
        nodeById: new Map<string, TreeNode3D>(),
        renderableById: new Map<string, TreeRenderableNode3D>(),
        maxDepth: 0,
        levelHeight: 2.1,
        layoutRadius: 0,
        trunkHeight: 2.4,
      };
    }

    const effectiveExpanded = new Set(expandedNodeIdSet);
    effectiveExpanded.add(treeResult.rootId);

    const requiredChildByParentId = new Map<string, string>();
    if (selectedNodeId) {
      let cursorId: string | null = selectedNodeId;
      while (cursorId) {
        effectiveExpanded.add(cursorId);
        const cursor = treeResult.byId.get(cursorId);
        const parentId = cursor?.parentId ?? null;
        if (parentId) {
          effectiveExpanded.add(parentId);
          requiredChildByParentId.set(parentId, cursorId);
        }
        cursorId = parentId;
      }
    }

    const buildEntityItem = (node: TreeNodeData): LayoutItem => {
      if (!effectiveExpanded.has(node.id)) {
        return { kind: 'entity', id: node.id, treeNode: node, children: [] };
      }

      const requestedChildId = requiredChildByParentId.get(node.id) ?? null;
      const childCount = node.children.length;

      if (childCount >= DENSE_CHILDREN_THRESHOLD) {
        const k = getClusterCount(childCount);
        const sortedChildren = [...node.children].sort((a, b) => a.id.localeCompare(b.id));
        const clusters = spatialKMeans(sortedChildren, {
          k,
          seed: hashStringToUint32(`kmeans:${node.id}`),
          getPoint: (child) => makePseudoPoint(child.id),
        })
          .map((cluster) => {
            const memberNodes = [...cluster.items].sort((a, b) => a.id.localeCompare(b.id));
            const memberNodeIds = memberNodes.map((c) => c.id);
            const clusterHash = hashStringToUint32(
              `${node.id}|${memberNodeIds.join(',')}`
            ).toString(36);
            const id = `cluster:${node.id}:${clusterHash}`;
            const memberTypes = new Set<EntityType>(
              memberNodes.map((m) => m.node.entityType)
            );
            return { id, memberNodes, memberNodeIds, memberTypes, centroid: cluster.centroid };
          })
          .sort((a, b) => {
            const aAngle = Math.atan2(a.centroid[2], a.centroid[0]);
            const bAngle = Math.atan2(b.centroid[2], b.centroid[0]);
            return aAngle - bAngle;
          });

        // Ensure the path to the selected node stays visible even if it falls inside a cluster.
        if (requestedChildId) {
          const clusterWithRequired = clusters.find((c) => c.memberNodeIds.includes(requestedChildId));
          if (clusterWithRequired) {
            effectiveExpanded.add(clusterWithRequired.id);
          }
        }

        const clusterItems: LayoutItem[] = clusters.map((cluster) => {
          const expanded = effectiveExpanded.has(cluster.id);
          return {
            kind: 'cluster',
            id: cluster.id,
            parentEntityId: node.id,
            memberNodes: cluster.memberNodes,
            memberNodeIds: cluster.memberNodeIds,
            memberTypes: cluster.memberTypes,
            children: expanded ? cluster.memberNodes.map((m) => buildEntityItem(m)) : [],
          };
        });

        return { kind: 'entity', id: node.id, treeNode: node, children: clusterItems };
      }

      let visibleChildren = node.children.slice(0, maxChildrenVisible);
      if (requestedChildId && !visibleChildren.some((c) => c.id === requestedChildId)) {
        const requiredChild = node.children.find((c) => c.id === requestedChildId);
        if (requiredChild) {
          visibleChildren = [
            ...visibleChildren.slice(0, Math.max(0, maxChildrenVisible - 1)),
            requiredChild,
          ];
        }
      }

      return {
        kind: 'entity',
        id: node.id,
        treeNode: node,
        children: visibleChildren.map((child) => buildEntityItem(child)),
      };
    };

    const rootLayout = buildEntityItem(treeResult.root);

    const rootHierarchy = hierarchy(rootLayout, (d) => d.children);

    const descendants = rootHierarchy.descendants();
    const maxDepth = Math.max(0, ...descendants.map((d) => d.depth));
    const maxLabelLen = Math.max(0, ...descendants.map((d) => {
      if (d.data.kind !== 'entity') return 0;
      return d.data.treeNode.node.displayLabel?.length ?? 0;
    }));

    const labelScale = showAllLabels ? 1 + Math.min(1.6, maxLabelLen / 28) : 1;

    const levelHeight = showAllLabels ? 2.6 * labelScale : 2.1;
    const trunkHeight = showAllLabels ? 3.2 * labelScale : 2.4;

    // Keep expanded subtrees compact: as node density increases, reduce branch length in XZ.
    const avgPerLevel = descendants.length / Math.max(1, maxDepth + 1);
    const densityScale = clamp(1 / Math.sqrt(avgPerLevel / 12), 0.55, 1);

    const baseRadiusStep = (showAllLabels ? 3.2 * labelScale : 2.4) * densityScale;
    const layoutRadius = Math.max(5.5, (maxDepth + 1) * baseRadiusStep);

    const treeLayout = d3Tree<LayoutItem>().size([2 * Math.PI, layoutRadius]);
    if (showAllLabels) {
      treeLayout.separation((a, b) => {
        if (a.data.kind !== 'entity' || b.data.kind !== 'entity') {
          return a.parent === b.parent ? 1 : 1.8;
        }

        const aLen = a.data.treeNode.node.displayLabel?.length ?? 0;
        const bLen = b.data.treeNode.node.displayLabel?.length ?? 0;
        const maxLen = Math.max(aLen, bLen);
        const approxWidth = maxLen * 6;
        const factor = 1 + Math.min(2.6, approxWidth / 120);
        const base = a.parent === b.parent ? 1 : 1.8;
        return base * factor;
      });
    }

    const pointRoot = treeLayout(rootHierarchy);

    const TWO_PI = Math.PI * 2;
    const normalizeAngle = (angle: number) => {
      const mod = angle % TWO_PI;
      return mod < 0 ? mod + TWO_PI : mod;
    };
    const normalizeAngleDelta = (delta: number) => {
      const mod = (delta + Math.PI) % TWO_PI;
      const wrapped = mod < 0 ? mod + TWO_PI : mod;
      return wrapped - Math.PI;
    };

    const getTightenFactor = (parent: typeof pointRoot): number => {
      if (parent.depth <= 0) return 1;
      const siblingCount = parent.children?.length ?? 0;
      if (siblingCount <= 1) return 1;

      const depthTighten = clamp(0.88 - parent.depth * 0.075, 0.58, 0.92);
      const countTighten = clamp(1 - Math.max(0, siblingCount - 4) * 0.028, 0.72, 1);
      const kindTighten = parent.data.kind === 'cluster' ? 0.9 : 1;
      return clamp(depthTighten * countTighten * kindTighten, 0.54, 0.94);
    };

    const getMinSiblingDelta = (childRadial: number): number => {
      const baseArc = showAllLabels ? 1.1 * labelScale : 0.82;
      const radial = Math.max(0.0001, childRadial);
      return clamp(baseArc / radial, 0.055, 0.26);
    };

    const adjustedAngleById = new Map<string, number>();

    const assignAngles = (node: typeof pointRoot, angle: number) => {
      const nextAngle = normalizeAngle(angle);
      adjustedAngleById.set(node.data.id, nextAngle);

      if (!node.children?.length) return;

      const tighten = getTightenFactor(node);
      const childRadial = node.children[0]?.y ?? 1;
      const minDelta = getMinSiblingDelta(childRadial);

      const childDeltas = node.children.map((child) => {
        const rawDelta = normalizeAngleDelta(child.x - node.x);
        return rawDelta * tighten;
      });

      const indexed = childDeltas
        .map((delta, idx) => ({ idx, delta }))
        .sort((a, b) => a.delta - b.delta);

      for (let i = 1; i < indexed.length; i += 1) {
        const prev = indexed[i - 1];
        const cur = indexed[i];
        if (!prev || !cur) continue;
        const gap = cur.delta - prev.delta;
        if (gap < minDelta) {
          cur.delta = prev.delta + minDelta;
        }
      }

      const first = indexed[0]?.delta ?? 0;
      const last = indexed[indexed.length - 1]?.delta ?? 0;
      const centerOffset = -((first + last) / 2);

      const finalChildAngles: number[] = new Array(node.children.length).fill(0);
      for (const entry of indexed) {
        finalChildAngles[entry.idx] = nextAngle + entry.delta + centerOffset;
      }

      node.children.forEach((child, idx) => {
        assignAngles(child, finalChildAngles[idx] ?? child.x);
      });
    };

    assignAngles(pointRoot, pointRoot.x);

    const nodes: TreeRenderableNode3D[] = [];
    const nodeById = new Map<string, TreeNode3D>();
    const renderableById = new Map<string, TreeRenderableNode3D>();

    pointRoot.descendants().forEach((n) => {
      const angle = adjustedAngleById.get(n.data.id) ?? n.x;
      const radial = n.y;
      const x = Math.cos(angle - Math.PI / 2) * radial;
      const z = Math.sin(angle - Math.PI / 2) * radial;
      const y = n.depth * levelHeight + trunkHeight;

      const rng = mulberry32(hashStringToUint32(n.data.id));
      const jitterBase = showAllLabels ? 0.26 : 0.42;
      const jitterScale =
        Math.min(1, n.depth / 3) *
        (n.data.kind === 'cluster' ? jitterBase * 0.35 : jitterBase);
      const jitterX = (rng() - 0.5) * jitterScale;
      const jitterZ = (rng() - 0.5) * jitterScale;

      const renderParentId = n.parent?.data.id ?? null;

      if (n.data.kind === 'cluster') {
        const clusterNode: TreeCluster3D = {
          kind: 'cluster',
          id: n.data.id,
          position: new Vector3(x + jitterX, y, z + jitterZ),
          depth: n.depth,
          parentId: renderParentId,
          memberCount: n.data.memberNodeIds.length,
          memberNodeIds: n.data.memberNodeIds,
          memberTypes: n.data.memberTypes,
          isExpanded: effectiveExpanded.has(n.data.id),
        };

        nodes.push(clusterNode);
        renderableById.set(clusterNode.id, clusterNode);
        return;
      }

      const childCount = n.data.treeNode.children.length;
      const isExpanded = effectiveExpanded.has(n.data.id);
      const overflowCount = Math.max(0, childCount - maxChildrenVisible);
      const connectionCount = childCount + (n.data.treeNode.parentId ? 1 : 0);

      const entityNode: TreeNode3D = {
        kind: 'entity',
        id: n.data.id,
        data: n.data.treeNode,
        position: new Vector3(x + jitterX, y, z + jitterZ),
        depth: n.depth,
        parentId: renderParentId,
        childCount,
        isExpanded,
        overflowCount,
        connectionCount,
        foliageCount: getParticleCount(n.data.treeNode.node.occurrenceCount, connectionCount),
        freshness: getFreshness(n.data.treeNode.node),
      };

      nodes.push(entityNode);
      nodeById.set(entityNode.id, entityNode);
      renderableById.set(entityNode.id, entityNode);
    });

    const provisionalLinks = pointRoot
      .links()
      .map((l) => {
        const source = renderableById.get(l.source.data.id);
        const target = renderableById.get(l.target.data.id);
        if (!source || !target) return null;

        const edge = target.kind === 'entity' ? target.data.parentEdge ?? null : null;
        const occurrenceCount = edge?.occurrenceCount ?? 1;
        const weight = edge?.weight ?? 0.5;
        const weightNorm = clamp(weight, 0, 10) / 10;
        const countNorm = Math.log1p(Math.max(0, occurrenceCount));
        const rawScore = countNorm * 0.75 + weightNorm * 0.25;

        const needsReview = edge
          ? edge.relationships.some((rel) =>
              getRelationshipNeedsReview({
                acknowledgedAt: rel.acknowledgedAt ?? null,
                lastModifiedAt: rel.lastModifiedAt ?? null,
              })
            )
          : false;

        return {
          key: `${source.id}->${target.id}`,
          source,
          target,
          edge,
          occurrenceCount,
          weight,
          rawScore,
          weightNorm,
          needsReview,
        };
      })
      .filter(
        (
          link
        ): link is NonNullable<
          typeof link
        > => Boolean(link)
      );

    const sortedByStrength = [...provisionalLinks].sort((a, b) => a.rawScore - b.rawScore);
    const sortedByWeight = [...provisionalLinks].sort((a, b) => a.weightNorm - b.weightNorm);

    const strengthRankByKey = new Map<string, number>();
    sortedByStrength.forEach((l, idx) => strengthRankByKey.set(l.key, idx));

    const weightRankByKey = new Map<string, number>();
    sortedByWeight.forEach((l, idx) => weightRankByKey.set(l.key, idx));

    const linkCount = provisionalLinks.length;

    const links: TreeLink3D[] = provisionalLinks.map((link) => {
      const strengthRank = strengthRankByKey.get(link.key) ?? 0;
      const strengthScore = linkCount <= 1 ? 0.5 : strengthRank / (linkCount - 1);
      const strength = toRankTier(strengthRank, linkCount);

      const weightRank = weightRankByKey.get(link.key) ?? 0;
      const weightScore = linkCount <= 1 ? 0.5 : weightRank / (linkCount - 1);
      const lowConfidence = weightScore <= 0.2 || link.weightNorm <= 0.25;

      const gapReason: GapReason = link.needsReview
        ? 'review'
        : lowConfidence
          ? 'confidence'
          : strength === 'weak'
            ? 'weak'
            : null;

      return {
        key: link.key,
        source: link.source,
        target: link.target,
        edge: link.edge,
        occurrenceCount: link.occurrenceCount,
        weight: link.weight,
        strength,
        strengthScore,
        needsReview: link.needsReview,
        gapReason,
      };
    });

    const cycles: TreeCycle3D[] = (treeResult.cycleEdges ?? [])
      .map((edge) => {
        const source = nodeById.get(edge.sourceId);
        const target = nodeById.get(edge.targetId);
        if (!source || !target) return null;
        return {
          key: `${edge.sourceId}~${edge.targetId}`,
          edge,
          source,
          target,
        };
      })
      .filter((c): c is TreeCycle3D => Boolean(c));

    return {
      nodes,
      links,
      cycles,
      nodeById,
      renderableById,
      maxDepth,
      levelHeight,
      layoutRadius,
      trunkHeight,
    };
  }, [expandedNodeIdSet, maxChildrenVisible, selectedNodeId, showAllLabels, treeResult]);
}
