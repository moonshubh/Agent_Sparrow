const HEADING_MARKDOWN = /^#{1,6}\s+/m;
const LEGACY_LABEL = /^([A-Za-z][A-Za-z0-9 /&()_-]{2,60}):\s*(.*)$/;
const URL_PREFIX = /^(https?:|ftp:)/i;

const shouldConvertLabel = (label: string): boolean => {
  const words = label.trim().split(/\s+/);
  if (words.length === 0 || words.length > 4) return false;
  return true;
};

export const normalizeLegacyMemoryContent = (content: string): string => {
  if (!content) return content;
  if (HEADING_MARKDOWN.test(content)) {
    return content;
  }

  const lines = content.split(/\r?\n/);
  const normalized: string[] = [];
  let hasLegacy = false;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      normalized.push('');
      continue;
    }

    if (URL_PREFIX.test(trimmed)) {
      normalized.push(trimmed);
      continue;
    }

    const match = trimmed.match(LEGACY_LABEL);
    if (match && shouldConvertLabel(match[1])) {
      const label = match[1].trim();
      const rest = match[2]?.trim();
      if (normalized.length > 0 && normalized[normalized.length - 1].trim() !== '') {
        normalized.push('');
      }
      normalized.push(`### ${label}`);
      if (rest) {
        normalized.push(rest);
      }
      hasLegacy = true;
      continue;
    }

    normalized.push(rawLine);
  }

  if (!hasLegacy) {
    return content;
  }

  return normalized.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};
