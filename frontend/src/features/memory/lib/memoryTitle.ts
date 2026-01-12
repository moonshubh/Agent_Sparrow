export function deriveMemoryTitleFromContent(
  content: string,
  maxLength = 72
): string {
  const normalized = String(content || '')
    .replace(/\s+/g, ' ')
    .trim();

  if (!normalized) return 'Untitled memory';

  const sentenceMatch = normalized.match(/^(.+?)([.!?](?:\s|$)|$)/);
  const candidate = (sentenceMatch?.[1] ?? normalized).trim();

  if (candidate.length <= maxLength) return candidate;

  const slice = candidate.slice(0, maxLength + 1).trimEnd();
  const lastSpace = slice.lastIndexOf(' ');
  const trimmed =
    lastSpace >= Math.max(12, maxLength - 24) ? slice.slice(0, lastSpace) : slice.slice(0, maxLength);

  return `${trimmed.trimEnd()}…`;
}

export function getMemoryTitle(
  memory: { content: string; metadata?: Record<string, unknown> | null },
  maxLength = 72
): string {
  const rawTitle = memory.metadata?.title;
  if (typeof rawTitle === 'string' && rawTitle.trim()) {
    const title = rawTitle.trim();
    return title.length <= maxLength ? title : deriveMemoryTitleFromContent(title, maxLength);
  }

  return deriveMemoryTitleFromContent(memory.content, maxLength);
}

