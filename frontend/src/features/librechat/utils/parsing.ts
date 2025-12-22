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
