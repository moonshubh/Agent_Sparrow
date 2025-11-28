'use client';

import React from 'react';
import { AnimatePresence } from 'framer-motion';
import { ToolEvidenceCard } from './ToolEvidenceCard';
import type { TimelineOperation } from '../timeline/AgenticTimelineView';
import type { ToolEvidenceUpdateEvent, ToolEvidenceCard as EvidenceCard } from '@/services/ag-ui/event-types';

type EvidenceType = 'grounding' | 'research' | 'knowledge' | 'log_analysis';

type NormalizedEvidenceItem = {
  id: string;
  type: EvidenceType;
  title: string;
  snippet: string;
  url?: string;
  fullContent: string;
  status: 'success' | 'partial';
  timestamp?: string;
  metadata?: Record<string, unknown>;
};

type EvidencePayload = ToolEvidenceUpdateEvent & {
  cards?: EvidenceCard[];
  metadata?: Record<string, unknown>;
};

interface ToolEvidenceSidebarProps {
  operations: TimelineOperation[];
  toolEvidence: Record<string, EvidencePayload>;
  className?: string;
}

const deriveEvidenceType = (hint?: string): EvidenceType => {
  const normalized = hint?.toLowerCase() || '';
  if (normalized.includes('log')) return 'log_analysis';
  if (normalized.includes('search') || normalized.includes('retriev')) return 'research';
  if (normalized.includes('knowledge') || normalized.includes('memory')) return 'knowledge';
  return 'grounding';
};

const stringifyContent = (content: unknown): string => {
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content ?? '', null, 2);
  } catch {
    return String(content ?? '');
  }
};

const normalizeSnippet = (value: unknown): string => {
  const raw = typeof value === 'string' ? value : stringifyContent(value);
  const compact = raw.replace(/\s+/g, ' ').trim();
  return compact ? compact.slice(0, 160) : 'No output available';
};

const deriveUrl = (
  output: unknown,
  metadata?: Record<string, unknown>
): string | undefined => {
  if (typeof output === 'string' && output.startsWith('http')) return output;
  const metaUrl =
    metadata && typeof (metadata as { url?: unknown }).url === 'string'
      ? (metadata as { url?: string }).url
      : undefined;
  return metaUrl;
};

const normalizeStatus = (
  status?: string,
  opStatus?: TimelineOperation['status']
): NormalizedEvidenceItem['status'] => {
  if (status === 'success' || opStatus === 'success') return 'success';
  return 'partial';
};

const mapCardToEvidenceItem = ({
  card,
  idx,
  baseId,
  fallbackName,
  opEndTime,
  opMetadata,
  opStatus,
  evidence,
}: {
  card: EvidenceCard;
  idx: number;
  baseId: string;
  fallbackName?: string;
  opEndTime?: string | Date;
  opMetadata?: Record<string, unknown>;
  opStatus?: TimelineOperation['status'];
  evidence: EvidencePayload;
}): NormalizedEvidenceItem => {
  const timestampSource = card.timestamp ?? opEndTime;
  const status = normalizeStatus(card.status, opStatus);

  return {
    id: `${baseId}-${idx}`,
    type: deriveEvidenceType(card.type || fallbackName || evidence.toolName),
    title: card.title || evidence.toolName || fallbackName || 'Tool',
    snippet: normalizeSnippet(card.snippet ?? evidence.summary),
    url: card.url || deriveUrl(card.fullContent, card.metadata) || deriveUrl(evidence.output, evidence.metadata),
    fullContent: stringifyContent(card.fullContent ?? evidence.output),
    status,
    timestamp: timestampSource ? new Date(timestampSource).toISOString() : undefined,
    metadata: card.metadata || evidence.metadata || opMetadata,
  };
};

const mapFallbackEvidenceItem = ({
  evidence,
  baseId,
  fallbackName,
  opEndTime,
  opMetadata,
  opStatus,
}: {
  evidence: EvidencePayload;
  baseId: string;
  fallbackName?: string;
  opEndTime?: string | Date;
  opMetadata?: Record<string, unknown>;
  opStatus?: TimelineOperation['status'];
}): NormalizedEvidenceItem => {
  const outputText = stringifyContent(evidence.output);
  const status = normalizeStatus(undefined, opStatus);

  return {
    id: baseId,
    type: deriveEvidenceType(fallbackName || evidence.toolName),
    title: evidence.toolName || fallbackName || 'Tool',
    snippet: normalizeSnippet(evidence.summary ?? outputText),
    url: deriveUrl(evidence.output, evidence.metadata),
    fullContent: outputText,
    status,
    timestamp: opEndTime ? new Date(opEndTime).toISOString() : undefined,
    metadata: evidence.metadata || opMetadata,
  };
};

const mapEvidencePayloadToItems = ({
  evidence,
  baseId,
  opName,
  opEndTime,
  opMetadata,
  opStatus,
}: {
  evidence: EvidencePayload;
  baseId: string;
  opName?: string;
  opEndTime?: string | Date;
  opMetadata?: Record<string, unknown>;
  opStatus?: TimelineOperation['status'];
}): NormalizedEvidenceItem[] => {
  const cards = Array.isArray(evidence.cards) && evidence.cards.length > 0 ? evidence.cards : null;
  const fallbackName = evidence.toolName || opName || baseId;

  if (cards) {
    return cards.map((card, idx) =>
      mapCardToEvidenceItem({
        card,
        idx,
        baseId,
        fallbackName,
        opEndTime,
        opMetadata,
        opStatus,
        evidence,
      })
    );
  }

  return [
    mapFallbackEvidenceItem({
      evidence,
      baseId,
      fallbackName,
      opEndTime,
      opMetadata,
      opStatus,
    }),
  ];
};

export const ToolEvidenceSidebar: React.FC<ToolEvidenceSidebarProps> = ({
  operations,
  toolEvidence,
  className = '',
}) => {
  // Filter for tool operations that have evidence
  const evidenceItems = operations
    .filter((op) => {
      if (op.name?.toLowerCase().includes('write_todos')) return false;
      const evidence = toolEvidence[op.id];
      if (evidence?.toolName === 'write_todos') return false;
      return op.type === 'tool' && Boolean(evidence);
    })
    .flatMap((op) => {
      const evidence = toolEvidence[op.id];
      if (!evidence) return [];
      return mapEvidencePayloadToItems({
        evidence,
        baseId: op.id,
        opName: op.name,
        opEndTime: op.endTime,
        opMetadata: op.metadata,
        opStatus: op.status,
      });
    })
    .reverse(); // Show newest first

  // Fallback: if no operations match, try rendering any evidence by id
  const existingIds = new Set(evidenceItems.map((e) => e.id));
  if (evidenceItems.length === 0 && toolEvidence && Object.keys(toolEvidence).length) {
    Object.entries(toolEvidence).forEach(([id, evidence]) => {
      if (!evidence || evidence.toolName === 'write_todos' || existingIds.has(id)) return;
      const items = mapEvidencePayloadToItems({
        evidence,
        baseId: id,
        opName: evidence.toolName || id,
      });
      items.forEach((item) => evidenceItems.push(item));
    });
  }

  if (evidenceItems.length === 0) {
    return null;
  }

  return (
    <div className={`space-y-4 ${className}`}>
      <AnimatePresence initial={false}>
        {evidenceItems.map((item) => (
          <ToolEvidenceCard key={item.id} {...item} />
        ))}
      </AnimatePresence>
    </div>
  );
};
