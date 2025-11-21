/**
 * Model & Search Transparency Panel
 * Shows metadata about model selection, fallbacks, and search services
 */

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain,
  GitBranch,
  Search,
  Database,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  Zap,
  Globe,
  Link2,
  ChevronDown,
  ChevronUp,
  Info,
  Activity
} from 'lucide-react';
import {
  neuralPulseAnimation,
  glassRevealAnimation,
  modelBadgeAnimation,
  quotaMeterAnimation
} from '@/shared/animations/crystalline-animations';
import './transparency.css';

const clampPercentage = (value?: number) => {
  const numericValue = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  return Math.min(100, Math.max(0, Math.round(numericValue)));
};

const parseUsageString = (usageString?: string) => {
  if (!usageString) {
    return { used: 0, limitLabel: '—', percentage: 0 };
  }
  const [usedRaw = '0', limitRaw = '0'] = usageString.split('/');
  const used = Number(usedRaw);
  const limit = Number(limitRaw);
  const safeUsed = Number.isFinite(used) && used >= 0 ? used : 0;
  const safeLimit = Number.isFinite(limit) && limit > 0 ? limit : 0;
  const limitLabel = safeLimit > 0 ? safeLimit : '∞';
  const percentage = safeLimit > 0 ? clampPercentage((safeUsed / safeLimit) * 100) : 0;
  return { used: safeUsed, limitLabel, percentage };
};

const formatServiceName = (service: string) => service.replace(/_/g, ' ');

export interface ModelMetadata {
  taskType: string;
  selectedModel: string;
  originalModel?: string;
  fallbackOccurred: boolean;
  fallbackChain?: string[];
  fallbackReason?: string;
  modelHealth?: {
    available: boolean;
    rpmUsage: string;
    rpdUsage: string;
    circuitState: 'open' | 'closed' | 'half_open';
  };
  searchService?: 'gemini_grounding' | 'tavily' | 'firecrawl' | 'fallback_chain';
  searchMetadata?: {
    resultsCount: number;
    maxRequested: number;
    queryLength: number;
    servicesUsed?: string[];
    successRate?: number;
  };
  memoryOps?: {
    retrievalAttempted: boolean;
    factsRetrieved: number;
    relevanceScores?: number[];
    writeAttempted: boolean;
    factsWritten: number;
  };
  quotaStatus?: {
    geminiPro: number;
    geminiFlash: number;
    grounding: number;
    embeddings: number;
  };
  traceId?: string;
  timestamp?: string;
}

