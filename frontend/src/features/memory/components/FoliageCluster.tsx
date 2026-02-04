"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import {
  clamp,
  getFoliageColor,
  hashStringToUint32,
  mulberry32,
} from "../lib/tree3DGeometry";
import type { TreeViewMode } from "../types";

export interface FoliageClusterProps {
  id: string;
  center: THREE.Vector3;
  count: number;
  freshness: "fresh" | "stale";
  isDimmed: boolean;
  isSelected: boolean;
  viewMode: TreeViewMode;
  leafTexture: THREE.Texture | null;
}

export function FoliageCluster({
  id,
  center,
  count,
  freshness,
  isDimmed,
  isSelected,
  viewMode,
  leafTexture,
}: FoliageClusterProps) {
  const pointsRef = useRef<THREE.Points>(null);
  const canopyRef = useRef<THREE.Mesh>(null);
  const seedOffset = useMemo(() => (hashStringToUint32(id) % 1000) / 140, [id]);

  const geometry = useMemo(() => {
    const seed = hashStringToUint32(`foliage:${id}`);
    const rng = mulberry32(seed);

    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const radius = 0.52 + Math.min(1.1, count / 150) * 0.78;

    const base = getFoliageColor(freshness);
    const baseHsl = { h: 0, s: 0, l: 0 };
    base.getHSL(baseHsl);
    const tmp = new THREE.Color();

    for (let i = 0; i < count; i += 1) {
      const phi = rng() * Math.PI * 2;
      const cosTheta = rng() * 1.6 - 0.6;
      const theta = Math.acos(Math.max(-1, Math.min(1, cosTheta)));
      const r = radius * Math.cbrt(rng());

      positions[i * 3] = r * Math.sin(theta) * Math.cos(phi);
      positions[i * 3 + 1] = r * Math.sin(theta) * Math.sin(phi);
      positions[i * 3 + 2] = r * Math.cos(theta);

      const hue =
        baseHsl.h + (rng() - 0.5) * (freshness === "fresh" ? 0.04 : 0.02);
      const sat = clamp(baseHsl.s * (0.82 + rng() * 0.28), 0, 1);
      const light = clamp(baseHsl.l * (0.72 + rng() * 0.38), 0, 1);
      tmp.setHSL((hue + 1) % 1, sat, light);
      colors[i * 3] = tmp.r;
      colors[i * 3 + 1] = tmp.g;
      colors[i * 3 + 2] = tmp.b;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return geo;
  }, [count, freshness, id]);

  const canopyRadius = useMemo(
    () => 0.78 + Math.min(1.25, count / 140) * 0.86,
    [count],
  );
  const canopyGeometry = useMemo(
    () => new THREE.IcosahedronGeometry(canopyRadius, 1),
    [canopyRadius],
  );

  useFrame((state) => {
    if (!pointsRef.current) return;
    const t = state.clock.elapsedTime;
    const sway = Math.sin(t * 0.6 + seedOffset) * 0.035;
    pointsRef.current.rotation.y = Math.sin(t * 0.32 + seedOffset) * 0.08;
    pointsRef.current.rotation.x = Math.cos(t * 0.25 + seedOffset) * 0.06;
    pointsRef.current.position.set(center.x, center.y + sway, center.z);

    const mat = pointsRef.current.material;
    if (!(mat instanceof THREE.PointsMaterial)) return;

    const baseOpacity = isDimmed
      ? 0.16
      : isSelected
        ? 1
        : viewMode === "celebrate_strengths"
          ? 0.82
          : 0.62;

    if (viewMode === "surface_gaps" && !isDimmed && !isSelected) {
      const pulse = 0.06 + (Math.sin(t * 1.45) + 1) * 0.03;
      mat.opacity = Math.min(1, baseOpacity + pulse);
    } else {
      mat.opacity = baseOpacity;
    }

    if (canopyRef.current) {
      canopyRef.current.rotation.y = Math.sin(t * 0.18 + seedOffset) * 0.08;
      canopyRef.current.rotation.x = Math.cos(t * 0.16 + seedOffset) * 0.06;
      canopyRef.current.position.set(center.x, center.y + sway * 0.6, center.z);
    }
  });

  const material = useMemo(() => {
    const baseOpacity = isDimmed
      ? 0.16
      : isSelected
        ? 1
        : viewMode === "celebrate_strengths"
          ? 0.82
          : 0.62;

    return new THREE.PointsMaterial({
      color: new THREE.Color("#ffffff"),
      map: leafTexture ?? undefined,
      transparent: true,
      alphaTest: 0.2,
      size: isSelected ? 0.34 : viewMode === "surface_gaps" ? 0.22 : 0.28,
      sizeAttenuation: true,
      opacity: baseOpacity,
      depthWrite: false,
      vertexColors: true,
    });
  }, [isDimmed, isSelected, leafTexture, viewMode]);

  const canopyMaterial = useMemo(() => {
    const baseColor = getFoliageColor(freshness).multiplyScalar(0.55);
    const glow = viewMode === "surface_gaps" ? "#22d3ee" : "#ffcd40";
    const opacity = isDimmed
      ? 0.03
      : isSelected
        ? 0.095
        : viewMode === "celebrate_strengths"
          ? 0.075
          : 0.06;
    return new THREE.MeshStandardMaterial({
      color: baseColor,
      transparent: true,
      opacity,
      depthWrite: false,
      emissive: new THREE.Color(glow),
      emissiveIntensity: viewMode === "surface_gaps" ? 0.12 : 0.08,
      roughness: 0.95,
      metalness: 0,
    });
  }, [freshness, isDimmed, isSelected, viewMode]);

  return (
    <>
      <mesh
        ref={canopyRef}
        geometry={canopyGeometry}
        material={canopyMaterial}
        position={[center.x, center.y, center.z]}
        castShadow={false}
        receiveShadow={false}
      />
      <points
        ref={pointsRef}
        position={[center.x, center.y, center.z]}
        geometry={geometry}
        material={material}
      />
    </>
  );
}
