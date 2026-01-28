/**
 * Shared parsing utilities for LibreChat feature
 * 
 * Provides common functions for parsing tool outputs, extracting data,
 * and handling various data formats from the backend.
 */

/**
 * Strip code fence markers from text (```language ... ```)
 */
export function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const fenceMatch = trimmed.match(/^```[a-zA-Z0-9]*\s*([\s\S]*?)```$/);
  return fenceMatch ? fenceMatch[1].trim() : trimmed;
}

const isInternalRetrievalPayload = (value: unknown): boolean => {
  if (!value) return false;
  if (Array.isArray(value)) {
    return value.some((item) => isInternalRetrievalPayload(item));
  }
  if (typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.retrieval_id === 'string' &&
    Array.isArray(record.sources_searched) &&
    Array.isArray(record.results)
  );
};

const isStructuredLogPayload = (value: unknown): boolean => {
  const isSegment = (item: Record<string, unknown>): boolean =>
    'line_range' in item || 'lineRange' in item || 'key_info' in item || 'keyInfo' in item || 'relevance' in item;

  if (Array.isArray(value)) {
    return value.some((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return false;
      return isSegment(item as Record<string, unknown>);
    });
  }
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  const containers = ['segments', 'items', 'sections'] as const;
  for (const key of containers) {
    const list = record[key];
    if (Array.isArray(list) && list.some((item) => isSegment(item as Record<string, unknown>))) {
      return true;
    }
  }
  return isSegment(record);
};

const isLogDiagnoserPayload = (value: unknown): boolean => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  const hasEvidence = Array.isArray(record.evidence);
  const hasIssues = Array.isArray(record.issues) || Array.isArray(record.identified_issues);
  const hasActions =
    Array.isArray(record.actions) ||
    Array.isArray(record.recommended_actions) ||
    Array.isArray(record.proposed_solutions);
  const hasAnswer = typeof record.answer === 'string' || typeof record.summary === 'string';
  return (hasEvidence && (hasIssues || hasActions)) || (hasAnswer && (hasIssues || hasActions));
};

const isInternalToolPayload = (value: unknown): boolean =>
  isInternalRetrievalPayload(value) || isStructuredLogPayload(value) || isLogDiagnoserPayload(value);

const INTERNAL_MARKER_REGEX =
  /"(retrieval_id|sources_searched|query_understood|customer_ready|internal_notes|recommended_actions|proposed_solutions|line_range|key_info|relevance_score|priority_concerns|identified_issues|structured_log)"/i;

const tryParseJson = (raw: string): unknown | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (
    !((trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']')))
  ) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
};

