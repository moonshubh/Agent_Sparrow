/**
 * Per-Subagent Model Configuration
 * Model recommendations and override settings per agent type
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Users,
  Search,
  FileWarning,
  Database,
  Zap,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  DollarSign,
  Clock,
  Info,
  Settings
} from 'lucide-react';
import { crystalCardAnimation } from '@/shared/animations/crystalline-animations';
import './subagent-model-config.css';

export type AgentType = 'primary' | 'research' | 'log_diagnoser' | 'memory' | 'custom';

export interface ModelOption {
  id: string;
  name: string;
  provider: 'gemini' | 'openai';
  tier: 'pro' | 'flash' | 'lite';
  costPerMillion: number;
  averageLatency: number;
  contextWindow: number;
}

export interface AgentConfig {
  type: AgentType;
  name: string;
  description: string;
  icon: React.ReactNode;
  recommendedModel: string;
  currentModel: string;
  availableModels: ModelOption[];
  performancePrediction?: {
    quality: 'excellent' | 'good' | 'fair' | 'poor';
    speed: 'fast' | 'medium' | 'slow';
    cost: 'low' | 'medium' | 'high';
  };
  overrideWarning?: string;
}

export interface SubagentModelConfigProps {
  agents: AgentConfig[];
  onModelChange: (agentType: AgentType, modelId: string) => void;
  onResetToRecommended: (agentType: AgentType) => void;
  className?: string;
}

const agentIcons: Record<AgentType, React.ReactNode> = {
  primary: <Users className="w-5 h-5" />,
  research: <Search className="w-5 h-5" />,
  log_diagnoser: <FileWarning className="w-5 h-5" />,
  memory: <Database className="w-5 h-5" />,
  custom: <Zap className="w-5 h-5" />
};

export const SubagentModelConfig: React.FC<SubagentModelConfigProps> = ({
  agents,
  onModelChange,
  onResetToRecommended,
  className = ''
}) => {
  const [selectedAgent, setSelectedAgent] = useState<AgentType | null>(null);
  const [showOverrideWarning, setShowOverrideWarning] = useState<AgentType | null>(null);
  const [pendingOverride, setPendingOverride] = useState<{ agentType: AgentType; modelId: string } | null>(null);

  const handleModelChange = (agentType: AgentType, modelId: string, isRecommended: boolean) => {
    if (!isRecommended) {
      setPendingOverride({ agentType, modelId });
      setShowOverrideWarning(agentType);
      return;
    }
    setPendingOverride(null);
    setShowOverrideWarning(null);
    onModelChange(agentType, modelId);
  };

  const confirmOverride = () => {
    if (pendingOverride) {
      onModelChange(pendingOverride.agentType, pendingOverride.modelId);
    }
    setPendingOverride(null);
    setShowOverrideWarning(null);
  };

  const cancelOverride = () => {
    setPendingOverride(null);
    setShowOverrideWarning(null);
  };

  return (
    <motion.div
      className={`subagent-model-config glass-panel ${className}`}
      variants={crystalCardAnimation}
      initial="hidden"
      animate="visible"
    >
      {/* Header */}
      <div className="config-header">
        <div className="header-left">
          <div className="config-icon">
            <Settings className="w-5 h-5" />
          </div>
          <div className="header-text">
            <h3 className="config-title">Model Configuration</h3>
            <p className="config-subtitle">Per-agent model selection and optimization</p>
          </div>
        </div>
      </div>

      {/* Agents Grid */}
      <div className="agents-grid">
        {agents.map((agent) => (
          <AgentConfigCard
            key={agent.type}
            agent={agent}
            isSelected={selectedAgent === agent.type}
            onSelect={() => setSelectedAgent(agent.type)}
            onModelChange={handleModelChange}
            onReset={() => onResetToRecommended(agent.type)}
          />
        ))}
      </div>

      {/* Override Warning Modal */}
      <AnimatePresence>
        {showOverrideWarning && pendingOverride && pendingOverride.agentType === showOverrideWarning && (() => {
          const agent = agents.find(a => a.type === showOverrideWarning);
          if (!agent) {
            return null;
          }
          const pendingModel = agent.availableModels.find(model => model.id === pendingOverride.modelId);
          return (
            <OverrideWarningModal
              agent={agent}
              pendingModelId={pendingOverride.modelId}
              pendingModel={pendingModel}
              onConfirm={confirmOverride}
              onCancel={cancelOverride}
            />
          );
        })()}
      </AnimatePresence>
    </motion.div>
  );
};

