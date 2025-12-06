/**
 * Shared log formatting utilities for AG-UI feature
 * 
 * Provides functions for parsing and formatting structured log data
 * from log analysis tool outputs.
 */

import { stripCodeFence } from './parsing';

/**
 * Parse structured log segments from content string
 */
export function parseStructuredLogSegments(content: string): any[] | null {
  const trimmed = stripCodeFence(content);
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed);
    let segments: any[] | null = null;
    if (Array.isArray(parsed)) {
      segments = parsed;
    } else {
      const candidates = ['sections', 'items', 'segments'] as const;
      const foundKey = candidates.find((key) => Array.isArray((parsed as any)?.[key]));
      segments = foundKey ? (parsed as any)[foundKey] : null;
    }
    if (!segments || !Array.isArray(segments)) return null;
    const normalized = segments.filter((seg) => typeof seg === 'object');
    return normalized.length ? normalized : null;
  } catch {
    return null;
  }
}

/**
 * Format structured log segments into readable text
 */
export function formatStructuredLogSegments(segments: any[]): string {
  return segments.map((seg, idx) => {
    const lineRange = seg.line_range || seg.lines || seg.range || seg.lineRange;
    const relevance = seg.relevance || seg.summary || seg.description;
    const keyInfo = seg.key_info || seg.key || seg.detail || seg.info;
    const parts = [];
    if (lineRange) parts.push(`Lines ${lineRange}`);
    if (relevance) parts.push(String(relevance));
    if (keyInfo) parts.push(`Key: ${keyInfo}`);
    return `${idx + 1}. ${parts.filter(Boolean).join(' — ')}`;
  }).join('\n');
}

const normalizeLogContent = (content: any): string => {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((part) =>
        typeof part === 'string'
          ? part
          : part && typeof part === 'object' && typeof (part as any).text === 'string'
            ? (part as any).text
            : ''
      )
      .join('');
  }
  return '';
};

/**
 * Format content if it contains structured log data
 * Returns formatted string or null if not structured log format
 */
export function formatIfStructuredLog(content: any): string | null {
  const normalized = normalizeLogContent(content);
  if (!normalized) return null;
  const segments = parseStructuredLogSegments(normalized);
  if (!segments) return null;
  return formatStructuredLogSegments(segments);
}
