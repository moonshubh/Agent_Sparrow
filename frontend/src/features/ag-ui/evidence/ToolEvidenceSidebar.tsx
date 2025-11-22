'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ToolEvidenceCard } from './ToolEvidenceCard';
import { TimelineOperation } from '../timeline/AgenticTimelineView';

interface ToolEvidenceSidebarProps {
  operations: TimelineOperation[];
  toolEvidence: Record<string, any>;
  className?: string;
}

export const ToolEvidenceSidebar: React.FC<ToolEvidenceSidebarProps> = ({
  operations,
  toolEvidence,
  className = ''
}) => {
  // Filter for tool operations that have evidence
  const evidenceItems = operations
    .filter(op => {
      // Skip rendering todo updates as tool evidence; they belong in Run Tasks
      if (op.name?.toLowerCase().includes('write_todos')) return false;
      const evidence = toolEvidence[op.id];
      if (evidence?.toolName === 'write_todos') return false;
      return op.type === 'tool' && evidence;
    })
    .map(op => {
      const evidence = toolEvidence[op.id];
      const outputText = typeof evidence.output === 'string'
        ? evidence.output
        : JSON.stringify(evidence.output ?? '', null, 2);
      const snippet = (evidence.summary || outputText || '').toString().replace(/\s+/g, ' ').slice(0, 160);
      const url = typeof evidence.output === 'string' && evidence.output.startsWith('http')
        ? evidence.output
        : typeof evidence.metadata?.url === 'string'
          ? evidence.metadata.url
          : undefined;
      return {
        id: op.id,
        // Map tool names to types
        type: (op.name.includes('search') || op.name.includes('retriev')) ? 'research' as const
          : op.name.includes('log') ? 'log_analysis' as const
            : op.name.includes('memory') ? 'knowledge' as const
              : 'grounding' as const,
        title: evidence.toolName || op.name,
        snippet: snippet || 'No output available',
        url,
        fullContent: outputText,
        status: op.status === 'success' ? 'success' as const : 'partial' as const,
        timestamp: op.endTime ? new Date(op.endTime).toLocaleTimeString() : undefined,
        metadata: op.metadata
      };
    })
    .reverse(); // Show newest first

  if (evidenceItems.length === 0) {
    return null;
  }

  return (
    <div className={`space-y-4 ${className}`}>
      <AnimatePresence initial={false}>
        {evidenceItems.map((item) => (
          <ToolEvidenceCard
            key={item.id}
            {...item}
          />
        ))}
      </AnimatePresence>
    </div>
  );
};
