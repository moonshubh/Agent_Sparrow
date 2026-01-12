import * as THREE from 'three';

export const TREE_COLORS = {
  trunk: '#5D4037',
  branchBase: '#795548',
  branchTip: '#A1887F',
  foliageFresh: '#4CAF50',
  foliageStale: '#8D6E63',
  emissiveGold: '#ffcd40',
  emissiveBlue: '#3b82f6',
  emissiveBark: '#a0785a',
} as const;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function hashStringToUint32(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function mulberry32(seed: number): () => number {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function getBranchColor(depth: number, maxDepth = 6): THREE.Color {
  const t = Math.min(depth / Math.max(1, maxDepth), 1);
  return new THREE.Color(TREE_COLORS.branchBase).lerp(
    new THREE.Color(TREE_COLORS.branchTip),
    t
  );
}

export function createBranchCurve(
  start: THREE.Vector3,
  end: THREE.Vector3,
  curvature = 0.22,
  seed?: number
): THREE.CatmullRomCurve3 {
  const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

  const direction = new THREE.Vector3().subVectors(end, start);
  const perpendicular = new THREE.Vector3(
    -direction.z,
    0,
    direction.x
  ).normalize();

  mid.y += curvature * direction.length() * 0.3;

  const rng = seed === undefined ? Math.random : mulberry32(seed);
  const wiggle = (rng() - 0.5) * curvature * direction.length();
  mid.add(perpendicular.multiplyScalar(wiggle));

  return new THREE.CatmullRomCurve3([start, mid, end]);
}

export function getFoliageColor(freshness: 'fresh' | 'stale'): THREE.Color {
  return new THREE.Color(
    freshness === 'fresh' ? TREE_COLORS.foliageFresh : TREE_COLORS.foliageStale
  );
}

export function getParticleCount(
  occurrenceCount: number,
  connectionCount: number
): number {
  const base = 30;
  const fromOccurrences = Math.min(occurrenceCount * 5, 50);
  const fromConnections = Math.min(connectionCount * 8, 40);
  return Math.min(base + fromOccurrences + fromConnections, 150);
}

