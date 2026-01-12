'use client';

import { useMemo } from 'react';
import * as THREE from 'three';
import { getGroundTextures } from '../lib/textureLoader';

export function GroundPlane({ size }: { size: number }) {
  const groundTextures = useMemo(() => getGroundTextures(), []);

  const geometry = useMemo(() => new THREE.PlaneGeometry(size, size, 1, 1), [size]);

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: new THREE.Color('#558B2F'),
        map: groundTextures.map ?? undefined,
        normalMap: groundTextures.normalMap ?? undefined,
        emissiveMap: groundTextures.emissiveMap ?? undefined,
        emissive: new THREE.Color('#22d3ee'),
        emissiveIntensity: 0.18,
        normalScale: new THREE.Vector2(0.65, 0.65),
        roughness: 1,
        metalness: 0,
      }),
    [groundTextures.emissiveMap, groundTextures.map, groundTextures.normalMap]
  );

  return (
    <mesh
      geometry={geometry}
      material={material}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, -0.02, 0]}
      receiveShadow
    />
  );
}
