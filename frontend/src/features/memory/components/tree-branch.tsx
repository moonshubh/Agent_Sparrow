'use client';

import { useEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import {
  AdditiveBlending,
  BackSide,
  BufferGeometry,
  Color,
  Line,
  LineBasicMaterial,
  LineDashedMaterial,
  MeshBasicMaterial,
  MeshStandardMaterial,
  TubeGeometry,
  Vector2,
} from 'three';
import type { TreeEdge, TreeViewMode } from '../types';
import type { TreeLink3D } from '../hooks/useTree3DLayout';
import type { LODLevel } from '../hooks/useLOD';
import { clamp, createBranchCurve, getBranchColor, TREE_COLORS } from '../lib/tree3DGeometry';
import { getBarkTextures } from '../lib/textureLoader';

type MeshStandardMaterialRef = MeshStandardMaterial | null;

function getBranchRadiusForLink(link: TreeLink3D): number {
  const byCount = Math.log2((link.occurrenceCount ?? 1) + 1);
  const byWeight = 0.8 + clamp(link.weight ?? 0.5, 0, 10) * 0.12;
  const base = 0.18 * Math.pow(0.72, link.target.depth);
  return clamp(base * byCount * byWeight, 0.035, 0.36);
}

const BRANCH_EMISSIVE = {
  bark: new Color(TREE_COLORS.emissiveBark),
  gold: new Color(TREE_COLORS.emissiveGold),
  blue: new Color(TREE_COLORS.emissiveBlue),
} as const;

const BIOLUM_VEIN = new Color('#22d3ee');
const GAP_COLORS = {
  review: new Color('#f43f5e'),
  confidence: new Color('#a855f7'),
  weak: BRANCH_EMISSIVE.blue,
} as const;

interface BranchAnimatorProps {
  materialRef: MutableRefObject<MeshStandardMaterialRef>;
  veinMaterialRef: MutableRefObject<LineDashedMaterial | null>;
  showVeins: boolean;
  viewMode: TreeViewMode;
  link: TreeLink3D;
  seed: number;
  isDimmed: boolean;
  isGhosted: boolean;
}

function BranchAnimator({
  materialRef,
  veinMaterialRef,
  showVeins,
  viewMode,
  link,
  seed,
  isDimmed,
  isGhosted,
}: BranchAnimatorProps) {
  useFrame((state) => {
    const mat = materialRef.current;
    if (!mat) return;

    const dimFactor = isDimmed ? 0.3 : isGhosted ? 0.22 : 1;

    if (viewMode === 'celebrate_strengths') {
      mat.emissive.copy(link.strength === 'weak' ? BRANCH_EMISSIVE.bark : BRANCH_EMISSIVE.gold);
      const intensity =
        link.strength === 'strong' ? 0.95 : link.strength === 'medium' ? 0.52 : 0.08;
      mat.emissiveIntensity = intensity * dimFactor;
    }

    if (viewMode === 'surface_gaps') {
      const t = state.clock.elapsedTime;

      if (link.gapReason === 'review') {
        mat.emissive.copy(GAP_COLORS.review);
        mat.emissiveIntensity = (0.3 + (Math.sin(t * 1.6) + 1) * 0.25) * dimFactor;
      } else if (link.gapReason === 'confidence') {
        mat.emissive.copy(GAP_COLORS.confidence);
        mat.emissiveIntensity = (0.24 + (Math.sin(t * 1.35) + 1) * 0.2) * dimFactor;
      } else if (link.gapReason === 'weak') {
        mat.emissive.copy(GAP_COLORS.weak);
        mat.emissiveIntensity = (0.22 + (Math.sin(t * 2) + 1) * 0.25) * dimFactor;
      } else {
        mat.emissive.copy(BRANCH_EMISSIVE.bark);
        mat.emissiveIntensity = 0.06 * dimFactor;
      }
    }

    const veinMat = veinMaterialRef.current;
    if (veinMat && showVeins) {
      const t = state.clock.elapsedTime;
      const seedOffset = (seed % 1000) / 140;
      const speed = viewMode === 'surface_gaps' ? 1.1 : 0.55;
      veinMat.scale = 1 + Math.sin(t * speed + seedOffset) * 0.15;
      const base = viewMode === 'surface_gaps' ? 0.16 : 0.12;
      veinMat.opacity = base + (Math.sin(t * 1.15 + seedOffset) + 1) * 0.06;
    }
  });

  return null;
}

interface TreeBranchProps {
  link: TreeLink3D;
  maxDepth: number;
  viewMode: TreeViewMode;
  isDimmed: boolean;
  isGhosted: boolean;
  lod: LODLevel;
  onClick?: (edge: TreeEdge) => void;
}

export function TreeBranch({
  link,
  maxDepth,
  viewMode,
  isDimmed,
  isGhosted,
  lod,
  onClick,
}: TreeBranchProps) {
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
    () => createBranchCurve(link.source.position, link.target.position, 0.22, seed),
    [link.source.position, link.target.position, seed]
  );

  const isHigh = lod === 'high';
  const isLow = lod === 'low';
  const showTube = !isLow;
  const useTextures = isHigh;

  const radius = useMemo(() => getBranchRadiusForLink(link), [link]);
  const tubeSegments = isHigh ? 18 : 10;
  const radialSegments = isHigh ? 8 : 6;
  const geometry = useMemo(
    () =>
      showTube ? new TubeGeometry(curve, tubeSegments, radius, radialSegments, false) : null,
    [curve, radialSegments, radius, showTube, tubeSegments]
  );
  const hitGeometry = useMemo(
    () =>
      edge && !isLow
        ? new TubeGeometry(
            curve,
            isHigh ? 18 : 10,
            Math.max(radius + 0.12, 0.18),
            isHigh ? 6 : 5,
            false
          )
        : null,
    [curve, edge, isHigh, isLow, radius]
  );

  const glowGeometry = useMemo(() => {
    if (!isHigh || link.target.depth > 2) return null;
    return new TubeGeometry(curve, 12, radius + 0.09, 6, false);
  }, [curve, isHigh, link.target.depth, radius]);

  const lineGeometry = useMemo(() => {
    if (!isLow) return null;
    const points = curve.getPoints(6);
    return new BufferGeometry().setFromPoints(points);
  }, [curve, isLow]);

  const baseColor = useMemo(
    () => getBranchColor(link.target.depth, maxDepth),
    [link.target.depth, maxDepth]
  );

  const dimFactor = isDimmed ? 0.3 : isGhosted ? 0.22 : 1;

  const baseEmissive = useMemo(() => {
    if (viewMode === 'celebrate_strengths') {
      return link.strength === 'weak' ? BRANCH_EMISSIVE.bark : BRANCH_EMISSIVE.gold;
    }

    if (link.gapReason) {
      return GAP_COLORS[link.gapReason];
    }

    return BRANCH_EMISSIVE.bark;
  }, [link.gapReason, link.strength, viewMode]);

  const baseEmissiveIntensity = useMemo(() => {
    if (viewMode === 'celebrate_strengths') {
      return link.strength === 'strong' ? 0.95 : link.strength === 'medium' ? 0.52 : 0.08;
    }

    if (link.gapReason === 'review') return 0.3;
    if (link.gapReason === 'confidence') return 0.24;
    if (link.gapReason === 'weak') return 0.22;
    return 0.06;
  }, [link.gapReason, link.strength, viewMode]);

  const material = useMemo(() => {
    if (!showTube) return null;

    const baseOpacity = isGhosted ? 0.12 : isDimmed ? 0.18 : 1;
    const opacity =
      viewMode === 'surface_gaps' && !isGhosted && !isDimmed && !link.gapReason
        ? 0.55
        : baseOpacity;

    return new MeshStandardMaterial({
      color: baseColor,
      map: useTextures ? barkTextures.map ?? undefined : undefined,
      normalMap: useTextures ? barkTextures.normalMap ?? undefined : undefined,
      normalScale: useTextures ? new Vector2(0.85, 0.95) : undefined,
      roughness: 0.9,
      metalness: 0.04,
      emissive: baseEmissive,
      emissiveIntensity: baseEmissiveIntensity * dimFactor,
      transparent: true,
      opacity,
    });
  }, [
    barkTextures.map,
    barkTextures.normalMap,
    baseColor,
    baseEmissive,
    baseEmissiveIntensity,
    dimFactor,
    isDimmed,
    isGhosted,
    link.gapReason,
    showTube,
    useTextures,
    viewMode,
  ]);

  const lineMaterial = useMemo(() => {
    if (!isLow) return null;
    const opacity = isGhosted ? 0.08 : isDimmed ? 0.16 : 0.45;
    return new LineBasicMaterial({
      color: baseColor,
      transparent: true,
      opacity,
    });
  }, [baseColor, isDimmed, isGhosted, isLow]);

  const glowMaterial = useMemo(() => {
    if (!glowGeometry) return null;
    const opacity = isGhosted ? 0.03 : isDimmed ? 0.05 : 0.12;
    const color = viewMode === 'celebrate_strengths'
      ? link.strength === 'strong'
        ? BRANCH_EMISSIVE.gold
        : link.strength === 'medium'
          ? BIOLUM_VEIN
          : BRANCH_EMISSIVE.bark
      : link.gapReason
        ? GAP_COLORS[link.gapReason]
        : BIOLUM_VEIN;

    return new MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      blending: AdditiveBlending,
      side: BackSide,
      depthWrite: false,
    });
  }, [glowGeometry, isDimmed, isGhosted, link.gapReason, link.strength, viewMode]);

  const showVeins =
    isHigh &&
    !isGhosted &&
    !isDimmed &&
    link.target.depth <= 4 &&
    (viewMode === 'celebrate_strengths'
      ? link.strength !== 'weak'
      : Boolean(link.gapReason));

  const veinGeometry = useMemo(() => {
    if (!showVeins) return null;
    const points = curve.getPoints(26);
    return new BufferGeometry().setFromPoints(points);
  }, [curve, showVeins]);

  const veinColor = useMemo(() => {
    if (!showVeins) return null;
    if (viewMode === 'celebrate_strengths') {
      return link.strength === 'strong' ? BRANCH_EMISSIVE.gold : BIOLUM_VEIN;
    }

    if (link.gapReason) {
      return GAP_COLORS[link.gapReason];
    }

    return BIOLUM_VEIN;
  }, [link.gapReason, link.strength, showVeins, viewMode]);

  const veinMaterial = useMemo(() => {
    if (!showVeins || !veinColor) return null;
    const baseOpacity = isGhosted ? 0.025 : isDimmed ? 0.06 : 0.18;
    return new LineDashedMaterial({
      color: veinColor,
      transparent: true,
      opacity: baseOpacity,
      dashSize: 0.48,
      gapSize: 0.82,
      blending: AdditiveBlending,
      depthWrite: false,
    });
  }, [isDimmed, isGhosted, showVeins, veinColor]);

  const materialRef = useRef<MeshStandardMaterialRef>(null);
  useEffect(() => {
    materialRef.current = material;
    return () => {
      materialRef.current = null;
    };
  }, [material]);

  const veinMaterialRef = useRef<LineDashedMaterial | null>(null);
  useEffect(() => {
    veinMaterialRef.current = veinMaterial;
    return () => {
      veinMaterialRef.current = null;
    };
  }, [veinMaterial]);

  const veinLine = useMemo(
    () => (veinGeometry && veinMaterial ? new Line(veinGeometry, veinMaterial) : null),
    [veinGeometry, veinMaterial]
  );

  useEffect(() => {
    if (!showVeins || !veinLine) return;
    veinLine.computeLineDistances();
  }, [showVeins, veinLine]);

  const hitMaterial = useMemo(
    () =>
      new MeshBasicMaterial({
        transparent: true,
        opacity: 0,
        depthWrite: false,
      }),
    []
  );

  useEffect(() => {
    return () => {
      geometry?.dispose();
      hitGeometry?.dispose();
      glowGeometry?.dispose();
      lineGeometry?.dispose();
      veinGeometry?.dispose();
    };
  }, [geometry, glowGeometry, hitGeometry, lineGeometry, veinGeometry]);

  useEffect(() => {
    return () => {
      material?.dispose();
      glowMaterial?.dispose();
      lineMaterial?.dispose();
      veinMaterial?.dispose();
    };
  }, [glowMaterial, lineMaterial, material, veinMaterial]);

  useEffect(() => {
    return () => {
      hitMaterial.dispose();
    };
  }, [hitMaterial]);

  if (isLow && lineGeometry && lineMaterial) {
    return (
      <line
        geometry={lineGeometry}
        material={lineMaterial}
        onClick={(e) => {
          if (!edge) return;
          e.stopPropagation();
          onClick?.(edge);
        }}
      />
    );
  }

  const shouldAnimate =
    isHigh &&
    (showVeins ||
      (viewMode === 'surface_gaps' && Boolean(link.gapReason)) ||
      (viewMode === 'celebrate_strengths' && link.strength === 'strong'));

  return (
    <group>
      {geometry && material ? (
        <mesh
          geometry={geometry}
          material={material}
          onClick={(e) => {
            if (!edge) return;
            e.stopPropagation();
            onClick?.(edge);
          }}
        />
      ) : null}
      {glowGeometry && glowMaterial ? (
        <mesh geometry={glowGeometry} material={glowMaterial} />
      ) : null}
      {veinLine ? <primitive object={veinLine} /> : null}
      {edge && hitGeometry ? (
        <mesh
          geometry={hitGeometry}
          material={hitMaterial}
          onClick={(e) => {
            e.stopPropagation();
            onClick?.(edge);
          }}
        />
      ) : null}
      {shouldAnimate && material ? (
        <BranchAnimator
          materialRef={materialRef}
          veinMaterialRef={veinMaterialRef}
          showVeins={showVeins}
          viewMode={viewMode}
          link={link}
          seed={seed}
          isDimmed={isDimmed}
          isGhosted={isGhosted}
        />
      ) : null}
    </group>
  );
}
