'use client';

import { useEffect, useMemo } from 'react';
import { Color, MeshStandardMaterial, PlaneGeometry, Vector2 } from 'three';
import { getGroundTextures } from '../lib/textureLoader';

interface GroundPlaneProps {
  readonly size: number;
}

export function GroundPlane({ size }: GroundPlaneProps) {
  const groundTextures = useMemo(() => getGroundTextures(), []);

  const geometry = useMemo(() => new PlaneGeometry(size, size, 1, 1), [size]);

  const material = useMemo(
    () =>
      new MeshStandardMaterial({
        color: new Color('#558B2F'),
        map: groundTextures.map ?? undefined,
        normalMap: groundTextures.normalMap ?? undefined,
        emissiveMap: groundTextures.emissiveMap ?? undefined,
        emissive: new Color('#22d3ee'),
        emissiveIntensity: 0.18,
        normalScale: new Vector2(0.65, 0.65),
        roughness: 1,
        metalness: 0,
      }),
    [groundTextures.emissiveMap, groundTextures.map, groundTextures.normalMap]
  );

  useEffect(() => {
    return () => {
      geometry.dispose();
    };
  }, [geometry]);

  useEffect(() => {
    return () => {
      material.dispose();
    };
  }, [material]);

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
