"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { TreeEdge, TreeViewMode } from "../types";
import type { TreeLink3D } from "../hooks/useTree3DLayout";
import {
  clamp,
  createBranchCurve,
  getBranchColor,
  TREE_COLORS,
} from "../lib/tree3DGeometry";
import { getBarkTextures } from "../lib/textureLoader";

type MeshStandardMaterialRef = THREE.MeshStandardMaterial | null;

function getBranchRadiusForLink(link: TreeLink3D): number {
  const byCount = Math.log2((link.occurrenceCount ?? 1) + 1);
  const byWeight = 0.8 + clamp(link.weight ?? 0.5, 0, 10) * 0.12;
  const base = 0.18 * Math.pow(0.72, link.target.depth);
  return clamp(base * byCount * byWeight, 0.035, 0.36);
}

const BRANCH_EMISSIVE = {
  bark: new THREE.Color(TREE_COLORS.emissiveBark),
  gold: new THREE.Color(TREE_COLORS.emissiveGold),
  blue: new THREE.Color(TREE_COLORS.emissiveBlue),
} as const;

const BIOLUM_VEIN = new THREE.Color("#22d3ee");
const GAP_COLORS = {
  review: new THREE.Color("#f43f5e"),
  confidence: new THREE.Color("#a855f7"),
  weak: BRANCH_EMISSIVE.blue,
} as const;

