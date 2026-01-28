import { parseToolOutput, stripCodeFence } from '../utils';

const normalizePayload = (raw: any): any => {
  if (!raw) return null;
  if (typeof raw === 'string') return raw;
  // AG-UI / LangChain messages sometimes wrap text in an array of content parts
  if (Array.isArray(raw)) {
    const asText = raw
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part && typeof part === 'object') {
          if (typeof (part as any).text === 'string') return (part as any).text;
          return JSON.stringify(part);
        }
        return '';
      })
      .join('');
    return asText || null;
  }
  if (typeof raw === 'object') return raw;
  return null;
};

const unwrapCandidate = (value: any): any => {
  if (!value || typeof value !== 'object') return value;

  const maybeObj = (candidate: any): any => {
    if (!candidate) return null;
    if (Array.isArray(candidate)) {
      return candidate.find((item) => item && typeof item === 'object' && !Array.isArray(item)) || null;
    }
    if (typeof candidate === 'object') return candidate;
    return null;
  };

  return (
    maybeObj((value as any).result) ||
    maybeObj((value as any).output) ||
    maybeObj((value as any).data) ||
    maybeObj((value as any).value) ||
    maybeObj((value as any).content) ||
    value
  );
};

export function formatLogAnalysisResult(raw: any): string | null {
  if (!raw) return null;

  const normalized = normalizePayload(raw);
  if (!normalized) return null;

  let data: any = normalized;
  if (typeof normalized === 'string') {
    const stripped = stripCodeFence(normalized);
    try {
      data = JSON.parse(stripped);
    } catch {
      data = parseToolOutput(stripped);
    }
  }

  data = unwrapCandidate(data);
  if (data && typeof data === 'object' && Array.isArray((data as any).items)) {
    const items = (data as any).items as any[];
    const unwrappedItems = items
      .map((item) => unwrapCandidate(item))
      .filter((item) => item && typeof item === 'object' && !Array.isArray(item));

    if (unwrappedItems.length === 1) {
      data = unwrappedItems[0] || data;
    } else if (unwrappedItems.length > 1) {
      const merged: any = {
        priority_concerns: [],
        identified_issues: [],
        proposed_solutions: [],
      };

      for (const item of unwrappedItems) {
        if (!merged.overall_summary && (item as any).overall_summary) merged.overall_summary = (item as any).overall_summary;
        if (!merged.summary && (item as any).summary) merged.summary = (item as any).summary;
        if (!merged.health_status && (item as any).health_status) merged.health_status = (item as any).health_status;
        if (merged.confidence_level === undefined && (item as any).confidence_level !== undefined) {
          merged.confidence_level = (item as any).confidence_level;
        }

        const concerns = (item as any).priority_concerns;
        if (Array.isArray(concerns)) merged.priority_concerns.push(...concerns);

        const issues = (item as any).identified_issues || (item as any).issues;
        if (Array.isArray(issues)) merged.identified_issues.push(...issues);

        const solutions = (item as any).proposed_solutions || (item as any).solutions;
        if (Array.isArray(solutions)) merged.proposed_solutions.push(...solutions);
      }

      const looksLikeIssue = (obj: any) =>
        obj &&
        typeof obj === 'object' &&
        (typeof obj.title === 'string' || typeof obj.details === 'string' || typeof obj.description === 'string');
      if (!merged.identified_issues.length) {
        const issueLike = unwrappedItems.filter(looksLikeIssue);
        if (issueLike.length) merged.identified_issues = issueLike;
      }

      data = merged;
    }
  }

  if (data && typeof data === 'object') {
    const customerReady = (data as any).customer_ready || (data as any).customerReady;
    if (typeof customerReady === 'string' && customerReady.trim()) {
      return customerReady.trim();
    }
  }

  // typeof null === 'object' in JS, so explicit null check needed
  if (data === null || typeof data !== 'object') return null;

  const summary = data.overall_summary || data.summary;
  const health = data.health_status;
  const concerns: any[] = Array.isArray(data.priority_concerns) ? data.priority_concerns : [];
  const issues: any[] = Array.isArray(data.identified_issues || data.issues) ? (data.identified_issues || data.issues) : [];
  const solutions: any[] = Array.isArray(data.proposed_solutions || data.solutions) ? (data.proposed_solutions || data.solutions) : [];
  const recommendedActions: string[] = Array.isArray((data as any).recommended_actions)
    ? (data as any).recommended_actions.filter((item: any) => typeof item === 'string')
    : [];
  const confidence = data.confidence_level;

  const lines: string[] = [];
  const hasDiagnosis = summary || health || concerns.length || issues.length;
  if (hasDiagnosis) {
    lines.push('## The Diagnosis');
    if (summary) lines.push(summary);
    if (health) lines.push(`- Health: ${health}`);
    if (concerns.length) {
      lines.push('**Top concerns**');
      concerns.filter(Boolean).forEach((item) => lines.push(`- ${item}`));
    }
  }

  issues.forEach((issue) => {
    if (typeof issue !== 'object') return;
    const title = issue.title || '';
    const sev = issue.severity ? `[${issue.severity}] ` : '';
    const details = issue.details || issue.description || '';
    const line = `${sev}${title}`.trim();
    if (line || details) {
      if (!hasDiagnosis) {
        lines.push('## The Diagnosis');
      }
      lines.push(`- ${line}${line && details ? ': ' : ''}${details}`);
    }
  });

  if (solutions.length) {
    if (lines.length) lines.push('');
    lines.push('## How to Fix It');
    solutions.forEach((solution, index) => {
      if (typeof solution !== 'object') return;
      const title = solution.title || 'Recommended action';
      const steps: string[] = Array.isArray(solution.steps) ? solution.steps : [];
      if (!steps.length) return;
      lines.push(`**Step ${index + 1}: ${title}**`);
      steps.forEach((step, idx) => {
        lines.push(`${idx + 1}. ${step}`);
      });
    });
  } else if (recommendedActions.length) {
    if (lines.length) lines.push('');
    lines.push('## How to Fix It');
    recommendedActions.slice(0, 10).forEach((action, index) => {
      lines.push(`${index + 1}. ${action}`);
    });
  }

  if (confidence !== undefined) {
    const pct = Math.round(Number(confidence) * 100);
    if (!Number.isNaN(pct)) {
      if (lines.length) lines.push('');
      lines.push(`Confidence: ~${pct}%`);
    }
  }

  return lines.length ? lines.join('\n') : null;
}

