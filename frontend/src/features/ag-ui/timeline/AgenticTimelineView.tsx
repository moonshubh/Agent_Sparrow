/**
 * Agentic Timeline View
 * Complete workflow visualization with parallel operations and branching
 */

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play,
  Pause,
  CheckCircle,
  XCircle,
  AlertCircle,
  GitBranch,
  Clock,
  Zap,
  Database,
  Search,
  FileText,
  Users,
  Layers,
  ChevronRight,
  ChevronDown
} from 'lucide-react';
import { timelineBranchAnimation, crystalCardAnimation } from '@/shared/animations/crystalline-animations';
import './agentic-timeline.css';

export type OperationStatus = 'pending' | 'running' | 'success' | 'error' | 'skipped';
export type OperationType = 'agent' | 'tool' | 'subagent' | 'decision' | 'memory' | 'search';

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

export interface AgenticTimelineViewProps {
  operations: TimelineOperation[];
  currentOperation?: string;
  isPlaying?: boolean;
  onOperationClick?: (operation: TimelineOperation) => void;
  onPlayPause?: () => void;
  className?: string;
}

const operationIcons: Record<OperationType, React.ReactNode> = {
  agent: <Users className="w-4 h-4" />,
  tool: <Zap className="w-4 h-4" />,
  subagent: <Layers className="w-4 h-4" />,
  decision: <GitBranch className="w-4 h-4" />,
  memory: <Database className="w-4 h-4" />,
  search: <Search className="w-4 h-4" />
};

const operationColors: Record<OperationType, string> = {
  agent: 'var(--crystal-cyan-400)',
  tool: 'var(--accent-amber-400)',
  subagent: 'var(--accent-gold-400)',
  decision: 'var(--status-warning)',
  memory: 'var(--status-info)',
  search: 'var(--crystal-cyan-300)'
};

const statusColors: Record<OperationStatus, string> = {
  pending: 'var(--neutral-500)',
  running: 'var(--accent-amber-400)',
  success: 'var(--status-success)',
  error: 'var(--status-error)',
  skipped: 'var(--neutral-600)'
};

