'use client';

import { Html } from '@react-three/drei';
import { useMemo, useState, type RefObject } from 'react';
import * as THREE from 'three';
import { ENTITY_COLORS } from '../types';
import type { GraphNode, OrphanEntity } from '../types';
import { hashStringToUint32, mulberry32 } from '../lib/tree3DGeometry';
import { getLeafTexture } from '../lib/textureLoader';

function toTimeMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function getFreshness(node: GraphNode): 'fresh' | 'stale' {
  const acknowledgedMs = toTimeMs(node.acknowledgedAt);
  if (!acknowledgedMs) return 'fresh';

  const lastModifiedMs = toTimeMs(node.lastModifiedAt);
  if (!lastModifiedMs) return 'stale';

  return lastModifiedMs > acknowledgedMs ? 'fresh' : 'stale';
}

function mixColor(a: string, b: string, t: number): string {
  const ca = new THREE.Color(a);
  ca.lerp(new THREE.Color(b), Math.min(1, Math.max(0, t)));
  return `#${ca.getHexString()}`;
}

export function OrphanScatter({
  orphans,
  groundSize,
  htmlPortal,
  onSelect,
}: {
  orphans: OrphanEntity[];
  groundSize: number;
  htmlPortal?: RefObject<HTMLElement>;
  onSelect?: (node: GraphNode) => void;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const leafTexture = useMemo(() => getLeafTexture(), []);

  const geometry = useMemo(() => new THREE.PlaneGeometry(0.7, 0.42, 1, 1), []);

  const placements = useMemo(() => {
    const inner = Math.max(3.2, groundSize * 0.18);
    const outer = Math.max(inner + 3, groundSize * 0.42);

    return orphans.map((orphan) => {
      const rng = mulberry32(hashStringToUint32(`orphan:${orphan.id}`));
      const angle = rng() * Math.PI * 2;
      const radius = inner + (outer - inner) * Math.sqrt(rng());
      const x = Math.cos(angle) * radius;
      const z = Math.sin(angle) * radius;
      const y = 0.11 + rng() * 0.06;

      const yaw = rng() * Math.PI * 2;
      const tilt = (rng() - 0.5) * 0.35;

      const scale = 0.75 + rng() * 0.75;

      const freshness = getFreshness(orphan.node);
      const base = ENTITY_COLORS[orphan.node.entityType] ?? '#6B7280';
      const earthy = freshness === 'fresh'
        ? mixColor(base, '#4CAF50', 0.22)
        : mixColor(base, '#5D4037', 0.55);

      return {
        id: orphan.id,
        node: orphan.node,
        position: new THREE.Vector3(x, y, z),
        rotation: new THREE.Euler(-Math.PI / 2 + tilt, yaw, 0),
        scale,
        color: earthy,
        freshness,
      };
    });
  }, [groundSize, orphans]);

  const hovered = hoveredId
    ? placements.find((p) => p.id === hoveredId) ?? null
    : null;

  return (
    <group>
      {placements.map((p) => (
        <mesh
          key={p.id}
          geometry={geometry}
          position={[p.position.x, p.position.y, p.position.z]}
          rotation={[p.rotation.x, p.rotation.y, p.rotation.z]}
          scale={[p.scale, p.scale, p.scale]}
          onPointerOver={(e) => {
            e.stopPropagation();
            setHoveredId(p.id);
          }}
          onPointerOut={(e) => {
            e.stopPropagation();
            setHoveredId((prev) => (prev === p.id ? null : prev));
          }}
          onClick={(e) => {
            e.stopPropagation();
            onSelect?.(p.node);
          }}
        >
          <meshStandardMaterial
            color={p.color}
            map={leafTexture ?? undefined}
            alphaMap={leafTexture ?? undefined}
            transparent
            opacity={0.82}
            alphaTest={0.25}
            roughness={0.95}
            metalness={0.05}
            emissive={p.color}
            emissiveIntensity={0.08}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}

      {hovered && (
        <Html
          position={[hovered.position.x, hovered.position.y + 0.5, hovered.position.z]}
          center
          portal={htmlPortal}
        >
          <div className="particle-tree-hint">
            Disconnected · {hovered.node.displayLabel} · {hovered.node.entityType}
          </div>
        </Html>
      )}
    </group>
  );
}
