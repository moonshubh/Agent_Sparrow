'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { TREE_COLORS } from '../lib/tree3DGeometry';
import { getBarkTextures } from '../lib/textureLoader';

const BIOLUM_COLOR = new THREE.Color('#22d3ee');

type TrunkStrand = {
  geometry: THREE.BufferGeometry;
  dashOffsetSeed: number;
};

function createTrunkStrands(height: number): TrunkStrand[] {
  const strandCount = 5;
  const pointsPerStrand = 90;
  const topRadius = 0.55;
  const bottomRadius = 0.72;
  const rotations = 2.8;

  const strands: TrunkStrand[] = [];

  for (let s = 0; s < strandCount; s += 1) {
    const phase = (s / strandCount) * Math.PI * 2;
    const points: THREE.Vector3[] = [];

    for (let i = 0; i < pointsPerStrand; i += 1) {
      const t = i / (pointsPerStrand - 1);
      const y = (t - 0.5) * height;
      const radius = bottomRadius * (1 - t) + topRadius * t;
      const angle = phase + t * Math.PI * 2 * rotations;
      const r = radius * 1.06;
      points.push(new THREE.Vector3(Math.cos(angle) * r, y, Math.sin(angle) * r));
    }

    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    strands.push({ geometry, dashOffsetSeed: (s / strandCount) * 10 });
  }

  return strands;
}

export function TreeTrunk({ height }: { height: number }) {
  const barkTextures = useMemo(() => getBarkTextures(), []);
  const geometry = useMemo(
    () => new THREE.CylinderGeometry(0.55, 0.72, height, 18),
    [height]
  );
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: new THREE.Color(TREE_COLORS.trunk),
        map: barkTextures.map ?? undefined,
        normalMap: barkTextures.normalMap ?? undefined,
        normalScale: new THREE.Vector2(1.05, 1.05),
        roughness: 0.92,
        metalness: 0.04,
        emissive: BIOLUM_COLOR,
        emissiveIntensity: 0.04,
      }),
    [barkTextures.map, barkTextures.normalMap]
  );

  const glowMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: BIOLUM_COLOR,
        transparent: true,
        opacity: 0.08,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        depthWrite: false,
      }),
    []
  );

  const strands = useMemo(() => createTrunkStrands(height), [height]);
  const strandRefs = useRef<Array<THREE.Line | null>>([]);
  const strandMaterialRefs = useRef<Array<THREE.LineDashedMaterial | null>>([]);

  useEffect(() => {
    strandRefs.current.forEach((line) => line?.computeLineDistances());
  }, [strands]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    for (let i = 0; i < strands.length; i += 1) {
      const mat = strandMaterialRefs.current[i];
      if (!mat) continue;
      mat.scale = 1 + Math.sin(t * 0.7 + (strands[i]?.dashOffsetSeed ?? 0)) * 0.12;
      mat.opacity = 0.16 + (Math.sin(t * 1.1 + i) + 1) * 0.035;
    }
  });

  return (
    <group position={[0, height / 2, 0]}>
      <mesh geometry={geometry} material={material} castShadow />
      <mesh geometry={geometry} material={glowMaterial} scale={1.06} />
      {strands.map((strand, idx) => (
        <line
          key={`trunk-strand-${strand.dashOffsetSeed}`}
          geometry={strand.geometry}
          ref={(line) => {
            strandRefs.current[idx] = line;
          }}
        >
          <lineDashedMaterial
            ref={(mat) => {
              strandMaterialRefs.current[idx] = mat;
            }}
            color={BIOLUM_COLOR}
            transparent
            opacity={0.22}
            dashSize={0.55}
            gapSize={0.85}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </line>
      ))}
    </group>
  );
}
