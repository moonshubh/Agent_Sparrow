/**
 * Shared data-formatting helpers for AG-UI.
 */

/**
 * Human-friendly tool name (snake/camel → Title Case).
 */
export function formatToolName(name: string): string {
  const normalized = name
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

  if (!normalized) return '';

  return normalized
    .split(' ')
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : ''))
    .filter(Boolean)
    .join(' ');
}

/**
 * Summarize tool output for compact UI display.
 */
export function summarizeToolOutput(output: unknown, limit = 140): string {
  if (typeof output === 'string') {
    const trimmed = output.trim();
    return trimmed.length > limit ? `${trimmed.slice(0, limit)}…` : trimmed;
  }
  if (output && typeof output === 'object') {
    try {
      const text = JSON.stringify(output);
      return text.length > limit ? `${text.slice(0, limit)}…` : text;
    } catch {
      return '';
    }
  }
  return '';
}

/**
 * Summarize log-analysis JSON payloads for thinking traces.
 */
export function summarizeLogJson(raw: string): string | null {
  try {
    const parsed = JSON.parse(raw);
    const overall = parsed?.overall_summary || parsed?.summary;
    const health = parsed?.health_status;
    const concerns = Array.isArray(parsed?.priority_concerns) && parsed.priority_concerns.length > 0
      ? parsed.priority_concerns.slice(0, 2).join('; ')
      : null;
    const firstIssue =
      Array.isArray(parsed?.identified_issues) && parsed.identified_issues.length
        ? parsed.identified_issues[0]
        : null;
    const issueTitle = firstIssue?.title;
    const issueSeverity = firstIssue?.severity;
    const issueDetail = firstIssue?.details || firstIssue?.description;

    const parts: string[] = [];
    if (overall) parts.push(String(overall));
    if (health) parts.push(`Health: ${health}`);
    if (concerns) parts.push(`Concerns: ${concerns}`);
    if (issueTitle || issueSeverity || issueDetail) {
      const detail = [issueTitle, issueSeverity && `(${issueSeverity})`, issueDetail]
        .filter(Boolean)
        .join(' ');
      if (detail) parts.push(detail);
    }
    const out = parts.join(' · ');
    return out || 'Analyzing logs...';
  } catch {
    return null;
  }
}