export const AgenticTimelineView: React.FC<AgenticTimelineViewProps> = ({
  operations,
  currentOperation,
  isPlaying = false,
  onOperationClick,
  onPlayPause,
  className = ''
}) => {
  const [selectedOperation, setSelectedOperation] = useState<TimelineOperation | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  // Build operation hierarchy
  const buildHierarchy = () => {
    const roots: TimelineOperation[] = [];
    const opMap = new Map<string, TimelineOperation>();

    operations.forEach(op => opMap.set(op.id, op));

    operations.forEach(op => {
      if (!op.parent) {
        roots.push(op);
      }
    });

    return roots;
  };

  const rootOperations = buildHierarchy();

  // Get parallel operations
  const getParallelOperations = (groupId: string): TimelineOperation[] => {
    return operations.filter(op => op.parallelGroup === groupId);
  };

  // Toggle group expansion
  const toggleGroup = (groupId: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(groupId)) {
      newExpanded.delete(groupId);
    } else {
      newExpanded.add(groupId);
    }
    setExpandedGroups(newExpanded);
  };

  // Handle operation click
  const handleOperationClick = (operation: TimelineOperation) => {
    setSelectedOperation(operation);
    onOperationClick?.(operation);
  };

  return (
    <motion.div
      ref={containerRef}
      className={`agentic-timeline-view glass-panel ${className}`}
      variants={crystalCardAnimation}
      initial="hidden"
      animate="visible"
    >
      {/* Timeline Header */}
      <div className="timeline-header">
        <div className="header-left">
          <div className="timeline-icon">
            <GitBranch className="w-5 h-5" />
          </div>
          <div className="header-text">
            <h3 className="timeline-title">Agent Workflow</h3>
            <p className="timeline-subtitle">
              {operations.filter(op => op.status === 'success').length} / {operations.length} completed
            </p>
          </div>
        </div>
        <div className="header-actions">
          {onPlayPause && (
            <motion.button
              className="play-pause-btn"
              onClick={onPlayPause}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              aria-label={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </motion.button>
          )}
        </div>
      </div>

      {/* Timeline Content */}
      <div className="timeline-content">
        <svg className="timeline-connections">
          {operations.map((op, index) => {
            if (!op.parent) return null;

            const parent = operations.find(o => o.id === op.parent);
            if (!parent) return null;

            const parentIndex = operations.indexOf(parent);
            const startY = 80 + parentIndex * 100;
            const endY = 80 + index * 100;

            return (
              <motion.path
                key={`connection-${op.id}`}
                d={`M 40 ${startY} Q 40 ${(startY + endY) / 2}, 40 ${endY}`}
                className="timeline-connection"
                stroke={operationColors[op.type]}
                strokeWidth="2"
                fill="none"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.3 }}
                transition={{ duration: 0.5, delay: index * 0.1 }}
              />
            );
          })}
        </svg>

        <div className="operations-list">
          {rootOperations.map((operation, index) => (
            <OperationNode
              key={operation.id}
              operation={operation}
              allOperations={operations}
              level={0}
              index={index}
              isSelected={selectedOperation?.id === operation.id}
              isCurrent={currentOperation === operation.id}
              onClick={handleOperationClick}
              expandedGroups={expandedGroups}
              onToggleGroup={toggleGroup}
            />
          ))}
        </div>
      </div>

      {/* Operation Detail Panel */}
      <AnimatePresence>
        {selectedOperation && (
          <OperationDetailPanel
            operation={selectedOperation}
            onClose={() => setSelectedOperation(null)}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// Operation Node Component
const OperationNode: React.FC<{
  operation: TimelineOperation;
  allOperations: TimelineOperation[];
  level: number;
  index: number;
  isSelected: boolean;
  isCurrent: boolean;
  onClick: (op: TimelineOperation) => void;
  expandedGroups: Set<string>;
  onToggleGroup: (groupId: string) => void;
}> = ({
  operation,
  allOperations,
  level,
  index,
  isSelected,
  isCurrent,
  onClick,
  expandedGroups,
  onToggleGroup
}) => {
  const hasChildren = operation.children && operation.children.length > 0;
  const isExpanded = expandedGroups.has(operation.id);
  const icon = operationIcons[operation.type];
  const color = operationColors[operation.type];
  const statusColor = statusColors[operation.status];

  // Get child operations
  const children = hasChildren
    ? allOperations.filter(op => operation.children?.includes(op.id))
    : [];

  // Check if operation is part of parallel group
  const parallelSiblings = operation.parallelGroup
    ? allOperations.filter(op => op.parallelGroup === operation.parallelGroup && op.id !== operation.id)
    : [];

  return (
    <>
      <motion.div
        className={`operation-node ${operation.status} ${isSelected ? 'selected' : ''} ${isCurrent ? 'current' : ''}`}
        style={{
          '--operation-color': color,
          '--status-color': statusColor,
          '--level-indent': `${level * 40}px`
        } as React.CSSProperties}
        variants={timelineBranchAnimation}
        initial="hidden"
        animate="visible"
        custom={index}
        onClick={() => onClick(operation)}
      >
        {/* Expand/Collapse Button */}
        {hasChildren && (
          <button
            className="expand-btn"
            onClick={(e) => {
              e.stopPropagation();
              onToggleGroup(operation.id);
            }}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}

        {/* Operation Icon */}
        <div className="operation-icon">{icon}</div>

        {/* Operation Content */}
        <div className="operation-content">
          <div className="operation-header">
            <h4 className="operation-name">{operation.name}</h4>
            {operation.duration && (
              <span className="operation-duration">
                <Clock className="w-3 h-3" />
                {Math.round(operation.duration)}ms
              </span>
            )}
          </div>
          {operation.description && (
            <p className="operation-description">{operation.description}</p>
          )}
          {parallelSiblings.length > 0 && (
            <div className="parallel-indicator">
              <GitBranch className="w-3 h-3" />
              Parallel with {parallelSiblings.length} other operations
            </div>
          )}
        </div>

        {/* Status Badge */}
        <div className="status-badge">
          {operation.status === 'success' && <CheckCircle className="w-4 h-4" />}
          {operation.status === 'error' && <XCircle className="w-4 h-4" />}
          {operation.status === 'running' && (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            >
              <Zap className="w-4 h-4" />
            </motion.div>
          )}
          {operation.status === 'pending' && <AlertCircle className="w-4 h-4" />}
        </div>
      </motion.div>

      {/* Render children if expanded */}
      <AnimatePresence>
        {isExpanded && hasChildren && (
          <motion.div
            className="operation-children"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            {children.map((child, childIndex) => (
              <OperationNode
                key={child.id}
                operation={child}
                allOperations={allOperations}
                level={level + 1}
                index={childIndex}
                isSelected={isSelected}
                isCurrent={isCurrent}
                onClick={onClick}
                expandedGroups={expandedGroups}
                onToggleGroup={onToggleGroup}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

// Operation Detail Panel
const OperationDetailPanel: React.FC<{
  operation: TimelineOperation;
  onClose: () => void;
}> = ({ operation, onClose }) => {
  return (
    <motion.div
      className="operation-detail-panel glass-panel"
      initial={{ opacity: 0, x: 300 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 300 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      <div className="detail-header">
        <div className="detail-icon" style={{ '--operation-color': operationColors[operation.type] } as React.CSSProperties}>
          {operationIcons[operation.type]}
        </div>
        <div className="detail-title-section">
          <h4 className="detail-title">{operation.name}</h4>
          <span className={`detail-status status-${operation.status}`}>
            {operation.status}
          </span>
        </div>
        <button className="close-btn" onClick={onClose} aria-label="Close">
          <XCircle className="w-5 h-5" />
        </button>
      </div>

      <div className="detail-content">
        {operation.description && (
          <div className="detail-section">
            <h5 className="section-label">Description</h5>
            <p className="section-text">{operation.description}</p>
          </div>
        )}

        {(operation.startTime || operation.endTime) && (
          <div className="detail-section">
            <h5 className="section-label">Timing</h5>
            <div className="timing-info">
              {operation.startTime && (
                <div className="timing-row">
                  <span className="timing-label">Started:</span>
                  <span className="timing-value">{operation.startTime.toLocaleTimeString()}</span>
                </div>
              )}
              {operation.endTime && (
                <div className="timing-row">
                  <span className="timing-label">Completed:</span>
                  <span className="timing-value">{operation.endTime.toLocaleTimeString()}</span>
                </div>
              )}
              {operation.duration && (
                <div className="timing-row">
                  <span className="timing-label">Duration:</span>
                  <span className="timing-value">{Math.round(operation.duration)}ms</span>
                </div>
              )}
            </div>
          </div>
        )}

        {operation.metadata && Object.keys(operation.metadata).length > 0 && (
          <div className="detail-section">
            <h5 className="section-label">Metadata</h5>
            <div className="metadata-grid">
              {Object.entries(operation.metadata).map(([key, value]) => (
                <div key={key} className="metadata-row">
                  <span className="metadata-key">{key}:</span>
                  <span className="metadata-value">
                    {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {operation.error && (
          <div className="detail-section error-section">
            <h5 className="section-label">Error</h5>
            <pre className="error-text">{operation.error}</pre>
          </div>
        )}
      </div>
    </motion.div>
  );
};
