import { mulberry32 } from './tree3DGeometry';

export type Vec3 = readonly [number, number, number];

export interface SpatialCluster<T> {
  readonly centroid: Vec3;
  readonly items: readonly T[];
}

function distanceSq(a: Vec3, b: Vec3): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  const dz = a[2] - b[2];
  return dx * dx + dy * dy + dz * dz;
}

function mean(points: readonly Vec3[]): Vec3 {
  if (points.length === 0) return [0, 0, 0];
  let x = 0;
  let y = 0;
  let z = 0;
  for (const p of points) {
    x += p[0];
    y += p[1];
    z += p[2];
  }
  const inv = 1 / points.length;
  return [x * inv, y * inv, z * inv];
}

function pickKMeansPlusPlusCentroids(
  points: readonly Vec3[],
  k: number,
  seed: number
): Vec3[] {
  const rng = mulberry32(seed);
  const centroids: Vec3[] = [];
  if (points.length === 0 || k <= 0) return centroids;

  const firstIndex = Math.min(points.length - 1, Math.floor(rng() * points.length));
  centroids.push(points[firstIndex] ?? [0, 0, 0]);

  while (centroids.length < k) {
    const distances = points.map((p) => {
      let best = Number.POSITIVE_INFINITY;
      for (const c of centroids) {
        best = Math.min(best, distanceSq(p, c));
      }
      return best === Number.POSITIVE_INFINITY ? 0 : best;
    });

    const total = distances.reduce((acc, v) => acc + v, 0);
    if (total <= 0) {
      const idx = Math.min(points.length - 1, Math.floor(rng() * points.length));
      centroids.push(points[idx] ?? [0, 0, 0]);
      continue;
    }

    let roll = rng() * total;
    let selectedIdx = 0;
    for (let i = 0; i < distances.length; i += 1) {
      roll -= distances[i] ?? 0;
      if (roll <= 0) {
        selectedIdx = i;
        break;
      }
    }
    centroids.push(points[selectedIdx] ?? [0, 0, 0]);
  }

  return centroids;
}

export function spatialKMeans<T>(
  items: readonly T[],
  options: {
    readonly k: number;
    readonly getPoint: (item: T) => Vec3;
    readonly seed?: number;
    readonly maxIterations?: number;
  }
): SpatialCluster<T>[] {
  if (items.length === 0) return [];

  const k = Math.max(1, Math.min(options.k, items.length));
  const seed = options.seed ?? 1337;
  const maxIterations = options.maxIterations ?? 12;

  const points = items.map(options.getPoint);
  let centroids = pickKMeansPlusPlusCentroids(points, k, seed);

  const assignments = new Array<number>(items.length).fill(-1);

  for (let iter = 0; iter < maxIterations; iter += 1) {
    let changed = false;

    for (let i = 0; i < points.length; i += 1) {
      const p = points[i];
      if (!p) continue;

      let bestIdx = 0;
      let bestDist = Number.POSITIVE_INFINITY;
      for (let c = 0; c < centroids.length; c += 1) {
        const d = distanceSq(p, centroids[c] ?? [0, 0, 0]);
        if (d < bestDist) {
          bestDist = d;
          bestIdx = c;
        }
      }

      if (assignments[i] !== bestIdx) {
        assignments[i] = bestIdx;
        changed = true;
      }
    }

    if (!changed && iter > 0) break;

    const buckets: Vec3[][] = Array.from({ length: k }, () => []);
    for (let i = 0; i < points.length; i += 1) {
      const cluster = assignments[i] ?? 0;
      const p = points[i];
      if (!p) continue;
      buckets[cluster]?.push(p);
    }

    const rng = mulberry32(seed + iter + 1);
    centroids = buckets.map((bucket) => {
      if (bucket.length > 0) return mean(bucket);
      const idx = Math.min(points.length - 1, Math.floor(rng() * points.length));
      return points[idx] ?? [0, 0, 0];
    });
  }

  const grouped: T[][] = Array.from({ length: k }, () => []);
  for (let i = 0; i < items.length; i += 1) {
    const cluster = assignments[i] ?? 0;
    grouped[cluster]?.push(items[i] as T);
  }

  return grouped
    .map((clusterItems, idx) => ({
      centroid: centroids[idx] ?? [0, 0, 0],
      items: clusterItems,
    }))
    .filter((cluster) => cluster.items.length > 0);
}