export function TreeBranch({
  link,
  maxDepth,
  viewMode,
  isDimmed,
  isGhosted,
  onClick,
}: {
  link: TreeLink3D;
  maxDepth: number;
  viewMode: TreeViewMode;
  isDimmed: boolean;
  isGhosted: boolean;
  onClick?: (edge: TreeEdge) => void;
}) {
  const barkTextures = useMemo(() => getBarkTextures(), []);
  const edge = link.edge;
  const seed = useMemo(() => {
    let hash = 2166136261;
    for (let i = 0; i < link.key.length; i += 1) {
      hash ^= link.key.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }, [link.key]);

  const curve = useMemo(
    () =>
      createBranchCurve(link.source.position, link.target.position, 0.22, seed),
    [link.source.position, link.target.position, seed],
  );

  const radius = useMemo(() => getBranchRadiusForLink(link), [link]);
  const geometry = useMemo(
    () => new THREE.TubeGeometry(curve, 18, radius, 8, false),
    [curve, radius],
  );
  const hitGeometry = useMemo(
    () =>
      new THREE.TubeGeometry(
        curve,
        18,
        Math.max(radius + 0.12, 0.18),
        6,
        false,
      ),
    [curve, radius],
  );

  const glowGeometry = useMemo(() => {
    if (link.target.depth > 2) return null;
    return new THREE.TubeGeometry(curve, 12, radius + 0.09, 6, false);
  }, [curve, link.target.depth, radius]);

  const baseColor = useMemo(
    () => getBranchColor(link.target.depth, maxDepth),
    [link.target.depth, maxDepth],
  );

  const material = useMemo(() => {
    const baseOpacity = isGhosted ? 0.12 : isDimmed ? 0.18 : 1;
    const opacity =
      viewMode === "surface_gaps" && !isGhosted && !isDimmed && !link.gapReason
        ? 0.55
        : baseOpacity;

    return new THREE.MeshStandardMaterial({
      color: baseColor,
      map: barkTextures.map ?? undefined,
      normalMap: barkTextures.normalMap ?? undefined,
      normalScale: new THREE.Vector2(0.85, 0.95),
      roughness: 0.9,
      metalness: 0.04,
      emissive: BRANCH_EMISSIVE.bark,
      emissiveIntensity: 0.15,
      transparent: true,
      opacity,
    });
  }, [
    barkTextures.map,
    barkTextures.normalMap,
    baseColor,
    isDimmed,
    isGhosted,
    link.gapReason,
    viewMode,
  ]);

  const glowMaterial = useMemo(() => {
    const opacity = isGhosted ? 0.03 : isDimmed ? 0.05 : 0.12;
    const color =
      viewMode === "celebrate_strengths"
        ? link.strength === "strong"
          ? BRANCH_EMISSIVE.gold
          : link.strength === "medium"
            ? BIOLUM_VEIN
            : BRANCH_EMISSIVE.bark
        : link.gapReason
          ? GAP_COLORS[link.gapReason]
          : BIOLUM_VEIN;

    return new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
    });
  }, [isDimmed, isGhosted, link.gapReason, link.strength, viewMode]);

  const veinGeometry = useMemo(() => {
    const points = curve.getPoints(26);
    return new THREE.BufferGeometry().setFromPoints(points);
  }, [curve]);

  const veinColor = useMemo(() => {
    if (viewMode === "celebrate_strengths") {
      return link.strength === "strong" ? BRANCH_EMISSIVE.gold : BIOLUM_VEIN;
    }

    if (link.gapReason) {
      return GAP_COLORS[link.gapReason];
    }

    return BIOLUM_VEIN;
  }, [link.gapReason, link.strength, viewMode]);

  const veinMaterial = useMemo(() => {
    const baseOpacity = isGhosted ? 0.025 : isDimmed ? 0.06 : 0.18;
    return new THREE.LineDashedMaterial({
      color: veinColor,
      transparent: true,
      opacity: baseOpacity,
      dashSize: 0.48,
      gapSize: 0.82,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
  }, [isDimmed, isGhosted, veinColor]);

  const showVeins =
    !isGhosted &&
    !isDimmed &&
    link.target.depth <= 4 &&
    (viewMode === "celebrate_strengths"
      ? link.strength !== "weak"
      : Boolean(link.gapReason));

  const materialRef = useRef<MeshStandardMaterialRef>(null);
  useEffect(() => {
    materialRef.current = material;
    return () => {
      materialRef.current = null;
    };
  }, [material]);

  const veinRef = useRef<THREE.Line>(null);
  const veinMaterialRef = useRef<THREE.LineDashedMaterial | null>(null);
  useEffect(() => {
    veinMaterialRef.current = veinMaterial;
    return () => {
      veinMaterialRef.current = null;
    };
  }, [veinMaterial]);

  useEffect(() => {
    if (!showVeins) return;
    veinRef.current?.computeLineDistances();
  }, [showVeins, veinGeometry]);

  useFrame((state) => {
    const mat = materialRef.current;
    if (!mat) return;

    const dimFactor = isDimmed ? 0.3 : isGhosted ? 0.22 : 1;

    if (viewMode === "celebrate_strengths") {
      mat.emissive.copy(
        link.strength === "weak" ? BRANCH_EMISSIVE.bark : BRANCH_EMISSIVE.gold,
      );
      const intensity =
        link.strength === "strong"
          ? 0.95
          : link.strength === "medium"
            ? 0.52
            : 0.08;
      mat.emissiveIntensity = intensity * dimFactor;
    }

    if (viewMode === "surface_gaps") {
      const t = state.clock.elapsedTime;

      if (link.gapReason === "review") {
        mat.emissive.copy(GAP_COLORS.review);
        mat.emissiveIntensity =
          (0.3 + (Math.sin(t * 1.6) + 1) * 0.25) * dimFactor;
      } else if (link.gapReason === "confidence") {
        mat.emissive.copy(GAP_COLORS.confidence);
        mat.emissiveIntensity =
          (0.24 + (Math.sin(t * 1.35) + 1) * 0.2) * dimFactor;
      } else if (link.gapReason === "weak") {
        mat.emissive.copy(GAP_COLORS.weak);
        mat.emissiveIntensity =
          (0.22 + (Math.sin(t * 2) + 1) * 0.25) * dimFactor;
      } else {
        mat.emissive.copy(BRANCH_EMISSIVE.bark);
        mat.emissiveIntensity = 0.06 * dimFactor;
      }
    }

    const veinMat = veinMaterialRef.current;
    if (veinMat && showVeins) {
      const t = state.clock.elapsedTime;
      const seedOffset = (seed % 1000) / 140;
      const speed = viewMode === "surface_gaps" ? 1.1 : 0.55;
      veinMat.scale = 1 + Math.sin(t * speed + seedOffset) * 0.15;
      const base = viewMode === "surface_gaps" ? 0.16 : 0.12;
      veinMat.opacity = base + (Math.sin(t * 1.15 + seedOffset) + 1) * 0.06;
    }
  });

  const hitMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0,
        depthWrite: false,
      }),
    [],
  );

  return (
    <group>
      <mesh
        geometry={geometry}
        material={material}
        onClick={(e) => {
          if (!edge) return;
          e.stopPropagation();
          onClick?.(edge);
        }}
      />
      {glowGeometry ? (
        <mesh geometry={glowGeometry} material={glowMaterial} />
      ) : null}
      {showVeins ? (
        <threeLine
          ref={veinRef}
          geometry={veinGeometry}
          material={veinMaterial}
        />
      ) : null}
      {edge && (
        <mesh
          geometry={hitGeometry}
          material={hitMaterial}
          onClick={(e) => {
            e.stopPropagation();
            onClick?.(edge);
          }}
        />
      )}
    </group>
  );
}
