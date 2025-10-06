import { TimelineInput, TimelineStep } from '@/types/trace';

const PHASE_TITLES: Record<string, string> = {
  QUERY_ANALYSIS: 'Query analysis',
  CONTEXT_RECOGNITION: 'Context recognition',
  SOLUTION_MAPPING: 'Solution mapping',
  TOOL_ASSESSMENT: 'Tool assessment',
  RESPONSE_STRATEGY: 'Response strategy',
  QUALITY_ASSESSMENT: 'Quality assessment',
};

const redact = (s?: string): string | undefined => {
  if (!s) return s;
  let out = s;
  out = out.replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}/g, '[redacted-email]');
  out = out.replace(/(api[_-]?key|token|secret)[=: ]+[A-Za-z0-9-_]{8,}/gi, '$1=[redacted]');
  out = out.replace(/([A-Za-z]:\\[^\s]+|\/?(?:home|users|var|etc)\/(?:[^\s])+)/gi, '[redacted-path]');
  return out;
};

const truncate = (s: string, max = 300) => (s.length > max ? `${s.slice(0, max)}…` : s);

function stableId(parts: string[], prefix: string) {
  const key = parts.filter(Boolean).join('|').toLowerCase();
  if (!key) return `${prefix}-unknown`;
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return `${prefix}-${hash.toString(16)}`;
}

