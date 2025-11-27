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

export function formatLogAnalysisResult(raw: any): string | null {
  if (!raw) return null;

  const normalized = normalizePayload(raw);
  if (!normalized) return null;

  let data: any = normalized;
  if (typeof normalized === 'string') {
    try {
      data = JSON.parse(normalized);
    } catch {
      return null;
    }
  }

  if (typeof data !== 'object') return null;

  const summary = data.overall_summary || data.summary;
  const health = data.health_status;
  const concerns: any[] = Array.isArray(data.priority_concerns) ? data.priority_concerns : [];
  const issues: any[] = Array.isArray(data.identified_issues || data.issues) ? (data.identified_issues || data.issues) : [];
  const solutions: any[] = Array.isArray(data.proposed_solutions || data.solutions) ? (data.proposed_solutions || data.solutions) : [];
  const confidence = data.confidence_level;

  const lines: string[] = [];
  if (summary) lines.push(`Summary: ${summary}`);
  if (health) lines.push(`Health: ${health}`);
  if (concerns.length) {
    const bullet = concerns.filter(Boolean).join('; ');
    if (bullet) lines.push(`Top concerns: ${bullet}`);
  }

  issues.forEach((issue) => {
    if (typeof issue !== 'object') return;
    const title = issue.title || '';
    const sev = issue.severity ? `[${issue.severity}] ` : '';
    const details = issue.details || issue.description || '';
    const line = `${sev}${title}`.trim();
    if (line || details) {
      lines.push(`- ${line}${line && details ? ': ' : ''}${details}`);
    }
  });

  solutions.forEach((solution) => {
    if (typeof solution !== 'object') return;
    const title = solution.title || 'Recommended action';
    const steps: string[] = Array.isArray(solution.steps) ? solution.steps : [];
    if (!steps.length) return;
    lines.push(`- ${title}:`);
    steps.forEach((step, idx) => {
      lines.push(`   ${idx + 1}. ${step}`);
    });
  });

  if (confidence !== undefined) {
    const pct = Math.round(Number(confidence) * 100);
    if (!Number.isNaN(pct)) {
      lines.push(`Confidence: ~${pct}%`);
    }
  }

  return lines.length ? lines.join('\n') : null;
}