const hasStructuredMarkdown = (text: string): boolean => {
  if (!text) return false;
  return /(^|\n)\s*##\s+/.test(text) || /(^|\n)\s*[-*]\s+/.test(text) || /(^|\n)\s*\d+\.\s+/.test(text);
};

export function formatLogAnalysisText(raw: string): string | null {
  if (!raw) return null;
  const text = raw.trim();
  if (!text || hasStructuredMarkdown(text)) return null;

  const labelRegex = /([A-Z][A-Za-z0-9 /&()_-]{2,50}):/g;
  const matches = [...text.matchAll(labelRegex)];
  if (matches.length < 2) return null;

  const sections: { label: string; body: string }[] = [];
  for (let i = 0; i < matches.length; i += 1) {
    const current = matches[i];
    const start = current.index ?? 0;
    const end = i + 1 < matches.length ? matches[i + 1].index ?? text.length : text.length;
    const label = current[1].trim();
    const body = text.slice(start + current[0].length, end).trim();
    if (label && body) sections.push({ label, body });
  }

  if (sections.length < 2) return null;

  const diagnosis = sections.shift();
  const lines: string[] = [];
  if (diagnosis) {
    lines.push('## 🔍 The Diagnosis', diagnosis.body.trim());
  }

  lines.push('', '## ✅ How to Fix It');
  sections.forEach((section, index) => {
    lines.push(`${index + 1}. **${section.label}:** ${section.body}`);
  });

  return lines.join('\n');
}