export function computeTimeline(input: TimelineInput): TimelineStep[] {
  const { dataParts = [], metadata, content = '', agentType, isStreaming } = input || {};
  const steps: TimelineStep[] = [];

  const parts = (dataParts as Array<{ type: string; data?: any }>).map(part => {
    if (!part) return null;
    if (part.type === 'data' && part.data && typeof part.data === 'object') {
      const innerType = (part.data as any).type;
      if (typeof innerType === 'string') {
        const innerData = (part.data as any).data ?? part.data;
        return { type: innerType, data: innerData };
      }
    }
    return part;
  }).filter(Boolean) as Array<{ type: string; data?: any }>;

  // Timeline step details from custom parts
  for (const part of parts) {
    if ((part?.type === 'timeline-step' || part?.type === 'data-timeline-step') && part.data) {
      const title = part.data.type || 'Step';
      const description = redact(part.data.description || '');
      const stat = String(part.data.status || '').toLowerCase();
      const status: TimelineStep['status'] = stat.includes('complete')
        ? 'completed'
        : stat.includes('error') || stat.includes('fail')
          ? 'failed'
          : 'in_progress';
      const existing = steps.find(s => s.title === title);
      if (existing) {
        existing.details = existing.details || {};
        if (description) existing.details.text = existing.details.text ? `${existing.details.text}\n${description}` : description;
        existing.status = status;
      } else {
        steps.push({ id: stableId(['timeline-step', title], 't'), title, status, details: description ? { text: description } : undefined });
      }
      continue;
    }

    if (part?.type === 'finish-step') {
      const idx = [...steps].reverse().findIndex(s => s.status === 'in_progress');
      const originalIdx = idx >= 0 ? steps.length - 1 - idx : -1;
      if (originalIdx >= 0) {
        steps[originalIdx].status = 'completed';
      } else if (steps.length > 0) {
        steps[steps.length - 1].status = 'completed';
      }
    }
  }

  // Reasoning stream (AI SDK native): aggregate into a single Thinking step
  let reasoningCollected = '';
  let reasoningSeen = false;
  let reasoningCompleted = false;
  for (const part of parts) {
    if (typeof part?.type === 'string' && part.type.startsWith('reasoning')) {
      reasoningSeen = true;
      const delta = (part as any)?.data?.delta ?? (part as any)?.delta ?? (part as any)?.text ?? '';
      if (typeof delta === 'string' && delta.trim()) {
        reasoningCollected += (reasoningCollected ? ' ' : '') + delta.trim();
      }
      if (part.type === 'reasoning-end') {
        reasoningCompleted = true;
      }
    }
  }
  if (reasoningSeen) {
    const description = redact(truncate(reasoningCollected || ''));
    const existing = steps.find(s => s.title === 'Thinking')
      || steps.find(s => s.title === 'Reasoning');
    const status: TimelineStep['status'] = reasoningCompleted ? 'completed' : 'in_progress';
    if (existing) {
      existing.status = status;
      if (description) {
        existing.details = existing.details || {};
        existing.details.text = existing.details.text ? `${existing.details.text}\n${description}` : description;
      }
    } else {
      steps.push({ id: stableId(['reasoning'], 'think'), title: 'Thinking', status, details: description ? { text: description } : undefined });
    }
  }

  // Primary agent inference from thinking trace
  const thinking = (parts.find(p => p.type === 'data-thinking')?.data)
    || (metadata && (metadata.thinking_trace || metadata.messageMetadata?.thinking_trace));

  if (thinking?.thinking_steps && Array.isArray(thinking.thinking_steps)) {
    for (const st of thinking.thinking_steps) {
      const title = PHASE_TITLES[st.phase] || st.phase?.toString()?.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) || 'Step';
      const text = redact(st.thought);
      const existing = steps.find(s => s.title === title);
      if (existing) {
        existing.details = existing.details || {};
        existing.details.text = existing.details.text ? `${existing.details.text}\n${text}` : text;
        existing.status = 'completed';
      } else {
        steps.push({ id: stableId(['phase', title], 'phase'), title, status: 'completed', details: { text } });
      }
    }
  }

  // Tool results
  const toolRes = parts.find(p => p.type === 'data-tool-result' || p.type === 'tool-result')?.data
    || metadata?.toolResults;
  const hasExplicitToolSteps = steps.some(s => s.title.toLowerCase().startsWith('tool'));
  if (toolRes && !hasExplicitToolSteps) {
    steps.push({
      id: stableId(['tools', toolRes?.id ?? toolRes?.name ?? 'tools'], 'tools'),
      title: 'Tools',
      status: 'completed',
      details: {
        text: redact(toolRes.reasoning || toolRes.summary || ''),
        toolIO: toolRes,
      },
    });
  }

  // Log analysis post hoc derivation
  const analysis = metadata?.analysisResults || metadata?.messageMetadata?.analysisResults;
  if (agentType === 'log_analysis' && analysis && typeof analysis === 'object') {
    const derived: TimelineStep[] = [];
    if (analysis.ingestion_metadata || analysis.system_metadata) {
      const lines = analysis?.ingestion_metadata?.line_count;
      const errs = analysis?.system_metadata?.error_count;
      derived.push({ id: stableId(['log', 'ingestion'], 'ingest'), title: 'Ingestion & parsing', status: 'completed', details: { text: truncate(`Entries: ${lines ?? 'N/A'}, Errors: ${errs ?? 'N/A'}`) } });
    }
    if (Array.isArray(analysis.identified_issues) && analysis.identified_issues.length) {
      derived.push({ id: stableId(['log', 'issues'], 'issues'), title: 'Issues detected', status: 'completed', details: { text: truncate(analysis.identified_issues[0]?.description || analysis.identified_issues[0]?.title || 'Issues found') } });
    }
    if (analysis.overall_summary || analysis.root_cause || analysis.priority_concerns) {
      const rc = analysis.root_cause || analysis.priority_concerns?.[0];
      derived.push({ id: stableId(['log', 'root'], 'root'), title: 'Root cause', status: 'completed', details: { text: truncate(rc?.summary || analysis.overall_summary || '') } });
    }
    if (Array.isArray(analysis.proposed_solutions) && analysis.proposed_solutions.length) {
      derived.push({ id: stableId(['log', 'solutions'], 'solutions'), title: 'Solutions', status: 'completed', details: { text: truncate(analysis.proposed_solutions[0]?.title || 'See solutions below') } });
    }
    if (analysis.validation_summary) {
      derived.push({ id: stableId(['log', 'verification'], 'verify'), title: 'Verification', status: 'completed', details: { text: truncate(typeof analysis.validation_summary === 'string' ? analysis.validation_summary : JSON.stringify(analysis.validation_summary)) } });
    }

    for (const step of derived) {
      const existing = steps.find(s => s.title === step.title);
      if (existing) {
        existing.status = step.status;
        existing.details = step.details;
      } else {
        steps.push(step);
      }
    }
  }

  // Heuristic fallback when we don't have explicit reasoning steps
  const hasDetailedSteps = steps.some(step => step.details?.text && step.title !== 'Tools' && step.title !== 'Answer');
  const hasToolData = Boolean(toolRes) || steps.some(step => step.title.toLowerCase().startsWith('tool'));
  const hasFollowups = Boolean(metadata?.followUpQuestions || metadata?.followupQuestions || metadata?.messageMetadata?.followUpQuestions)
    || parts.some(p => p.type === 'data-followups');

  if (!hasDetailedSteps) {
    const heuristicSteps: TimelineStep[] = [];
    heuristicSteps.push({
      id: stableId(['heuristic', 'analysis'], 'heuristic'),
      title: 'Understanding request',
      status: isStreaming ? 'in_progress' : 'completed',
    });
    heuristicSteps.push({
      id: stableId(['heuristic', 'tools'], 'heuristic'),
      title: 'Evaluating tools & data',
      status: hasToolData ? 'completed' : isStreaming ? 'pending' : 'completed',
    });
    heuristicSteps.push({
      id: stableId(['heuristic', 'drafting'], 'heuristic'),
      title: 'Drafting response',
      status: isStreaming ? 'in_progress' : 'completed',
    });
    if (hasFollowups) {
      heuristicSteps.push({
        id: stableId(['heuristic', 'followups'], 'heuristic'),
        title: 'Planning next steps',
        status: 'completed',
      });
    }

    const existingTitles = new Set(steps.map(s => s.title));
    const filteredHeuristics = heuristicSteps.filter(step => !existingTitles.has(step.title));
    if (filteredHeuristics.length) {
      steps.unshift(...filteredHeuristics);
    }
  }

  const answerStep = steps.find(s => s.title === 'Answer');
  if (isStreaming) {
    if (answerStep) {
      answerStep.status = 'in_progress';
      if (answerStep.details) delete answerStep.details.text;
    } else {
      steps.push({ id: stableId(['answer'], 'answer'), title: 'Answer', status: 'in_progress' });
    }
  } else if (content) {
    const text = truncate(content);
    if (answerStep) {
      answerStep.status = 'completed';
      answerStep.details = { ...(answerStep.details || {}), text };
    } else {
      steps.push({ id: stableId(['answer'], 'answer'), title: 'Answer', status: 'completed', details: { text } });
    }
  }

  return steps;
}
