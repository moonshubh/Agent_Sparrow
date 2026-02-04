import type {
  CycleEdge,
  GraphData,
  GraphLink,
  GraphNode,
  OrphanEntity,
  RelationshipType,
  TreeEdge,
  TreeNodeData,
  TreeTransformResult,
} from "../types";

type EdgeKey = `${string}|${string}`;

function makeEdgeKey(a: string, b: string): EdgeKey {
  return (a < b ? `${a}|${b}` : `${b}|${a}`) as EdgeKey;
}

function pickDefaultRoot(
  nodes: readonly GraphNode[],
  links: readonly GraphLink[],
): string {
  if (nodes.length === 0) return "";

  const degree = new Map<string, number>();
  nodes.forEach((n) => degree.set(n.id, 0));
  links.forEach((l) => {
    degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
    degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
  });

  const sorted = [...nodes].sort((a, b) => {
    const degA = degree.get(a.id) ?? 0;
    const degB = degree.get(b.id) ?? 0;
    if (degA !== degB) return degB - degA;
    return b.occurrenceCount - a.occurrenceCount;
  });

  return sorted[0]?.id ?? nodes[0].id;
}

interface AggregatedUndirectedEdge {
  a: string;
  b: string;
  occurrenceCount: number;
  weight: number;
  relationships: Array<{
    id: string;
    relationshipType: RelationshipType;
    weight: number;
    occurrenceCount: number;
    sourceId: string;
    targetId: string;
    acknowledgedAt?: string | null;
    lastModifiedAt?: string | null;
  }>;
  relationshipTypes: Set<RelationshipType>;
}

function aggregateLinks(
  links: readonly GraphLink[],
): Map<EdgeKey, AggregatedUndirectedEdge> {
  const map = new Map<EdgeKey, AggregatedUndirectedEdge>();
  for (const link of links) {
    const key = makeEdgeKey(link.source, link.target);
    const existing = map.get(key);
    if (!existing) {
      const a = link.source < link.target ? link.source : link.target;
      const b = link.source < link.target ? link.target : link.source;
      map.set(key, {
        a,
        b,
        occurrenceCount: link.occurrenceCount,
        weight: link.weight,
        relationships: [
          {
            id: link.id,
            relationshipType: link.relationshipType,
            weight: link.weight,
            occurrenceCount: link.occurrenceCount,
            sourceId: link.source,
            targetId: link.target,
            acknowledgedAt: link.acknowledgedAt ?? null,
            lastModifiedAt: link.lastModifiedAt ?? null,
          },
        ],
        relationshipTypes: new Set([link.relationshipType]),
      });
      continue;
    }

    existing.occurrenceCount += link.occurrenceCount;
    existing.weight = Math.max(existing.weight, link.weight);
    existing.relationships.push({
      id: link.id,
      relationshipType: link.relationshipType,
      weight: link.weight,
      occurrenceCount: link.occurrenceCount,
      sourceId: link.source,
      targetId: link.target,
      acknowledgedAt: link.acknowledgedAt ?? null,
      lastModifiedAt: link.lastModifiedAt ?? null,
    });
    existing.relationshipTypes.add(link.relationshipType);
  }
  return map;
}

export function buildRadialTree(
  data: GraphData,
  options?: { rootId?: string; maxDepth?: number },
): TreeTransformResult | null {
  if (!data.nodes.length) return null;

  const nodeById = new Map<string, GraphNode>();
  data.nodes.forEach((n) => nodeById.set(n.id, n));

  const aggregatedEdges = aggregateLinks(data.links);

  const adjacency = new Map<
    string,
    Array<{ neighborId: string; edge: AggregatedUndirectedEdge }>
  >();
  data.nodes.forEach((n) => adjacency.set(n.id, []));
  aggregatedEdges.forEach((edge) => {
    adjacency.get(edge.a)?.push({ neighborId: edge.b, edge });
    adjacency.get(edge.b)?.push({ neighborId: edge.a, edge });
  });

  const requestedRootId = options?.rootId;
  const rootId =
    (requestedRootId && nodeById.has(requestedRootId) && requestedRootId) ||
    pickDefaultRoot(data.nodes, data.links);

  const visited = new Set<string>();
  const byId = new Map<string, TreeNodeData>();
  const treeEdgeKeys = new Set<EdgeKey>();
  const treeEdges: TreeEdge[] = [];

  const createNode = (
    id: string,
    parentId: string | null,
    depth: number,
    parentEdge?: TreeEdge,
  ): TreeNodeData => {
    const node = nodeById.get(id);
    if (!node) {
      throw new Error(`Missing graph node for id=${id}`);
    }
    return {
      id,
      node,
      children: [],
      parentId,
      depth,
      parentEdge,
    };
  };

  const root = createNode(rootId, null, 0);
  byId.set(rootId, root);
  visited.add(rootId);

  const queue: string[] = [rootId];
  while (queue.length) {
    const currentId = queue.shift();
    if (!currentId) break;
    const current = byId.get(currentId);
    if (!current) continue;

    if (
      typeof options?.maxDepth === "number" &&
      current.depth >= options.maxDepth
    ) {
      continue;
    }

    const neighbors = adjacency.get(currentId) ?? [];
    for (const { neighborId, edge } of neighbors) {
      if (visited.has(neighborId)) continue;

      const parentEdge: TreeEdge = {
        sourceId: currentId,
        targetId: neighborId,
        occurrenceCount: edge.occurrenceCount,
        weight: edge.weight,
        relationshipTypes: Array.from(edge.relationshipTypes.values()),
        relationships: edge.relationships.map((r) => ({
          id: r.id,
          relationshipType: r.relationshipType,
          weight: r.weight,
          occurrenceCount: r.occurrenceCount,
          sourceId: r.sourceId,
          targetId: r.targetId,
          acknowledgedAt: r.acknowledgedAt ?? null,
          lastModifiedAt: r.lastModifiedAt ?? null,
        })),
      };

      const child = createNode(
        neighborId,
        currentId,
        current.depth + 1,
        parentEdge,
      );
      current.children.push(child);
      byId.set(neighborId, child);
      visited.add(neighborId);
      queue.push(neighborId);

      treeEdgeKeys.add(makeEdgeKey(currentId, neighborId));
      treeEdges.push(parentEdge);
    }
  }

  const orphans: OrphanEntity[] = data.nodes
    .filter((n) => !visited.has(n.id))
    .map((n) => ({ id: n.id, node: n }));

  const cycleEdges: CycleEdge[] = [];
  aggregatedEdges.forEach((edge) => {
    if (!visited.has(edge.a) || !visited.has(edge.b)) return;
    const key = makeEdgeKey(edge.a, edge.b);
    if (treeEdgeKeys.has(key)) return;
    cycleEdges.push({
      sourceId: edge.a,
      targetId: edge.b,
      occurrenceCount: edge.occurrenceCount,
      weight: edge.weight,
    });
  });

  return {
    root,
    rootId,
    byId,
    treeEdges,
    cycleEdges,
    orphans,
  };
}
