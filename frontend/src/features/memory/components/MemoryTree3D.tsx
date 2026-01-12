'use client';

import { useCallback, useEffect, useMemo, useRef, type RefObject } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { EntityType, GraphNode, TreeEdge, TreeTransformResult, TreeViewMode } from '../types';
import { TreeScene } from './TreeScene';
import type { TreeCameraState } from '../hooks/useTreeState';

export type MemoryTree3DControlsApi = {
  zoomIn: () => void;
  zoomOut: () => void;
  reset: () => void;
};

type OrbitControlsHandle = {
  target: THREE.Vector3;
  minDistance?: number;
  maxDistance?: number;
  update: () => void;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export default function MemoryTree3D({
  tree,
  selectedNodeId,
  viewMode,
  showAllLabels,
  expandedNodeIdSet,
  maxChildrenVisible,
  entityTypeFilter,
  searchMatchIds,
  activeSearchMatchId,
  initialCameraState,
  onCameraStateChange,
  onBackgroundClick,
  htmlPortal,
  onNodeClick,
  lastExpansionEvent,
  onToggleExpanded,
  onShowChildren,
  onEdgeClick,
  onControlsReady,
  loading,
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
  initialCameraState?: TreeCameraState | null;
  onCameraStateChange?: (state: TreeCameraState) => void;
  onBackgroundClick?: () => void;
  htmlPortal?: RefObject<HTMLElement>;
  onNodeClick?: (node: GraphNode) => void;
  lastExpansionEvent?: { nodeId: string; action: 'expand' | 'collapse'; at: number } | null;
  onToggleExpanded?: (nodeId: string) => void;
  onShowChildren?: (nodeId: string) => void;
  onEdgeClick?: (edge: TreeEdge) => void;
  onControlsReady?: (api: MemoryTree3DControlsApi | null) => void;
  loading?: boolean;
}) {
  const controlsRef = useRef<OrbitControlsHandle | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const hydratedCameraRef = useRef(false);
  const lastCameraEmitRef = useRef(0);

  const initialCameraPosition = useMemo(() => new THREE.Vector3(0, 12, 22), []);
  const initialTarget = useMemo(() => new THREE.Vector3(0, 6, 0), []);

  const emitCameraState = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    onCameraStateChange?.({
      position: { x: camera.position.x, y: camera.position.y, z: camera.position.z },
      target: { x: controls.target.x, y: controls.target.y, z: controls.target.z },
    });
  }, [onCameraStateChange]);

  useEffect(() => {
    if (hydratedCameraRef.current) return;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    if (!initialCameraState) return;

    controls.target.set(
      initialCameraState.target.x,
      initialCameraState.target.y,
      initialCameraState.target.z
    );
    camera.position.set(
      initialCameraState.position.x,
      initialCameraState.position.y,
      initialCameraState.position.z
    );
    controls.update();
    hydratedCameraRef.current = true;
  }, [initialCameraState]);

  const reset = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;

    controls.target.copy(initialTarget);
    camera.position.copy(initialCameraPosition);
    controls.update();
    emitCameraState();
  }, [emitCameraState, initialCameraPosition, initialTarget]);

  const zoomByFactor = useCallback((factor: number) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;

    const dir = new THREE.Vector3().subVectors(camera.position, controls.target);
    const distance = dir.length();
    const next = clamp(
      distance * factor,
      controls.minDistance ?? 0,
      controls.maxDistance ?? 1e9
    );
    dir.setLength(next);
    camera.position.copy(controls.target).add(dir);
    controls.update();
    emitCameraState();
  }, [emitCameraState]);

  useEffect(() => {
    onControlsReady?.({
      reset,
      zoomIn: () => zoomByFactor(0.85),
      zoomOut: () => zoomByFactor(1.15),
    });

    return () => {
      onControlsReady?.(null);
    };
  }, [onControlsReady, reset, zoomByFactor]);

  const setOrbitControlsRef = useCallback((instance: unknown) => {
    controlsRef.current = instance ? (instance as OrbitControlsHandle) : null;
  }, []);

  const lighting = viewMode === 'celebrate_strengths'
    ? {
        ambient: { intensity: 0.42, color: '#FFF3E0' },
        hemi: { intensity: 0.22, sky: '#ffd3b0', ground: '#0b2216' },
        directional: { intensity: 1.35, color: '#ffcc80', position: [18, 16, -10] as const },
        point: { intensity: 0.8, color: '#ffb38a', position: [-10, 8, -6] as const },
        rim: { intensity: 0.35, color: '#22d3ee', position: [10, 10, 18] as const },
        fog: { color: '#0b0a12', near: 26, far: 88 },
      }
    : {
        ambient: { intensity: 0.22, color: '#dbeafe' },
        hemi: { intensity: 0.2, sky: '#bcdcff', ground: '#070816' },
        directional: { intensity: 1.05, color: '#93c5fd', position: [-14, 22, 12] as const },
        point: { intensity: 0.65, color: '#a855f7', position: [8, 10, -10] as const },
        rim: { intensity: 0.32, color: '#60a5fa', position: [10, 9, 18] as const },
        fog: { color: '#090a16', near: 24, far: 86 },
      };

  return (
    <div className="particle-tree-3d-container" style={{ width: '100%', height: '100%' }}>
      <Canvas
        shadows
        camera={{ position: [0, 12, 22], fov: 48 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
        onPointerMissed={() => {
          onBackgroundClick?.();
        }}
        onCreated={({ camera }) => {
          if (camera instanceof THREE.PerspectiveCamera) {
            cameraRef.current = camera;
          }
        }}
      >
        <fog attach="fog" args={[lighting.fog.color, lighting.fog.near, lighting.fog.far]} />
        <ambientLight intensity={lighting.ambient.intensity} color={lighting.ambient.color} />
        <hemisphereLight
          intensity={lighting.hemi.intensity}
          color={lighting.hemi.sky}
          groundColor={lighting.hemi.ground}
        />
        <directionalLight
          position={lighting.directional.position}
          intensity={lighting.directional.intensity}
          color={lighting.directional.color}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
          shadow-camera-near={1}
          shadow-camera-far={120}
          shadow-camera-left={-40}
          shadow-camera-right={40}
          shadow-camera-top={40}
          shadow-camera-bottom={-40}
        />
        <pointLight
          position={lighting.point.position}
          intensity={lighting.point.intensity}
          color={lighting.point.color}
        />
        <pointLight
          position={lighting.rim.position}
          intensity={lighting.rim.intensity}
          color={lighting.rim.color}
        />

        <OrbitControls
          ref={setOrbitControlsRef}
          enablePan
          enableZoom
          enableRotate
          minDistance={6}
          maxDistance={70}
          target={[initialTarget.x, initialTarget.y, initialTarget.z]}
          onChange={() => {
            const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
            if (now - lastCameraEmitRef.current < 120) return;
            lastCameraEmitRef.current = now;
            emitCameraState();
          }}
          onEnd={() => {
            emitCameraState();
          }}
        />

        <TreeScene
          tree={tree}
          selectedNodeId={selectedNodeId}
          viewMode={viewMode}
          showAllLabels={showAllLabels}
          expandedNodeIdSet={expandedNodeIdSet}
          maxChildrenVisible={maxChildrenVisible}
          entityTypeFilter={entityTypeFilter}
          searchMatchIds={searchMatchIds}
          activeSearchMatchId={activeSearchMatchId}
          onNodeClick={onNodeClick}
          onToggleExpanded={onToggleExpanded}
          onShowChildren={onShowChildren}
          onEdgeClick={onEdgeClick}
          orbitControlsRef={controlsRef}
          htmlPortal={htmlPortal}
          loading={loading}
          lastExpansionEvent={lastExpansionEvent}
        />
      </Canvas>
    </div>
  );
}
