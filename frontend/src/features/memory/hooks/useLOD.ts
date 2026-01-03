import { useFrame, useThree } from '@react-three/fiber';
import { useMemo, useRef, useState } from 'react';
import { Camera } from 'three';
import type { Vector3 } from 'three';

export type LODLevel = 'high' | 'medium' | 'low';

export function useLOD(
  nodes: readonly { id: string; position: Vector3 }[],
  options?: {
    readonly highDistance?: number;
    readonly mediumDistance?: number;
    readonly updateIntervalSeconds?: number;
  }
): ReadonlyMap<string, LODLevel> {
  const camera = useThree((state) => state.camera);

  const highDistance = options?.highDistance ?? 12;
  const mediumDistance = options?.mediumDistance ?? 30;
  const updateIntervalSeconds = options?.updateIntervalSeconds ?? 0.18;

  const [cameraPos, setCameraPos] = useState<readonly [number, number, number]>(() => [
    camera.position.x,
    camera.position.y,
    camera.position.z,
  ]);

  const lastUpdateRef = useRef<number>(-1);

  useFrame((state) => {
    if (!(camera instanceof Camera)) return;
    const now = state.clock.elapsedTime;
    if (lastUpdateRef.current >= 0 && now - lastUpdateRef.current < updateIntervalSeconds) {
      return;
    }
    lastUpdateRef.current = now;
    setCameraPos([camera.position.x, camera.position.y, camera.position.z]);
  });

  return useMemo(() => {
    const out = new Map<string, LODLevel>();
    const highSq = highDistance * highDistance;
    const mediumSq = mediumDistance * mediumDistance;

    const cx = cameraPos[0];
    const cy = cameraPos[1];
    const cz = cameraPos[2];

    for (const node of nodes) {
      const dx = node.position.x - cx;
      const dy = node.position.y - cy;
      const dz = node.position.z - cz;
      const distSq = dx * dx + dy * dy + dz * dz;
      const lod: LODLevel = distSq < highSq ? 'high' : distSq < mediumSq ? 'medium' : 'low';
      out.set(node.id, lod);
    }

    return out;
  }, [cameraPos, highDistance, mediumDistance, nodes]);
}
