/**
 * Enhanced Reasoning Panel with Timeline View
 * Shows agent's thought process with phases, tool selection, and confidence scores
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Search,
  Zap,
  CheckCircle,
  XCircle,
  TrendingUp,
  GitBranch,
  Clock,
  Target
} from 'lucide-react';
import {
  timelineNodeAnimation,
  timelineBranchAnimation,
  crystalCardAnimation
} from '@/shared/animations/crystalline-animations';
import './enhanced-reasoning.css';

export type ReasoningPhase = 'planning' | 'searching' | 'analyzing' | 'responding';

export interface ToolDecision {
  toolName: string;
  selected: boolean;
  confidence?: number;
  reason: string;
  alternatives?: string[];
}

export interface PhaseData {
  phase: ReasoningPhase;
  title: string;
  description: string;
  status: 'pending' | 'active' | 'complete';
  duration?: number; // in milliseconds
  toolDecisions?: ToolDecision[];
  thinkingSteps?: string[];
}

export interface EnhancedReasoningPanelProps {
  phases: PhaseData[];
  currentPhase?: ReasoningPhase;
  isExpanded?: boolean;
  onToggle?: () => void;
  className?: string;
}

const phaseIcons: Record<ReasoningPhase, React.ReactNode> = {
  planning: <Lightbulb className="w-4 h-4" />,
  searching: <Search className="w-4 h-4" />,
  analyzing: <Zap className="w-4 h-4" />,
  responding: <TrendingUp className="w-4 h-4" />
};

const phaseColors: Record<ReasoningPhase, string> = {
  planning: 'var(--crystal-cyan-400)',
  searching: 'var(--accent-amber-400)',
  analyzing: 'var(--accent-gold-400)',
  responding: 'var(--status-success)'
};

export const EnhancedReasoningPanel: React.FC<EnhancedReasoningPanelProps> = ({
  phases,
  currentPhase,
  isExpanded: initialExpanded = false,
  onToggle,
  className = ''
}) => {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [selectedPhase, setSelectedPhase] = useState<PhaseData | null>(null);

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
    onToggle?.();
  };

  const getPhaseStatus = (phase: PhaseData): 'future' | 'current' | 'past' => {
    if (!currentPhase) {
      return phase.status === 'complete' ? 'past' : phase.status === 'active' ? 'current' : 'future';
    }

    const phaseOrder: ReasoningPhase[] = ['planning', 'searching', 'analyzing', 'responding'];
    const currentIndex = phaseOrder.indexOf(currentPhase);
    const phaseIndex = phaseOrder.indexOf(phase.phase);

    if (phaseIndex < currentIndex) return 'past';
    if (phaseIndex === currentIndex) return 'current';
    return 'future';
  };

  return (
    <motion.div
      className={`enhanced-reasoning-panel glass-panel ${className}`}
      variants={crystalCardAnimation}
      initial="hidden"
      animate="visible"
      layout
    >
      {/* Panel Header */}
      <div className="reasoning-header" onClick={handleToggle}>
        <div className="header-left">
          <div className="thinking-icon">
            <motion.div
              animate={{
                rotate: [0, 180, 360],
                scale: [1, 1.1, 1]
              }}
              transition={{
                duration: 3,
                repeat: Infinity,
                ease: 'easeInOut'
              }}
            >
              <Lightbulb className="w-5 h-5" />
            </motion.div>
          </div>
          <div className="header-text">
            <h3 className="panel-title">Agent Reasoning</h3>
            <p className="panel-subtitle">
              {currentPhase ? `Current: ${currentPhase}` : `${phases.length} phases`}
            </p>
          </div>
        </div>
        <button className="toggle-btn" aria-label={isExpanded ? 'Collapse' : 'Expand'}>
          {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="reasoning-content"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
          >
            {/* Timeline View */}
            <div className="timeline-container">
              <svg className="timeline-connections">
                {phases.map((phase, index) => {
                  if (index === phases.length - 1) return null;

                  const startY = 60 + index * 120;
                  const endY = 60 + (index + 1) * 120;

                  return (
                    <motion.line
                      key={`line-${index}`}
                      x1="40"
                      y1={startY}
                      x2="40"
                      y2={endY}
                      className="timeline-line"
                      variants={timelineBranchAnimation}
                      initial="hidden"
                      animate="visible"
                      custom={index}
                    />
                  );
                })}
              </svg>

              {phases.map((phase, index) => (
                <PhaseNode
                  key={phase.phase}
                  phase={phase}
                  status={getPhaseStatus(phase)}
                  index={index}
                  onClick={() => setSelectedPhase(phase)}
                  isSelected={selectedPhase?.phase === phase.phase}
                />
              ))}
            </div>

            {/* Phase Detail View */}
            <AnimatePresence mode="wait">
              {selectedPhase && (
                <PhaseDetailView
                  phase={selectedPhase}
                  onClose={() => setSelectedPhase(null)}
                />
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// Phase Node Component
const PhaseNode: React.FC<{
  phase: PhaseData;
  status: 'future' | 'current' | 'past';
  index: number;
  onClick: () => void;
  isSelected: boolean;
}> = ({ phase, status, index, onClick, isSelected }) => {
  const icon = phaseIcons[phase.phase];
  const color = phaseColors[phase.phase];

  return (
    <motion.div
      className={`phase-node ${status} ${isSelected ? 'selected' : ''}`}
      variants={timelineNodeAnimation}
      initial="future"
      animate={status}
      custom={index}
      onClick={onClick}
      style={{
        '--phase-color': color
      } as React.CSSProperties}
    >
      <div className="node-indicator">
        <div className="node-icon">{icon}</div>
        {status === 'complete' && (
          <div className="completion-badge">
            <CheckCircle className="w-3 h-3" />
          </div>
        )}
      </div>

      <div className="node-content">
        <div className="node-header">
          <h4 className="node-title">{phase.title}</h4>
          {phase.duration && (
            <span className="node-duration">
              <Clock className="w-3 h-3" />
              {Math.round(phase.duration)}ms
            </span>
          )}
        </div>
        <p className="node-description">{phase.description}</p>

        {phase.toolDecisions && phase.toolDecisions.length > 0 && (
          <div className="tool-preview">
            <span className="tool-count">
              {phase.toolDecisions.filter(d => d.selected).length} tools selected
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// Phase Detail View
const PhaseDetailView: React.FC<{
  phase: PhaseData;
  onClose: () => void;
}> = ({ phase, onClose }) => {
  return (
    <motion.div
      className="phase-detail-view glass-panel"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.3 }}
    >
      <div className="detail-header">
        <div className="detail-icon" style={{ '--phase-color': phaseColors[phase.phase] } as React.CSSProperties}>
          {phaseIcons[phase.phase]}
        </div>
        <div className="detail-title-section">
          <h4 className="detail-title">{phase.title}</h4>
          <p className="detail-description">{phase.description}</p>
        </div>
      </div>

      {/* Thinking Steps */}
      {phase.thinkingSteps && phase.thinkingSteps.length > 0 && (
        <div className="thinking-steps">
          <h5 className="section-title">Thought Process</h5>
          <ul className="steps-list">
            {phase.thinkingSteps.map((step, index) => (
              <motion.li
                key={index}
                className="step-item"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                {step}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* Tool Decisions */}
      {phase.toolDecisions && phase.toolDecisions.length > 0 && (
        <div className="tool-decisions">
          <h5 className="section-title">Tool Selection</h5>
          <div className="decisions-grid">
            {phase.toolDecisions.map((decision, index) => (
              <ToolDecisionCard key={index} decision={decision} />
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

// Tool Decision Card
const ToolDecisionCard: React.FC<{
  decision: ToolDecision;
}> = ({ decision }) => {
  const [showAlternatives, setShowAlternatives] = useState(false);

  return (
    <div className={`tool-decision-card ${decision.selected ? 'selected' : 'rejected'}`}>
      <div className="decision-header">
        <div className="tool-name-section">
          {decision.selected ? (
            <CheckCircle className="w-4 h-4 text-green-500" />
          ) : (
            <XCircle className="w-4 h-4 text-gray-500" />
          )}
          <span className="tool-name">{decision.toolName}</span>
        </div>
        {decision.confidence !== undefined && decision.selected && (
          <ConfidenceBadge confidence={decision.confidence} />
        )}
      </div>

      <p className="decision-reason">{decision.reason}</p>

      {decision.alternatives && decision.alternatives.length > 0 && (
        <div className="alternatives-section">
          <button
            className="alternatives-toggle"
            onClick={() => setShowAlternatives(!showAlternatives)}
          >
            <GitBranch className="w-3 h-3" />
            {decision.alternatives.length} alternatives
            {showAlternatives ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          <AnimatePresence>
            {showAlternatives && (
              <motion.div
                className="alternatives-list"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
              >
                {decision.alternatives.map((alt, i) => (
                  <div key={i} className="alternative-item">
                    {alt}
                  </div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
};

// Confidence Badge Component
const ConfidenceBadge: React.FC<{ confidence: number }> = ({ confidence }) => {
  const getColor = () => {
    if (confidence >= 80) return 'var(--status-success)';
    if (confidence >= 50) return 'var(--accent-amber-400)';
    return 'var(--status-error)';
  };

  return (
    <div className="confidence-badge" style={{ '--confidence-color': getColor() } as React.CSSProperties}>
      <Target className="w-3 h-3" />
      <span>{confidence}%</span>
    </div>
  );
};