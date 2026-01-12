import { describe, expect, it } from 'vitest';
import type { GraphData, GraphLink, GraphNode, RelationshipType } from '../types';
import { buildRadialTree } from './treeTransform';

function makeNode(id: string, occurrenceCount: number = 1): GraphNode {
  return {
    id,
    entityType: 'issue',
    entityName: `Entity ${id}`,
    displayLabel: `Entity ${id}`,
    occurrenceCount,
  };
}

function makeLink({
  id,
  source,
  target,
  relationshipType,
  weight,
  occurrenceCount,
}: {
  id: string;
  source: string;
  target: string;
  relationshipType: RelationshipType;
  weight: number;
  occurrenceCount: number;
}): GraphLink {
  return { id, source, target, relationshipType, weight, occurrenceCount };
}

describe('buildRadialTree', () => {
  it('aggregates multiple directed links into one undirected tree edge', () => {
    const data: GraphData = {
      nodes: [makeNode('A'), makeNode('B'), makeNode('C'), makeNode('D')],
      links: [
        makeLink({
          id: 'r1',
          source: 'A',
          target: 'B',
          relationshipType: 'RELATED_TO',
          weight: 2,
          occurrenceCount: 1,
        }),
        makeLink({
          id: 'r2',
          source: 'B',
          target: 'A',
          relationshipType: 'AFFECTS',
          weight: 5,
          occurrenceCount: 2,
        }),
      ],
    };

    const tree = buildRadialTree(data, { rootId: 'A' });
    expect(tree).not.toBeNull();
    expect(tree?.treeEdges).toHaveLength(1);

    const edge = tree?.treeEdges[0];
    expect(edge?.sourceId).toBe('A');
    expect(edge?.targetId).toBe('B');
    expect(edge?.occurrenceCount).toBe(3);
    expect(edge?.weight).toBe(5);
    expect(new Set(edge?.relationshipTypes)).toEqual(
      new Set<RelationshipType>(['RELATED_TO', 'AFFECTS'])
    );
    expect(edge?.relationships.map((r) => r.id).sort()).toEqual(['r1', 'r2']);
  });

  it('identifies orphans outside the connected component', () => {
    const data: GraphData = {
      nodes: [makeNode('A'), makeNode('B'), makeNode('C'), makeNode('D')],
      links: [
        makeLink({
          id: 'r1',
          source: 'A',
          target: 'B',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
        makeLink({
          id: 'r2',
          source: 'B',
          target: 'C',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
      ],
    };

    const tree = buildRadialTree(data, { rootId: 'A' });
    expect(tree).not.toBeNull();
    expect(tree?.orphans.map((o) => o.id)).toEqual(['D']);
  });

  it('treats non-tree edges among visited nodes as cycle edges', () => {
    const data: GraphData = {
      nodes: [makeNode('A'), makeNode('B'), makeNode('C')],
      links: [
        makeLink({
          id: 'ab',
          source: 'A',
          target: 'B',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
        makeLink({
          id: 'bc',
          source: 'B',
          target: 'C',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
        makeLink({
          id: 'ca',
          source: 'C',
          target: 'A',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
      ],
    };

    const tree = buildRadialTree(data, { rootId: 'A' });
    expect(tree).not.toBeNull();
    expect(tree?.cycleEdges).toHaveLength(1);
    expect(new Set([tree?.cycleEdges[0]?.sourceId, tree?.cycleEdges[0]?.targetId])).toEqual(
      new Set(['B', 'C'])
    );
  });

  it('respects maxDepth when building the traversal tree', () => {
    const data: GraphData = {
      nodes: [makeNode('A'), makeNode('B'), makeNode('C')],
      links: [
        makeLink({
          id: 'ab',
          source: 'A',
          target: 'B',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
        makeLink({
          id: 'bc',
          source: 'B',
          target: 'C',
          relationshipType: 'RELATED_TO',
          weight: 1,
          occurrenceCount: 1,
        }),
      ],
    };

    const tree = buildRadialTree(data, { rootId: 'A', maxDepth: 1 });
    expect(tree).not.toBeNull();
    expect(tree?.treeEdges).toHaveLength(1);
    expect(tree?.orphans.map((o) => o.id)).toEqual(['C']);
  });
});

