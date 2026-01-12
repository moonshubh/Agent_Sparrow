import type { CycleEdge, GraphData } from '../types';

type EdgeKey = `${string}|${string}`;

function makeEdgeKey(a: string, b: string): EdgeKey {
  return (a < b ? `${a}|${b}` : `${b}|${a}`) as EdgeKey;
}

interface UndirectedEdgeInput {
  sourceId: string;
  targetId: string;
  occurrenceCount: number;
  weight: number;
}

/**
 * Find non-tree edges ("back edges") in an undirected graph using a Tarjan-style DFS.
 *
 * These edges can be rendered as cycle indicators across a tree layout.
 */
export function findCycleEdges(
  data: GraphData,
  options?: { startNodeId?: string }
): CycleEdge[] {
  const nodeIds = data.nodes.map((n) => n.id);
  const nodeIdSet = new Set(nodeIds);

  const edges: UndirectedEdgeInput[] = data.links
    .filter((l) => nodeIdSet.has(l.source) && nodeIdSet.has(l.target))
    .map((l) => ({
      sourceId: l.source,
      targetId: l.target,
      occurrenceCount: l.occurrenceCount,
      weight: l.weight,
    }));

  const adjacency = new Map<string, Array<{ neighborId: string; edge: UndirectedEdgeInput }>>();
  nodeIds.forEach((id) => adjacency.set(id, []));
  edges.forEach((edge) => {
    adjacency.get(edge.sourceId)?.push({ neighborId: edge.targetId, edge });
    adjacency.get(edge.targetId)?.push({ neighborId: edge.sourceId, edge });
  });

  const discoveryTime = new Map<string, number>();
  const parent = new Map<string, string | null>();
  const backEdges = new Map<EdgeKey, CycleEdge>();
  let time = 0;

  const visit = (startId: string) => {
    const dfs = (u: string) => {
      discoveryTime.set(u, time++);
      for (const { neighborId: v, edge } of adjacency.get(u) ?? []) {
        if (!discoveryTime.has(v)) {
          parent.set(v, u);
          dfs(v);
          continue;
        }

        const parentOfU = parent.get(u) ?? null;
        const discU = discoveryTime.get(u) ?? 0;
        const discV = discoveryTime.get(v) ?? 0;

        // Record a back edge once (the one pointing "back" in discovery time).
        if (v !== parentOfU && discV < discU) {
          const key = makeEdgeKey(u, v);
          if (!backEdges.has(key)) {
            backEdges.set(key, {
              sourceId: u,
              targetId: v,
              occurrenceCount: edge.occurrenceCount,
              weight: edge.weight,
            });
          }
        }
      }
    };

    parent.set(startId, null);
    dfs(startId);
  };

  const preferredStart = options?.startNodeId;
  if (preferredStart && nodeIdSet.has(preferredStart)) {
    visit(preferredStart);
  }

  // Cover disconnected components.
  nodeIds.forEach((id) => {
    if (!discoveryTime.has(id)) {
      visit(id);
    }
  });

  return Array.from(backEdges.values());
}

