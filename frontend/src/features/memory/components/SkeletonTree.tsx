'use client';

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

export function SkeletonTree() {
  const trunkHeight = 3.2;
  const groupRef = useRef<THREE.Group>(null);

  const trunkGeometry = useMemo(
    () => new THREE.CylinderGeometry(0.5, 0.68, trunkHeight, 16),
    [trunkHeight]
  );

  const branches = useMemo(() => {
    const start = new THREE.Vector3(0, trunkHeight * 0.9, 0);
    const endpoints = [
      new THREE.Vector3(3.2, trunkHeight + 2.4, 0.6),
      new THREE.Vector3(-2.8, trunkHeight + 2.1, 1.8),
      new THREE.Vector3(-1.4, trunkHeight + 1.9, -2.6),
      new THREE.Vector3(2.4, trunkHeight + 1.7, -2.2),
    ];

    return endpoints.map((end, idx) => {
      const mid = new THREE.Vector3()
        .addVectors(start, end)
        .multiplyScalar(0.5);
      mid.y += 0.8 + idx * 0.15;
      const curve = new THREE.CatmullRomCurve3([start, mid, end]);
      const geometry = new THREE.TubeGeometry(curve, 18, 0.09, 8, false);
      return { end, geometry };
    });
  }, [trunkHeight]);

  const nodeGeometry = useMemo(() => new THREE.SphereGeometry(0.18, 12, 12), []);

  useFrame((state) => {
    const group = groupRef.current;
    if (!group) return;

    const t = (Math.sin(state.clock.elapsedTime * 1.1) + 1) / 2;
    const scale = 0.98 + t * 0.03;
    group.scale.setScalar(scale);
    group.rotation.y = Math.sin(state.clock.elapsedTime * 0.12) * 0.08;
  });

  return (
    <group ref={groupRef}>
      <mesh geometry={trunkGeometry} position={[0, trunkHeight / 2, 0]}>
        <meshStandardMaterial
          color="#6B7280"
          roughness={0.95}
          metalness={0.05}
          transparent
          opacity={0.55}
          emissive="#9CA3AF"
          emissiveIntensity={0.12}
        />
      </mesh>
      {branches.map((b, idx) => (
        <group key={`skeleton-branch-${idx}`}>
          <mesh geometry={b.geometry}>
            <meshStandardMaterial
              color="#9CA3AF"
              roughness={0.9}
              metalness={0.02}
              transparent
              opacity={0.45}
              emissive="#9CA3AF"
              emissiveIntensity={0.08}
            />
          </mesh>
          <mesh geometry={nodeGeometry} position={[b.end.x, b.end.y, b.end.z]}>
            <meshStandardMaterial
              color="#D1D5DB"
              roughness={0.6}
              metalness={0.1}
              transparent
              opacity={0.6}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}