export function extractJsonObjects(text: string): string[] {
  const objects: string[] = [];
  const startIdx = text.indexOf('{');
  if (startIdx < 0) return objects;

  let idx = startIdx;
  while (idx >= 0 && idx < text.length) {
    const start = text.indexOf('{', idx);
    if (start < 0) break;

    let depth = 0;
    let inString = false;
    let escape = false;
    for (let i = start; i < text.length; i += 1) {
      const ch = text[i];
      if (inString) {
        if (escape) {
          escape = false;
        } else if (ch === '\\') {
          escape = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }
      if (ch === '"') {
        inString = true;
        continue;
      }
      if (ch === '{') depth += 1;
      if (ch === '}') depth -= 1;
      if (depth === 0) {
        objects.push(text.slice(start, i + 1));
        idx = i + 1;
        break;
      }
    }

    if (depth !== 0) break;
  }

  return objects;
}

export function extractJsonBlocks(text: string): string[] {
  const blocks: string[] = [];
  const startIdx = text.search(/[{\[]/);
  if (startIdx < 0) return blocks;

  let idx = startIdx;
  while (idx >= 0 && idx < text.length) {
    const braceIdx = text.indexOf('{', idx);
    const bracketIdx = text.indexOf('[', idx);
    const start =
      braceIdx >= 0 && bracketIdx >= 0
        ? Math.min(braceIdx, bracketIdx)
        : braceIdx >= 0
          ? braceIdx
          : bracketIdx;
    if (start < 0) break;

    const isArray = text[start] === '[';
    const openChar = isArray ? '[' : '{';
    const closeChar = isArray ? ']' : '}';
    let depth = 0;
    let inString = false;
    let escape = false;

    for (let i = start; i < text.length; i += 1) {
      const ch = text[i];
      if (inString) {
        if (escape) {
          escape = false;
        } else if (ch === '\\') {
          escape = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }
      if (ch === '"') {
        inString = true;
        continue;
      }
      if (ch === openChar) depth += 1;
      if (ch === closeChar) depth -= 1;
      if (depth === 0) {
        blocks.push(text.slice(start, i + 1));
        idx = i + 1;
        break;
      }
    }

    if (depth !== 0) break;
  }

  return blocks;
}

export function hasInternalToolPayload(text: string): boolean {
  if (!text) return false;
  if (INTERNAL_MARKER_REGEX.test(text)) return true;
  const blocks = extractJsonBlocks(text);
  for (const block of blocks) {
    const parsed = tryParseJson(block);
    if (parsed && isInternalToolPayload(parsed)) return true;
    if (INTERNAL_MARKER_REGEX.test(block)) return true;
  }
  return false;
}

export function stripInternalSearchPayloads(content: string): string {
  if (!content) return content;

  let changed = false;
  let cleaned = content;
  const hasMarkers = INTERNAL_MARKER_REGEX.test(cleaned);

  const fenceRegex = /```(?:json)?\s*([\s\S]*?)```/gi;
  cleaned = cleaned.replace(fenceRegex, (match, inner) => {
    const parsed = tryParseJson(inner);
    if (parsed && isInternalToolPayload(parsed)) {
      changed = true;
      return '';
    }
    return match;
  });

  const trimmed = stripCodeFence(cleaned).trim();
  const parsedTop = tryParseJson(trimmed);
  if (parsedTop && isInternalToolPayload(parsedTop)) {
    return '';
  }

  const blocks = extractJsonBlocks(cleaned);
  if (blocks.length) {
    let next = cleaned;
    blocks.forEach((block) => {
      const parsed = tryParseJson(block);
      if (parsed && isInternalToolPayload(parsed)) {
        next = next.replace(block, '');
        changed = true;
        return;
      }
      if (hasMarkers && INTERNAL_MARKER_REGEX.test(block)) {
        next = next.replace(block, '');
        changed = true;
      }
    });
    cleaned = next;
  }

  if (!changed && hasMarkers) {
    const pruned = cleaned
      .split('\n')
      .filter((line) => !INTERNAL_MARKER_REGEX.test(line))
      .filter((line) => {
        const trimmedLine = line.trim();
        return !['{', '}', '[', ']'].includes(trimmedLine);
      })
      .join('\n');
    cleaned = pruned;
    changed = true;
  }

  if (!changed) return content;

  const isPrefaceLine = (line: string): boolean => {
    const lower = line.toLowerCase();
    if (!/(json|retrieval|sources?\s+searched|kb|macros|feedme)/.test(lower)) return false;
    if (
      /(compile|format|results|following|below|here|required|provide|structured)/.test(lower) ||
      lower.startsWith('now i have') ||
      lower.startsWith('let me')
    ) {
      return true;
    }
    return false;
  };

  const lines = cleaned
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const filtered = lines.filter((line) => !isPrefaceLine(line));

  if (!filtered.length) return '';

  const cleanedResult = filtered.join('\n').replace(/\n{3,}/g, '\n\n').trim();
  if (changed) {
    const compact = cleanedResult.replace(/\s+/g, ' ').trim();
    const hasSentenceEnd = /[.!?]/.test(compact);
    if (compact.length < 180 && !hasSentenceEnd) {
      return '';
    }
  }

  return cleanedResult;
}

/**
 * Parse a potentially nested/wrapped output value into a usable object.
 * Handles various formats:
 * - Direct object/dict
 * - JSON string
 * - String with "content='{...}'" wrapper (from LangChain tool outputs)
 */
export function parseToolOutput(output: unknown): Record<string, unknown> {
  if (!output) return {};

  // Already an object
  if (typeof output === 'object' && output !== null && !Array.isArray(output)) {
    return output as Record<string, unknown>;
  }

  // Not a string - can't parse further
  if (typeof output !== 'string') return {};

  let text = output.trim();

  // Handle "content='{...}'" wrapper format from LangChain
  const startsWithContentSingle = text.startsWith("content='");
  const startsWithContentDouble = text.startsWith('content="');

  if (startsWithContentSingle || startsWithContentDouble) {
    const quoteChar = text[8]; // The quote character used
    const startPos = 9; // Position after "content='"

    // Find the JSON start (first { or [)
    const jsonStartBrace = text.indexOf('{', startPos);
    const jsonStartBracket = text.indexOf('[', startPos);
    const jsonStart = jsonStartBrace >= 0 && jsonStartBracket >= 0
      ? Math.min(jsonStartBrace, jsonStartBracket)
      : jsonStartBrace >= 0 ? jsonStartBrace : jsonStartBracket;

    if (jsonStart >= 0) {
      // Find the matching end by counting brackets
      const isArray = text[jsonStart] === '[';
      const openChar = isArray ? '[' : '{';
      const closeChar = isArray ? ']' : '}';
      let depth = 0;
      let inString = false;
      let escaped = false;
      let jsonEnd = -1;

      for (let i = jsonStart; i < text.length; i++) {
        const char = text[i];

        if (escaped) {
          escaped = false;
          continue;
        }

        if (char === '\\') {
          escaped = true;
          continue;
        }

        if (char === '"') {
          inString = !inString;
          continue;
        }

        if (!inString) {
          if (char === openChar) depth++;
          if (char === closeChar) {
            depth--;
            if (depth === 0) {
              jsonEnd = i;
              break;
            }
          }
        }
      }

      if (jsonEnd > jsonStart) {
        text = text.slice(jsonStart, jsonEnd + 1);
        // Unescape Python-style string escapes when wrapper used single quotes
        if (quoteChar === "'") {
          text = text.replace(/\\'/g, "'");
        }
        // Handle double-escaped sequences
        text = text.replace(/\\\\(["\\/bfnrtu])/g, '\\$1');
      }
    }
  }

  // Try parsing as JSON
  if ((text.startsWith('{') && text.endsWith('}')) ||
    (text.startsWith('[') && text.endsWith(']'))) {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === 'object' && parsed !== null) {
        return Array.isArray(parsed) ? { items: parsed } : parsed;
      }
    } catch {
      // Fall through to further attempts
    }
  }

  // Try to find JSON object in the string (handles prefix/suffix noise)
  const braceIdx = text.indexOf('{');
  const bracketIdx = text.indexOf('[');
  const startIdx = braceIdx >= 0 && bracketIdx >= 0
    ? Math.min(braceIdx, bracketIdx)
    : braceIdx >= 0 ? braceIdx : bracketIdx;

  if (startIdx >= 0) {
    // Try to find balanced JSON by bracket counting
    const isArray = text[startIdx] === '[';
    const openChar = isArray ? '[' : '{';
    const closeChar = isArray ? ']' : '}';
    let depth = 0;
    let inString = false;
    let escaped = false;
    let jsonEnd = -1;

    for (let i = startIdx; i < text.length; i++) {
      const char = text[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\') {
        escaped = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === openChar) depth++;
        if (char === closeChar) {
          depth--;
          if (depth === 0) {
            jsonEnd = i;
            break;
          }
        }
      }
    }

    if (jsonEnd > startIdx) {
      const candidate = text.slice(startIdx, jsonEnd + 1);
      try {
        const parsed = JSON.parse(candidate);
        if (typeof parsed === 'object' && parsed !== null) {
          return Array.isArray(parsed) ? { items: parsed } : parsed;
        }
      } catch {
        // Could not parse
      }
    }
  }

  return {};
}

/**
 * Extract todos from various payload formats
 * Handles nested structures, arrays, and different property names
 */
export function extractTodosFromPayload(input: any): any[] {
  const queue: any[] = [input];
  while (queue.length) {
    const raw = queue.shift();
    if (!raw) continue;

    if (typeof raw === 'string') {
      const stripped = stripCodeFence(raw);
      const direct = stripped.trim();
      const hasJsonFence = direct.startsWith('{') || direct.startsWith('[');
      if (hasJsonFence) {
        try {
          queue.push(JSON.parse(direct));
        } catch {
          // ignore
        }
      } else {
        // Try to extract the first JSON object/array from noisy strings
        const braceIdx = direct.indexOf('{');
        const bracketIdx = direct.indexOf('[');
        const candidates = [braceIdx, bracketIdx].filter((i) => i >= 0);
        const startIdx = candidates.length ? Math.min(...candidates) : -1;
        if (startIdx >= 0) {
          const isArray = direct[startIdx] === '[';
          const openChar = isArray ? '[' : '{';
          const closeChar = isArray ? ']' : '}';
          let depth = 0;
          let inString = false;
          let escaped = false;
          let jsonEnd = -1;

          for (let i = startIdx; i < direct.length; i++) {
            const char = direct[i];

            if (escaped) {
              escaped = false;
              continue;
            }

            if (char === '\\') {
              escaped = true;
              continue;
            }

            if (char === '"') {
              inString = !inString;
              continue;
            }

            if (!inString) {
              if (char === openChar) depth++;
              if (char === closeChar) {
                depth--;
                if (depth === 0) {
                  jsonEnd = i;
                  break;
                }
              }
            }
          }

          if (jsonEnd > startIdx) {
            const candidate = direct.slice(startIdx, jsonEnd + 1);
            try {
              queue.push(JSON.parse(candidate));
            } catch {
              // ignore parse failure and continue
            }
          }
        }
      }
      continue;
    }

    if (Array.isArray(raw)) {
      // Normalize array contents to plain objects and drop invalid entries
      const normalized = raw.reduce<any[]>((acc, item) => {
        if (item && typeof item === 'object' && !Array.isArray(item)) {
          const todo = { ...item };
          // Provide minimal defaults for common fields
          if (!('title' in todo) && 'id' in todo) {
            todo.title = String(todo.id);
          }
          acc.push(todo);
        }
        return acc;
      }, []);
      return normalized;
    }

    if (typeof raw === 'object') {
      if (Array.isArray(raw.todos)) return raw.todos;
      if (Array.isArray((raw as any).result?.todos)) return (raw as any).result.todos;
      if (Array.isArray((raw as any).items)) return (raw as any).items;
      if (Array.isArray((raw as any).steps)) return (raw as any).steps;
      if (Array.isArray((raw as any).value)) return (raw as any).value;
      // Explore nested containers for todos
      const nestedKeys = ['output', 'data', 'result', 'payload', 'content'];
      nestedKeys.forEach((key) => {
        if (raw && typeof raw === 'object' && key in raw) {
          queue.push((raw as any)[key]);
        }
      });
    }
  }
  return [];
}