export const ModelMetadataPanel: React.FC<{
  metadata: ModelMetadata;
  isCollapsed?: boolean;
  onToggle?: () => void;
  className?: string;
}> = ({ metadata, isCollapsed = true, onToggle, className = '' }) => {
  const [isExpanded, setIsExpanded] = useState(!isCollapsed);

  // Sync internal state with prop changes
  useEffect(() => {
    setIsExpanded(!isCollapsed);
  }, [isCollapsed]);

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
    onToggle?.();
  };

  const getModelIcon = (model: string) => {
    if (model.includes('pro')) return '🚀';
    if (model.includes('flash-lite')) return '⚡';
    if (model.includes('flash')) return '✨';
    return '🤖';
  };

  return (
    <motion.div
      className={`model-metadata-panel glass-panel ${className}`}
      variants={glassRevealAnimation}
      initial="hidden"
      animate="visible"
      layout
    >
      {/* Floating Orb Trigger */}
      <motion.button
        className="metadata-orb"
        onClick={handleToggle}
        variants={neuralPulseAnimation}
        animate="pulse"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
      >
        <Brain className="orb-icon" />
        <span className="orb-label">Metadata</span>
        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </motion.button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="metadata-content"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* Model Selection Section */}
            <div className="metadata-section model-section">
              <h4 className="section-title">
                <Brain className="w-4 h-4" />
                Model Selection
              </h4>

              <div className="model-info">
                <motion.div
                  className="selected-model"
                  variants={modelBadgeAnimation}
                  animate={metadata.fallbackOccurred ? 'fallback' : 'selected'}
                >
                  <span className="model-icon">{getModelIcon(metadata.selectedModel)}</span>
                  <span className="model-name">{metadata.selectedModel}</span>
                  {metadata.fallbackOccurred && (
                    <span className="fallback-badge">Fallback</span>
                  )}
                </motion.div>

                {metadata.fallbackChain && metadata.fallbackChain.length > 1 && (
                  <FallbackChain
                    chain={metadata.fallbackChain}
                    reason={metadata.fallbackReason}
                  />
                )}

                {metadata.modelHealth && (
                  <ModelHealth health={metadata.modelHealth} />
                )}
              </div>
            </div>

            {/* Search Service Section */}
            {metadata.searchService && (
              <div className="metadata-section search-section">
                <h4 className="section-title">
                  <Search className="w-4 h-4" />
                  Search Service
                </h4>

                <SearchServiceInfo
                  service={metadata.searchService}
                  metadata={metadata.searchMetadata}
                />
              </div>
            )}

            {/* Memory Operations Section */}
            {metadata.memoryOps && (
              <div className="metadata-section memory-section">
                <h4 className="section-title">
                  <Database className="w-4 h-4" />
                  Memory Operations
                </h4>

                <MemoryOperations ops={metadata.memoryOps} />
              </div>
            )}

            {/* Quota Status Section */}
            {metadata.quotaStatus && (
              <div className="metadata-section quota-section">
                <h4 className="section-title">
                  <Activity className="w-4 h-4" />
                  Quota Status
                </h4>

                <QuotaMeters quotas={metadata.quotaStatus} />
              </div>
            )}

            {/* Trace Info */}
            {metadata.traceId && (
              <div className="trace-info">
                <span className="trace-label">Trace ID:</span>
                <code className="trace-id">{metadata.traceId}</code>
                <a
                  href={`https://smith.langchain.com/trace/${metadata.traceId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="trace-link"
                >
                  View in LangSmith →
                </a>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// Fallback Chain Visualization
const FallbackChain: React.FC<{
  chain: string[];
  reason?: string;
}> = ({ chain, reason }) => {
  return (
    <div className="fallback-chain">
      <div className="chain-header">
        <GitBranch className="w-3 h-3" />
        <span className="chain-label">Fallback Chain</span>
        {reason && <span className="chain-reason">({reason})</span>}
      </div>
      <div className="chain-flow">
        {chain.map((model, index) => (
          <React.Fragment key={index}>
            <motion.div
              className={`chain-node ${index === chain.length - 1 ? 'active' : 'passed'}`}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: index * 0.1 }}
            >
              <span className="node-icon">{getModelIcon(model)}</span>
              <span className="node-name">{model}</span>
            </motion.div>
            {index < chain.length - 1 && (
              <motion.div
                className="chain-arrow"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 + 0.05 }}
              >
                →
              </motion.div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );

  function getModelIcon(model: string): string {
    if (model.includes('pro')) return '🚀';
    if (model.includes('flash-lite')) return '⚡';
    if (model.includes('flash')) return '✨';
    return '🤖';
  }
};

// Model Health Display
const ModelHealth: React.FC<{
  health: ModelMetadata['modelHealth'];
}> = ({ health }) => {
  if (!health) return null;

  const rpmUsage = parseUsageString(health.rpmUsage);
  const rpdUsage = parseUsageString(health.rpdUsage);

  return (
    <div className="model-health">
      <div className="health-status">
        {health.available ? (
          <CheckCircle className="w-4 h-4 text-green-500" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-yellow-500" />
        )}
        <span className="health-label">
          Circuit: {health.circuitState}
        </span>
      </div>

      <div className="usage-meters">
        <UsageMeter
          label="RPM"
          used={rpmUsage.used}
          limit={rpmUsage.limitLabel}
          percentage={rpmUsage.percentage}
        />
        <UsageMeter
          label="RPD"
          used={rpdUsage.used}
          limit={rpdUsage.limitLabel}
          percentage={rpdUsage.percentage}
        />
      </div>
    </div>
  );

  function parseUsage(usageString: string) {
    const [used, limit] = usageString.split('/').map(s => parseInt(s));
    return { used, limit, percentage: Math.round((used / limit) * 100) };
  }
};

// Usage Meter Component
const UsageMeter: React.FC<{
  label: string;
  used: number;
  limit: number | string;
  percentage: number;
}> = ({ label, used, limit, percentage }) => {
  const safePercentage = clampPercentage(percentage);
  const status = safePercentage < 50 ? 'healthy' : safePercentage < 80 ? 'warning' : 'critical';

  return (
    <div className="usage-meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-value">{used}/{limit}</span>
      </div>
      <div className="meter-bar-bg">
        <motion.div
          className={`meter-bar meter-${status}`}
          variants={quotaMeterAnimation}
          animate={status}
          custom={safePercentage}
          style={{ width: `${safePercentage}%` }}
        >
          <span className="meter-percentage">{safePercentage}%</span>
        </motion.div>
      </div>
    </div>
  );
};

// Search Service Info
const SearchServiceInfo: React.FC<{
  service: string;
  metadata?: ModelMetadata['searchMetadata'];
}> = ({ service, metadata }) => {
  const getServiceIcon = () => {
    switch (service) {
      case 'gemini_grounding':
        return <Zap className="w-4 h-4" />;
      case 'tavily':
        return <Search className="w-4 h-4" />;
      case 'firecrawl':
        return <Link2 className="w-4 h-4" />;
      case 'fallback_chain':
        return <GitBranch className="w-4 h-4" />;
      default:
        return <Globe className="w-4 h-4" />;
    }
  };

  return (
    <div className="search-service-info">
      <div className="service-header">
        {getServiceIcon()}
        <span className="service-name">{formatServiceName(service)}</span>
      </div>

      {metadata && (
        <div className="service-stats">
          <div className="stat-item">
            <span className="stat-label">Results:</span>
            <span className="stat-value">{metadata.resultsCount}/{metadata.maxRequested}</span>
          </div>
          {metadata.servicesUsed && (
            <div className="stat-item">
              <span className="stat-label">Chain:</span>
              <span className="stat-value">{metadata.servicesUsed.join(' → ')}</span>
            </div>
          )}
          {metadata.successRate !== undefined && (
            <div className="stat-item">
              <span className="stat-label">Success:</span>
              <span className="stat-value">{metadata.successRate}%</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Memory Operations Display
const MemoryOperations: React.FC<{
  ops: ModelMetadata['memoryOps'];
}> = ({ ops }) => {
  if (!ops) return null;

  return (
    <div className="memory-operations">
      {ops.retrievalAttempted && (
        <div className="memory-stat">
          <TrendingUp className="w-4 h-4 text-cyan-400" />
          <span className="stat-text">
            Retrieved {ops.factsRetrieved} facts
            {(() => {
              const scores = (ops.relevanceScores || []).filter(
                (score): score is number => typeof score === 'number' && Number.isFinite(score)
              );
              if (!scores.length) {
                return null;
              }
              const average = clampPercentage(
                scores.reduce((sum, score) => sum + score, 0) / scores.length
              );
              return (
                <span className="relevance-avg">
                  (avg: {average}%)
                </span>
              );
            })()}
          </span>
        </div>
      )}

      {ops.writeAttempted && (
        <div className="memory-stat">
          <Database className="w-4 h-4 text-amber-400" />
          <span className="stat-text">
            Wrote {ops.factsWritten} facts to memory
          </span>
        </div>
      )}
    </div>
  );
};

// Quota Meters Display
const QuotaMeters: React.FC<{
  quotas: ModelMetadata['quotaStatus'];
}> = ({ quotas }) => {
  if (!quotas) return null;

  const normalize = (value?: number) =>
    clampPercentage(typeof value === 'number' ? value : 0);

  const quotaItems = [
    { label: 'Gemini Pro', percentage: normalize(quotas.geminiPro), icon: '🚀' },
    { label: 'Gemini Flash', percentage: normalize(quotas.geminiFlash), icon: '✨' },
    { label: 'Grounding', percentage: normalize(quotas.grounding), icon: '🔍' },
    { label: 'Embeddings', percentage: normalize(quotas.embeddings), icon: '🧬' }
  ];

  return (
    <div className="quota-meters">
      {quotaItems.map((item, index) => (
        <motion.div
          key={item.label}
          className="quota-item"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: index * 0.05 }}
        >
          <div className="quota-header">
            <span className="quota-icon">{item.icon}</span>
            <span className="quota-label">{item.label}</span>
          </div>
          <QuotaBar percentage={item.percentage} />
        </motion.div>
      ))}
    </div>
  );
};

// Individual Quota Bar
const QuotaBar: React.FC<{ percentage: number }> = ({ percentage }) => {
  const safePercentage = clampPercentage(percentage);
  const status = safePercentage < 50 ? 'healthy' : safePercentage < 80 ? 'warning' : 'critical';

  return (
    <div className="quota-bar-container">
      <div className="quota-bar-bg">
        <motion.div
          className={`quota-bar quota-${status}`}
          initial={{ width: 0 }}
          animate={{ width: `${safePercentage}%` }}
          transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
        />
      </div>
      <span className={`quota-percentage quota-${status}`}>{safePercentage}%</span>
    </div>
  );
};
