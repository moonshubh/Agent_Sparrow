/**
 * Helpers for MemoryDashboard layout and coloring.
 */

export const DEFAULT_RADIUS = 120;

export function getHoursSinceCreation(createdAt: string): number {
  const timestamp = Date.parse(createdAt);
  if (Number.isNaN(timestamp)) return 0;
  const diff = Date.now() - timestamp;
  if (diff <= 0) return 0;
  return Math.round(diff / (1000 * 60 * 60));
}

export function getNodePosition(index: number, total: number, radius = DEFAULT_RADIUS) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  const spiralFactor = 1 + (index / Math.max(total, 1)) * 0.5;
  return {
    x: Math.cos(angle) * radius * spiralFactor + 200,
    y: Math.sin(angle) * radius * spiralFactor + 200,
  };
}

export function getNodeState(
  factId: string,
  recentlyRetrieved: string[],
  recentlyWritten: string[]
): 'dormant' | 'retrieved' | 'writing' {
  if (recentlyWritten.includes(factId)) return 'writing';
  if (recentlyRetrieved.includes(factId)) return 'retrieved';
  return 'dormant';
}

export function getNodeColor(createdAt: string): string {
  const hours = getHoursSinceCreation(createdAt);
  if (hours < 1) return 'var(--accent-gold-400)';
  if (hours < 24) return 'var(--accent-amber-400)';
  return 'var(--crystal-cyan-400)';
}