// Agent Config Card Component
const AgentConfigCard: React.FC<{
  agent: AgentConfig;
  isSelected: boolean;
  onSelect: () => void;
  onModelChange: (agentType: AgentType, modelId: string, isRecommended: boolean) => void;
  onReset: () => void;
}> = ({ agent, isSelected, onSelect, onModelChange, onReset }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isOverridden = agent.currentModel !== agent.recommendedModel;
  const currentModelObj = agent.availableModels.find(m => m.id === agent.currentModel);

  return (
    <motion.div
      className={`agent-config-card ${isSelected ? 'selected' : ''} ${isOverridden ? 'overridden' : ''}`}
      onClick={() => {
        onSelect();
        setIsExpanded(!isExpanded);
      }}
      whileHover={{ scale: 1.02 }}
      layout
    >
      {/* Card Header */}
      <div className="card-header">
        <div className="agent-icon">{agentIcons[agent.type]}</div>
        <div className="agent-info">
          <h4 className="agent-name">{agent.name}</h4>
          <p className="agent-description">{agent.description}</p>
        </div>
        {isOverridden && (
          <div className="override-badge">
            <AlertTriangle className="w-3 h-3" />
            Override
          </div>
        )}
      </div>

      {/* Current Model Display */}
      <div className="current-model-display">
        <span className="model-label">Current Model:</span>
        <span className="model-name">{currentModelObj?.name || agent.currentModel}</span>
        {!isOverridden && (
          <CheckCircle className="w-4 h-4 text-green-500" />
        )}
      </div>

      {/* Performance Prediction */}
      {agent.performancePrediction && (
        <div className="performance-preview">
          <PerformanceBadge
            label="Quality"
            value={agent.performancePrediction.quality}
            icon={<TrendingUp className="w-3 h-3" />}
          />
          <PerformanceBadge
            label="Speed"
            value={agent.performancePrediction.speed}
            icon={<Clock className="w-3 h-3" />}
          />
          <PerformanceBadge
            label="Cost"
            value={agent.performancePrediction.cost}
            icon={<DollarSign className="w-3 h-3" />}
          />
        </div>
      )}

      {/* Expanded Model Selection */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="model-selection"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <div className="selection-header">
              <h5 className="selection-title">Available Models</h5>
              {isOverridden && (
                <button
                  className="reset-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onReset();
                  }}
                >
                  <CheckCircle className="w-3 h-3" />
                  Reset to Recommended
                </button>
              )}
            </div>

            <div className="models-list">
              {agent.availableModels.map((model) => {
                const isRecommended = model.id === agent.recommendedModel;
                const isCurrent = model.id === agent.currentModel;

                return (
                  <motion.div
                    key={model.id}
                    className={`model-option ${isCurrent ? 'current' : ''} ${isRecommended ? 'recommended' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onModelChange(agent.type, model.id, isRecommended);
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="model-header">
                      <div className="model-name-section">
                        <span className="model-name">{model.name}</span>
                        {isRecommended && (
                          <span className="recommended-tag">Recommended</span>
                        )}
                      </div>
                      {isCurrent && <CheckCircle className="w-4 h-4 text-green-500" />}
                    </div>

                    <div className="model-stats">
                      <div className="stat">
                        <DollarSign className="w-3 h-3" />
                        <span>${model.costPerMillion}/M tokens</span>
                      </div>
                      <div className="stat">
                        <Clock className="w-3 h-3" />
                        <span>{model.averageLatency}ms avg</span>
                      </div>
                      <div className="stat">
                        <Info className="w-3 h-3" />
                        <span>{(model.contextWindow / 1000).toFixed(0)}K context</span>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// Performance Badge Component
const PerformanceBadge: React.FC<{
  label: string;
  value: string;
  icon: React.ReactNode;
}> = ({ label, value, icon }) => {
  const getColor = () => {
    if (value === 'excellent' || value === 'fast' || value === 'low') return 'var(--status-success)';
    if (value === 'good' || value === 'medium') return 'var(--accent-amber-400)';
    if (value === 'fair' || value === 'slow' || value === 'high') return 'var(--status-warning)';
    return 'var(--status-error)';
  };

  return (
    <div className="performance-badge" style={{ '--badge-color': getColor() } as React.CSSProperties}>
      {icon}
      <span className="badge-label">{label}:</span>
      <span className="badge-value">{value}</span>
    </div>
  );
};

// Override Warning Modal
const OverrideWarningModal: React.FC<{
  agent: AgentConfig;
  pendingModelId: string;
  pendingModel?: ModelOption;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ agent, pendingModelId, pendingModel, onConfirm, onCancel }) => {
  const modelLabel = pendingModel?.name || pendingModelId;

  return (
    <>
      <motion.div
        className="modal-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onCancel}
      />
      <motion.div
        className="override-warning-modal glass-panel"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      >
        <div className="modal-header">
          <div className="warning-icon">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h3 className="modal-title">Override Recommended Model?</h3>
        </div>

        <div className="modal-content">
          <p className="warning-message">
            You are about to override the recommended model for <strong>{agent.name}</strong> with <strong>{modelLabel}</strong>.
          </p>

          {agent.overrideWarning && (
            <div className="warning-box">
              <AlertTriangle className="w-4 h-4" />
              <p>{agent.overrideWarning}</p>
            </div>
          )}

          <div className="consequences">
            <h5 className="consequences-title">Potential Consequences:</h5>
            <ul className="consequences-list">
              <li>Performance may differ from expected results</li>
              <li>Cost and latency characteristics will change</li>
              <li>Quality of responses may be impacted</li>
              <li>This override will persist across sessions</li>
            </ul>
          </div>
        </div>

        <div className="modal-actions">
          <motion.button
            className="cancel-btn"
            onClick={onCancel}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Cancel
          </motion.button>
          <motion.button
            className="confirm-btn"
            onClick={onConfirm}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <CheckCircle className="w-4 h-4" />
            Confirm Override
          </motion.button>
        </div>
      </motion.div>
    </>
  );
};
