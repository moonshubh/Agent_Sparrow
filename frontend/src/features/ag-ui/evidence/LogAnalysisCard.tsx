/**
 * Log Analysis Card Component
 * Specialized evidence card for log analysis results with structured breakdown
 */

import React, { useState } from 'react';
import { FileText, AlertTriangle, CheckCircle, XCircle, Info, ChevronRight } from 'lucide-react';
import { ToolEvidenceCard, ToolEvidenceProps } from './ToolEvidenceCard';
import { motion, AnimatePresence } from 'framer-motion';

export type LogSeverity = 'error' | 'warning' | 'info' | 'success';

export interface LogIssue {
  severity: LogSeverity;
  message: string;
  line?: number;
  timestamp?: string;
  context?: string;
  solution?: string;
}

export interface LogAnalysisCardProps extends Omit<ToolEvidenceProps, 'type'> {
  summary: string;
  issues: LogIssue[];
  recommendations?: string[];
  logFile?: string;
  linesAnalyzed?: number;
  timeRange?: { start: string; end: string };
  patterns?: { name: string; count: number }[];
}

const severityIcons = {
  error: <XCircle className="w-4 h-4" />,
  warning: <AlertTriangle className="w-4 h-4" />,
  info: <Info className="w-4 h-4" />,
  success: <CheckCircle className="w-4 h-4" />
};

const severityColors = {
  error: 'error',
  warning: 'warning',
  info: 'info',
  success: 'success'
};

