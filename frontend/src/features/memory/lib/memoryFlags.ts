import type { Memory } from '../types';

export function isMemoryEdited(
  memory: Pick<Memory, 'created_at' | 'updated_at'>
): boolean {
  const createdMs = Date.parse(memory.created_at);
  const updatedMs = Date.parse(memory.updated_at);
  if (!Number.isFinite(createdMs) || !Number.isFinite(updatedMs)) return false;
  return updatedMs > createdMs;
}

