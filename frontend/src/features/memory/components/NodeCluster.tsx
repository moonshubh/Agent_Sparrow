"use client";

import { Html } from "@react-three/drei";
import { useMemo, type RefObject } from "react";
import * as THREE from "three";
import type { LODLevel } from "../hooks/useLOD";
import type { TreeCluster3D } from "../hooks/useTree3DLayout";

const CLUSTER_COLOR = new THREE.Color("#22d3ee");

export function NodeCluster({
  cluster,
  hovered,
  dimmed,
  ghosted,
  lod,
  showLabel,
  htmlPortal,
  onToggleExpanded,
  onControlsHoverChange,
}: {
  cluster: TreeCluster3D;
  hovered: boolean;
  dimmed: boolean;
  ghosted: boolean;
  lod: LODLevel;
  showLabel: boolean;
  htmlPortal?: RefObject<HTMLElement>;
  onToggleExpanded?: (clusterId: string) => void;
  onControlsHoverChange?: (hovered: boolean) => void;
}) {
  const opacity = ghosted ? 0.12 : dimmed ? 0.18 : hovered ? 0.95 : 0.85;
  const emissiveIntensity = ghosted
    ? 0.02
    : dimmed
      ? 0.05
      : hovered
        ? 0.55
        : 0.28;

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: new THREE.Color("#0b1220"),
        roughness: 0.4,
        metalness: 0.15,
        transparent: true,
        opacity,
        emissive: CLUSTER_COLOR,
        emissiveIntensity,
      }),
    [emissiveIntensity, opacity],
  );

  const glowMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: CLUSTER_COLOR,
        transparent: true,
        opacity: ghosted ? 0.06 : hovered ? 0.22 : 0.14,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    [ghosted, hovered],
  );

  const radius = lod === "low" ? 0.26 : lod === "medium" ? 0.32 : 0.36;

  return (
    <group
      position={[cluster.position.x, cluster.position.y, cluster.position.z]}
      onClick={(e) => {
        e.stopPropagation();
        onToggleExpanded?.(cluster.id);
      }}
    >
      <mesh>
        <icosahedronGeometry args={[radius, 1]} />
        <primitive object={material} attach="material" />
      </mesh>

      <mesh scale={1.18}>
        <icosahedronGeometry args={[radius, 0]} />
        <primitive object={glowMaterial} attach="material" />
      </mesh>

      {showLabel && (
        <Html position={[0, 1.05, 0]} center portal={htmlPortal}>
          <div className="particle-tree-cluster-label">
            +{cluster.memberCount}
          </div>
        </Html>
      )}

      {hovered && (
        <Html position={[0, 1.45, 0]} center portal={htmlPortal}>
          <div className="particle-tree-hint">
            Cluster · {cluster.memberCount} nodes
          </div>
        </Html>
      )}

      {hovered && onToggleExpanded && (
        <Html position={[0, 0.75, 0]} center portal={htmlPortal}>
          <div
            className="particle-tree-node-controls"
            onClick={(e) => e.stopPropagation()}
            onMouseEnter={() => onControlsHoverChange?.(true)}
            onMouseLeave={() => onControlsHoverChange?.(false)}
          >
            <button
              type="button"
              className="particle-tree-node-control particle-tree-node-control--expand"
              onClick={() => onToggleExpanded(cluster.id)}
              title={cluster.isExpanded ? "Collapse cluster" : "Expand cluster"}
            >
              {cluster.isExpanded ? "−" : "+"}
            </button>
          </div>
        </Html>
      )}
    </group>
  );
}