export const LogAnalysisCard: React.FC<LogAnalysisCardProps> = ({
  summary,
  issues,
  recommendations = [],
  logFile,
  linesAnalyzed,
  timeRange,
  patterns = [],
  ...props
}) => {
  const [expandedIssue, setExpandedIssue] = useState<number | null>(null);

  // Group issues by severity
  const groupedIssues = issues.reduce((acc, issue) => {
    if (!acc[issue.severity]) {
      acc[issue.severity] = [];
    }
    acc[issue.severity].push(issue);
    return acc;
  }, {} as Record<LogSeverity, LogIssue[]>);

  // Create full content with structured breakdown
  const fullContent = `
SUMMARY:
${summary}

ISSUES FOUND (${issues.length}):
${issues.map((issue, i) =>
  `[${issue.severity.toUpperCase()}] ${issue.message}${issue.line ? ` (Line ${issue.line})` : ''}${issue.solution ? `\n  Solution: ${issue.solution}` : ''}`
).join('\n')}

${recommendations.length > 0 ? `
RECOMMENDATIONS:
${recommendations.map((rec, i) => `${i + 1}. ${rec}`).join('\n')}
` : ''}

${patterns.length > 0 ? `
PATTERNS DETECTED:
${patterns.map(p => `- ${p.name}: ${p.count} occurrences`).join('\n')}
` : ''}
  `.trim();

  // Enhanced metadata
  const enhancedMetadata = {
    ...props.metadata,
    ...(logFile && { 'Log File': logFile }),
    ...(linesAnalyzed && { 'Lines Analyzed': linesAnalyzed }),
    ...(timeRange && {
      'Time Range': `${timeRange.start} - ${timeRange.end}`
    }),
    'Total Issues': issues.length,
    'Errors': groupedIssues.error?.length || 0,
    'Warnings': groupedIssues.warning?.length || 0
  };

  return (
    <div className="log-analysis-container">
      <ToolEvidenceCard
        {...props}
        type="log_analysis"
        title={props.title || 'Log Analysis Results'}
        source={logFile || 'Log Analysis'}
        snippet={summary}
        fullContent={fullContent}
        metadata={enhancedMetadata}
        confidence={issues.length > 0 ? 90 : 100}
        icon={<FileText className="w-5 h-5" />}
        className="log-analysis-card"
      />

      {/* Issues breakdown */}
      {issues.length > 0 && (
        <motion.div
          className="issues-breakdown glass-panel"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          <h4 className="breakdown-title">Issues Detected</h4>

          {Object.entries(groupedIssues).map(([severity, severityIssues]) => (
            <div key={severity} className={`severity-group severity-${severity}`}>
              <div className="severity-header">
                {severityIcons[severity as LogSeverity]}
                <span className="severity-label">{severity.toUpperCase()}</span>
                <span className="severity-count">{severityIssues.length}</span>
              </div>

              <div className="severity-issues">
                {severityIssues.slice(0, 3).map((issue, index) => (
                  <IssueItem
                    key={index}
                    issue={issue}
                    index={index}
                    isExpanded={expandedIssue === index}
                    onToggle={() =>
                      setExpandedIssue(expandedIssue === index ? null : index)
                    }
                  />
                ))}
                {severityIssues.length > 3 && (
                  <span className="more-issues">
                    +{severityIssues.length - 3} more {severity} issues
                  </span>
                )}
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <motion.div
          className="recommendations-section glass-panel"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
        >
          <h4 className="recommendations-title">Recommended Actions</h4>
          <ol className="recommendations-list">
            {recommendations.map((rec, index) => (
              <motion.li
                key={index}
                className="recommendation-item"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: index * 0.05 }}
              >
                {rec}
              </motion.li>
            ))}
          </ol>
        </motion.div>
      )}

      {/* Pattern Analysis */}
      {patterns.length > 0 && (
        <motion.div
          className="patterns-section glass-panel"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
        >
          <h4 className="patterns-title">Pattern Analysis</h4>
          <div className="patterns-grid">
            {patterns.map((pattern, index) => (
              <div key={index} className="pattern-item">
                <span className="pattern-name">{pattern.name}</span>
                <span className="pattern-count">{pattern.count}</span>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
};

// Individual issue item component
const IssueItem: React.FC<{
  issue: LogIssue;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}> = ({ issue, index, isExpanded, onToggle }) => {
  return (
    <motion.div
      className="issue-item"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2, delay: index * 0.05 }}
    >
      <button
        className="issue-header"
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? 'Collapse' : 'Expand'} issue: ${issue.message}`}
      >
        <ChevronRight
          className={`issue-chevron ${isExpanded ? 'expanded' : ''}`}
        />
        <span className="issue-message">{issue.message}</span>
        {issue.line && <span className="issue-line">Line {issue.line}</span>}
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="issue-details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {issue.timestamp && (
              <div className="detail-item">
                <span className="detail-label">Timestamp:</span>
                <span className="detail-value">{issue.timestamp}</span>
              </div>
            )}
            {issue.context && (
              <div className="detail-item">
                <span className="detail-label">Context:</span>
                <span className="detail-value">{issue.context}</span>
              </div>
            )}
            {issue.solution && (
              <div className="detail-item solution">
                <span className="detail-label">Solution:</span>
                <span className="detail-value">{issue.solution}</span>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// Enhanced styles for log analysis cards
const logAnalysisStyles = `
  .log-analysis-container {
    position: relative;
  }

  .issues-breakdown,
  .recommendations-section,
  .patterns-section {
    margin-top: var(--space-md);
    padding: var(--space-md);
    background: hsla(228, 62%, 10%, 0.4);
    border: 1px solid hsla(45, 100%, 50%, 0.2);
    border-radius: var(--radius-md);
  }

  .breakdown-title,
  .recommendations-title,
  .patterns-title {
    font-size: var(--font-size-md);
    font-weight: var(--font-weight-semibold);
    color: var(--accent-gold-400);
    margin: 0 0 var(--space-md) 0;
  }

  .severity-group {
    margin-bottom: var(--space-md);
  }

  .severity-group:last-child {
    margin-bottom: 0;
  }

  .severity-header {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    margin-bottom: var(--space-sm);
  }

  .severity-label {
    font-weight: var(--font-weight-semibold);
    font-size: var(--font-size-sm);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .severity-count {
    margin-left: auto;
    padding: 2px 6px;
    background: hsla(0, 0%, 100%, 0.1);
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-family: var(--font-family-mono);
  }

  .severity-error .severity-header {
    color: var(--status-error);
  }

  .severity-warning .severity-header {
    color: var(--status-warning);
  }

  .severity-info .severity-header {
    color: var(--status-info);
  }

  .severity-success .severity-header {
    color: var(--status-success);
  }

  .severity-issues {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .issue-item {
    background: hsla(0, 0%, 100%, 0.02);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }

  .issue-header {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    padding: var(--space-sm);
    width: 100%;
    background: transparent;
    border: none;
    cursor: pointer;
    text-align: left;
    transition: background var(--duration-fast) var(--ease-smooth);
  }

  .issue-header:hover {
    background: hsla(45, 100%, 50%, 0.05);
  }

  .issue-chevron {
    width: 16px;
    height: 16px;
    transition: transform var(--duration-fast) var(--ease-smooth);
  }

  .issue-chevron.expanded {
    transform: rotate(90deg);
  }

  .issue-message {
    flex: 1;
    color: var(--neutral-200);
    font-size: var(--font-size-sm);
  }

  .issue-line {
    color: var(--neutral-500);
    font-size: var(--font-size-xs);
    font-family: var(--font-family-mono);
  }

  .issue-details {
    padding: 0 var(--space-sm) var(--space-sm) calc(var(--space-sm) + 24px);
    overflow: hidden;
  }

  .detail-item {
    display: flex;
    gap: var(--space-xs);
    margin-top: var(--space-xs);
    font-size: var(--font-size-sm);
  }

  .detail-label {
    color: var(--neutral-500);
    min-width: 80px;
  }

  .detail-value {
    color: var(--neutral-300);
    font-family: var(--font-family-mono);
  }

  .detail-item.solution .detail-value {
    color: var(--status-success);
  }

  .more-issues {
    padding: var(--space-xs) var(--space-sm);
    color: var(--neutral-500);
    font-size: var(--font-size-xs);
    font-style: italic;
  }

  .recommendations-list {
    list-style: none;
    padding: 0;
    margin: 0;
    counter-reset: recommendation;
  }

  .recommendation-item {
    counter-increment: recommendation;
    position: relative;
    padding-left: var(--space-lg);
    margin-bottom: var(--space-sm);
    color: var(--neutral-200);
    font-size: var(--font-size-sm);
    line-height: var(--line-height-relaxed);
  }

  .recommendation-item::before {
    content: counter(recommendation);
    position: absolute;
    left: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    background: var(--accent-amber-500);
    color: var(--crystal-primary-900);
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-bold);
  }

  .patterns-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-sm);
  }

  .pattern-item {
    display: flex;
    justify-content: space-between;
    padding: var(--space-sm);
    background: hsla(0, 0%, 100%, 0.02);
    border: 1px solid hsla(190, 100%, 50%, 0.1);
    border-radius: var(--radius-sm);
    transition: all var(--duration-fast) var(--ease-smooth);
  }

  .pattern-item:hover {
    border-color: hsla(45, 100%, 50%, 0.3);
    background: hsla(45, 100%, 50%, 0.05);
  }

  .pattern-name {
    color: var(--crystal-cyan-300);
    font-size: var(--font-size-sm);
  }

  .pattern-count {
    color: var(--accent-amber-400);
    font-family: var(--font-family-mono);
    font-weight: var(--font-weight-semibold);
  }
`;

// Inject styles (with deduplication check)
if (typeof document !== 'undefined' && !document.getElementById('log-analysis-styles')) {
  const style = document.createElement('style');
  style.id = 'log-analysis-styles';
  style.textContent = logAnalysisStyles;
  document.head.appendChild(style);
}