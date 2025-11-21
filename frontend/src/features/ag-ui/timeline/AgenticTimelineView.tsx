'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle2,
  Circle,
  Clock,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Terminal,
  BrainCircuit,
  Search,
  Database,
  Cpu
} from 'lucide-react';
import './agentic-timeline.css';

export type OperationStatus = 'pending' | 'running' | 'success' | 'error';
export type OperationType = 'agent' | 'tool' | 'chain' | 'thought' | 'todo';

export interface TimelineOperation {
  id: string;
  type: OperationType;
  name: string;
  description?: string;
  status: OperationStatus;
  startTime?: Date;
  endTime?: Date;
  duration?: number;
  parent?: string;
  children?: string[];
  parallelGroup?: string;
  metadata?: Record<string, any>;
  error?: string;
}

interface AgenticTimelineViewProps {
  operations: TimelineOperation[];
  currentOperation?: string;
  className?: string;
}

const StatusIcon = ({ status, type }: { status: OperationStatus; type: OperationType }) => {
  if (status === 'running') {
    return <Circle className="node-icon" />;
  }
  if (status === 'success') {
    return <CheckCircle2 className="node-icon" />;
  }
  if (status === 'error') {
    return <AlertCircle className="node-icon" />;
  }
  return <Circle className="node-icon opacity-50" />;
};

const TypeIcon = ({ type }: { type: OperationType }) => {
  switch (type) {
    case 'agent':
      return <BrainCircuit className="w-3 h-3" />;
    case 'tool':
      return <Terminal className="w-3 h-3" />;
    case 'chain':
      return <Cpu className="w-3 h-3" />;
    case 'thought':
      return <Search className="w-3 h-3" />;
    case 'todo':
      return <CheckCircle2 className="w-3 h-3" />;
    default:
      return <Database className="w-3 h-3" />;
  }
};

export const AgenticTimelineView: React.FC<AgenticTimelineViewProps> = ({
  operations,
  currentOperation,
  className = ''
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousLengthRef = useRef<number>(0);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Auto-scroll to bottom
  useEffect(() => {
    if (!containerRef.current) return;
    const previous = previousLengthRef.current;
    if (operations.length > previous) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
    previousLengthRef.current = operations.length;
  }, [operations.length]);

  const toggleNode = (id: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return '';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  // Filter out root agent operation to avoid redundancy if desired, 
  // or keep it for completeness. Here we keep everything but style it cleanly.
  const displayOperations = operations;

  return (
    <div className={`agentic-timeline-container ${className}`} ref={containerRef}>
      <div className="timeline-content">
        <AnimatePresence initial={false}>
          {displayOperations.map((op, index) => (
            <motion.div
              key={op.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className={`timeline-node status-${op.status} ${currentOperation === op.id ? 'active' : ''}`}
              onClick={() => toggleNode(op.id)}
            >
              {/* Connector Line */}
              {index !== displayOperations.length - 1 && <div className="node-connector" />}

              {/* Icon */}
              <div className="node-icon-wrapper">
                <StatusIcon status={op.status} type={op.type} />
              </div>

              {/* Info */}
              <div className="node-info">
                <div className="node-header">
                  <span className="node-name" title={op.name}>
                    {op.name}
                  </span>
                  <span className="node-duration">
                    {formatDuration(op.duration)}
                  </span>
                </div>

                {op.description && (
                  <div className="node-details">{op.description}</div>
                )}

                {/* Expanded Details */}
                <AnimatePresence>
                  {expandedNodes.has(op.id) && op.metadata && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="detail-panel"
                    >
                      {Object.entries(op.metadata).map(([key, value]) => (
                        <div key={key} className="detail-row">
                          <span className="detail-key">{key}:</span>
                          <span className="detail-value">
                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                          </span>
                        </div>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};
