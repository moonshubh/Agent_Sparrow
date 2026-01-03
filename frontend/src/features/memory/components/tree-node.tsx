'use client';

import { useMemo, type RefObject } from 'react';
import { Html } from '@react-three/drei';
import { Color, type Texture } from 'three';
import type { GraphNode, TreeViewMode } from '../types';
import type { LODLevel } from '../hooks/useLOD';
import type { TreeNode3D } from '../hooks/useTree3DLayout';
import { ENTITY_COLORS } from '../types';
import { FoliageCluster } from './FoliageCluster';

interface TreeNodeProps {
  node: TreeNode3D;
  hovered: boolean;
  selected: boolean;
  reviewed?: boolean;
  dimmed: boolean;
  ghosted: boolean;
  lod: LODLevel;
  showLabel: boolean;
  viewMode: TreeViewMode;
  leafTexture: Texture | null;
  htmlPortal?: RefObject<HTMLElement>;
  onClick?: (graphNode: GraphNode) => void;
  onToggleExpanded?: (nodeId: string) => void;
  onShowChildren?: (nodeId: string) => void;
  onControlsHoverChange?: (hovered: boolean) => void;
}

export function TreeNode({
  node,
  hovered,
  selected,
  reviewed,
  dimmed,
  ghosted,
  lod,
  showLabel,
  viewMode,
  leafTexture,
  htmlPortal,
  onClick,
  onToggleExpanded,
  onShowChildren,
  onControlsHoverChange,
}: TreeNodeProps) {
  const coreColor = ENTITY_COLORS[node.data.node.entityType] ?? '#6B7280';
  const baseColor = ghosted ? '#9CA3AF' : coreColor;
  const reviewedOpacity = ghosted ? 0.08 : dimmed ? 0.14 : hovered ? 0.6 : 0.38;
  const reviewedColor = '#34d399';

  const materialProps = useMemo(
    () => ({
      color: new Color(baseColor),
      roughness: 0.3,
      metalness: 0.1,
      transparent: true,
      opacity: ghosted ? (dimmed ? 0.06 : 0.1) : dimmed ? 0.18 : hovered ? 0.95 : 0.9,
      emissive: new Color(baseColor),
      emissiveIntensity: ghosted
        ? 0.015
        : selected
          ? 0.35
          : hovered
            ? 0.18
            : 0.08,
    }),
    [baseColor, dimmed, ghosted, hovered, selected]
  );

  const showControls =
    (selected || hovered) && (node.childCount > 0 || node.overflowCount > 0);

  const foliageCount = useMemo(() => {
    const multiplier = viewMode === 'celebrate_strengths' ? 1.2 : 0.6;
    const lodMultiplier = lod === 'high' ? 1 : lod === 'medium' ? 0.5 : 0;
    const visibilityMultiplier = dimmed || ghosted ? 0.45 : 1;
    const raw = Math.round(node.foliageCount * multiplier * lodMultiplier * visibilityMultiplier);
    const min = dimmed || ghosted ? 8 : 18;
    return Math.min(200, Math.max(min, raw));
  }, [dimmed, ghosted, lod, node.foliageCount, viewMode]);

  const shouldAnimateFoliage = lod === 'high' && !dimmed && !ghosted;
  const showDetail = lod !== 'low';
  const sphereDetail = lod === 'high' ? 14 : lod === 'medium' ? 10 : 8;

  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(node.data.node);
      }}
    >
      {foliageCount > 0 && showDetail && (
        <FoliageCluster
          id={node.id}
          center={node.position}
          count={foliageCount}
          freshness={node.freshness}
          isDimmed={dimmed || ghosted}
          isSelected={selected}
          viewMode={viewMode}
          leafTexture={leafTexture}
          animate={shouldAnimateFoliage}
        />
      )}

      <mesh position={[node.position.x, node.position.y, node.position.z]}>
        <sphereGeometry args={[0.26, sphereDetail, sphereDetail]} />
        <meshStandardMaterial {...materialProps} />
      </mesh>

      {selected && (
        <mesh position={[node.position.x, node.position.y, node.position.z]}>
          <torusGeometry args={[0.52, 0.06, 10, 32]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={0.6} />
        </mesh>
      )}

      {reviewed && showDetail && (
        <mesh position={[node.position.x, node.position.y, node.position.z]}>
          <torusGeometry args={[0.72, 0.045, 10, 36]} />
          <meshBasicMaterial color={reviewedColor} transparent opacity={reviewedOpacity} />
        </mesh>
      )}

      {showLabel && showDetail && (
        <Html
          position={[node.position.x, node.position.y + 1.25, node.position.z]}
          center
          portal={htmlPortal}
        >
          <div className="particle-tree-label">{node.data.node.displayLabel}</div>
        </Html>
      )}

      {hovered && showDetail && (
        <Html
          position={[node.position.x, node.position.y + 1.55, node.position.z]}
          center
          portal={htmlPortal}
        >
          <div className="particle-tree-hint">
            {node.data.node.displayLabel} · {node.data.node.entityType}
          </div>
        </Html>
      )}

      {showControls && showDetail && (
        <Html
          position={[node.position.x, node.position.y + 0.85, node.position.z]}
          center
          portal={htmlPortal}
        >
          <div
            className="particle-tree-node-controls"
            onClick={(e) => e.stopPropagation()}
            onMouseEnter={() => onControlsHoverChange?.(true)}
            onMouseLeave={() => onControlsHoverChange?.(false)}
          >
            {node.childCount > 0 && onToggleExpanded && (
              <button
                type="button"
                className="particle-tree-node-control particle-tree-node-control--expand"
                onClick={() => onToggleExpanded(node.id)}
                title={node.isExpanded ? 'Collapse' : 'Expand'}
              >
                {node.isExpanded ? '−' : '+'}
              </button>
            )}
            {node.overflowCount > 0 && onShowChildren && (
              <button
                type="button"
                className="particle-tree-node-control particle-tree-node-control--overflow"
                onClick={() => onShowChildren(node.id)}
                title="Show all connections"
              >
                +{node.overflowCount}
              </button>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}
