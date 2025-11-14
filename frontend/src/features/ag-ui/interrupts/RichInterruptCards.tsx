/**
 * Rich Interrupt Cards
 * Specialized cards for different types of human-in-the-loop interrupts
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  HelpCircle,
  Database,
  Clock,
  Zap,
  Info,
  FileWarning,
  AlertOctagon
} from 'lucide-react';
import { interruptAnimation } from '@/shared/animations/crystalline-animations';
import './rich-interrupt-cards.css';

export type InterruptType = 'confirmation' | 'disambiguation' | 'risk' | 'rate_limit';

export interface BaseInterruptProps {
  id: string;
  type: InterruptType;
  title: string;
  message: string;
  timestamp?: Date;
  onResolve: (resolution: InterruptResolution) => void;
  onCancel?: () => void;
}

export interface ConfirmationInterruptProps extends BaseInterruptProps {
  type: 'confirmation';
  consequences?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
}

export interface DisambiguationInterruptProps extends BaseInterruptProps {
  type: 'disambiguation';
  options: DisambiguationOption[];
  allowMultiple?: boolean;
}

export interface DisambiguationOption {
  id: string;
  label: string;
  description?: string;
  recommended?: boolean;
}

export interface RiskInterruptProps extends BaseInterruptProps {
  type: 'risk';
  riskLevel: 'high' | 'critical';
  operationType: 'db_write' | 'bulk_operation' | 'delete' | 'external_api';
  affectedItems?: string[];
  requireReason?: boolean;
}

export interface RateLimitInterruptProps extends BaseInterruptProps {
  type: 'rate_limit';
  serviceName: string;
  currentUsage: number;
  limit: number;
  actions: RateLimitAction[];
}

export interface RateLimitAction {
  id: string;
  label: string;
  description: string;
  icon?: React.ReactNode;
}

export type InterruptProps =
  | ConfirmationInterruptProps
  | DisambiguationInterruptProps
  | RiskInterruptProps
  | RateLimitInterruptProps;

export interface InterruptResolution {
  interruptId: string;
  action: string;
  data?: any;
}

// Main Interrupt Card Router
export const RichInterruptCard: React.FC<InterruptProps> = (props) => {
  switch (props.type) {
    case 'confirmation':
      return <ConfirmationCard {...props} />;
    case 'disambiguation':
      return <DisambiguationCard {...props} />;
    case 'risk':
      return <RiskCard {...props} />;
    case 'rate_limit':
      return <RateLimitCard {...props} />;
    default:
      return null;
  }
};

// Confirmation Card
const ConfirmationCard: React.FC<ConfirmationInterruptProps> = ({
  id,
  title,
  message,
  consequences = [],
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  timestamp,
  onResolve,
  onCancel
}) => {
  return (
    <motion.div
      className="interrupt-card confirmation-card glass-panel"
      variants={interruptAnimation}
      initial="hidden"
      animate="visible"
    >
      <div className="interrupt-header">
        <div className="header-icon confirmation-icon">
          <HelpCircle className="w-5 h-5" />
        </div>
        <div className="header-text">
          <h4 className="interrupt-title">{title}</h4>
          {timestamp && (
            <span className="interrupt-timestamp">
              <Clock className="w-3 h-3" />
              {timestamp.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      <div className="interrupt-content">
        <p className="interrupt-message">{message}</p>

        {consequences.length > 0 && (
          <div className="consequences-section">
            <h5 className="consequences-title">
              <Info className="w-4 h-4" />
              Consequences:
            </h5>
            <ul className="consequences-list">
              {consequences.map((consequence, index) => (
                <motion.li
                  key={index}
                  className="consequence-item"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                >
                  {consequence}
                </motion.li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="interrupt-actions">
        <motion.button
          className="interrupt-btn cancel-btn"
          onClick={() => {
            onCancel?.();
            onResolve({ interruptId: id, action: 'cancel' });
          }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <XCircle className="w-4 h-4" />
          {cancelLabel}
        </motion.button>
        <motion.button
          className="interrupt-btn confirm-btn"
          onClick={() => onResolve({ interruptId: id, action: 'confirm' })}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <CheckCircle className="w-4 h-4" />
          {confirmLabel}
        </motion.button>
      </div>
    </motion.div>
  );
};

// Disambiguation Card
const DisambiguationCard: React.FC<DisambiguationInterruptProps> = ({
  id,
  title,
  message,
  options,
  allowMultiple = false,
  timestamp,
  onResolve,
  onCancel
}) => {
  const [selectedOptions, setSelectedOptions] = useState<Set<string>>(new Set());

  const handleOptionToggle = (optionId: string) => {
    const newSelected = new Set(selectedOptions);
    if (newSelected.has(optionId)) {
      newSelected.delete(optionId);
    } else {
      if (!allowMultiple) {
        newSelected.clear();
      }
      newSelected.add(optionId);
    }
    setSelectedOptions(newSelected);
  };

  const handleSubmit = () => {
    onResolve({
      interruptId: id,
      action: 'select',
      data: { selected: Array.from(selectedOptions) }
    });
  };

  return (
    <motion.div
      className="interrupt-card disambiguation-card glass-panel"
      variants={interruptAnimation}
      initial="hidden"
      animate="visible"
    >
      <div className="interrupt-header">
        <div className="header-icon disambiguation-icon">
          <HelpCircle className="w-5 h-5" />
        </div>
        <div className="header-text">
          <h4 className="interrupt-title">{title}</h4>
          {timestamp && (
            <span className="interrupt-timestamp">
              <Clock className="w-3 h-3" />
              {timestamp.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      <div className="interrupt-content">
        <p className="interrupt-message">{message}</p>

        <div className="options-grid">
          {options.map((option) => (
            <motion.div
              key={option.id}
              className={`option-card ${selectedOptions.has(option.id) ? 'selected' : ''} ${option.recommended ? 'recommended' : ''}`}
              onClick={() => handleOptionToggle(option.id)}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <div className="option-indicator">
                {selectedOptions.has(option.id) ? (
                  <CheckCircle className="w-5 h-5" />
                ) : (
                  <div className="empty-indicator" />
                )}
              </div>
              <div className="option-content">
                <h5 className="option-label">
                  {option.label}
                  {option.recommended && <span className="recommended-badge">Recommended</span>}
                </h5>
                {option.description && (
                  <p className="option-description">{option.description}</p>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="interrupt-actions">
        {onCancel && (
          <motion.button
            className="interrupt-btn cancel-btn"
            onClick={() => {
              onCancel();
              onResolve({ interruptId: id, action: 'cancel' });
            }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Cancel
          </motion.button>
        )}
        <motion.button
          className="interrupt-btn confirm-btn"
          onClick={handleSubmit}
          disabled={selectedOptions.size === 0}
          whileHover={{ scale: selectedOptions.size > 0 ? 1.02 : 1 }}
          whileTap={{ scale: selectedOptions.size > 0 ? 0.98 : 1 }}
        >
          Submit Selection
        </motion.button>
      </div>
    </motion.div>
  );
};

// Risk Card
const RiskCard: React.FC<RiskInterruptProps> = ({
  id,
  title,
  message,
  riskLevel,
  operationType,
  affectedItems = [],
  requireReason = false,
  timestamp,
  onResolve,
  onCancel
}) => {
  const [reason, setReason] = useState('');

  const getOperationIcon = () => {
    switch (operationType) {
      case 'db_write':
        return <Database className="w-5 h-5" />;
      case 'bulk_operation':
        return <Zap className="w-5 h-5" />;
      case 'delete':
        return <AlertOctagon className="w-5 h-5" />;
      case 'external_api':
        return <FileWarning className="w-5 h-5" />;
    }
  };

  const canProceed = !requireReason || reason.trim().length > 0;

  return (
    <motion.div
      className={`interrupt-card risk-card ${riskLevel}-risk glass-panel`}
      variants={interruptAnimation}
      initial="hidden"
      animate={riskLevel === 'critical' ? 'urgent' : 'visible'}
    >
      <div className="interrupt-header">
        <div className={`header-icon risk-icon ${riskLevel}-risk-icon`}>
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div className="header-text">
          <h4 className="interrupt-title">{title}</h4>
          <span className="risk-badge">{riskLevel.toUpperCase()} RISK</span>
        </div>
      </div>

      <div className="interrupt-content">
        <div className="operation-info">
          {getOperationIcon()}
          <span className="operation-type">{operationType.replace('_', ' ').toUpperCase()}</span>
        </div>

        <p className="interrupt-message">{message}</p>

        {affectedItems.length > 0 && (
          <div className="affected-items">
            <h5 className="affected-title">Affected Items ({affectedItems.length}):</h5>
            <div className="items-list">
              {affectedItems.slice(0, 5).map((item, index) => (
                <div key={index} className="affected-item">
                  {item}
                </div>
              ))}
              {affectedItems.length > 5 && (
                <div className="more-items">
                  +{affectedItems.length - 5} more items
                </div>
              )}
            </div>
          </div>
        )}

        {requireReason && (
          <div className="reason-input-section">
            <label className="reason-label">Reason (required):</label>
            <textarea
              className="reason-textarea"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Explain why this operation is necessary..."
              rows={3}
            />
          </div>
        )}
      </div>

      <div className="interrupt-actions">
        <motion.button
          className="interrupt-btn cancel-btn"
          onClick={() => {
            onCancel?.();
            onResolve({ interruptId: id, action: 'cancel' });
          }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <XCircle className="w-4 h-4" />
          Cancel
        </motion.button>
        <motion.button
          className={`interrupt-btn proceed-btn ${riskLevel}-proceed`}
          onClick={() => onResolve({
            interruptId: id,
            action: 'proceed',
            data: requireReason ? { reason } : undefined
          })}
          disabled={!canProceed}
          whileHover={{ scale: canProceed ? 1.02 : 1 }}
          whileTap={{ scale: canProceed ? 0.98 : 1 }}
        >
          <AlertTriangle className="w-4 h-4" />
          Proceed with Operation
        </motion.button>
      </div>
    </motion.div>
  );
};

// Rate Limit Card
const RateLimitCard: React.FC<RateLimitInterruptProps> = ({
  id,
  title,
  message,
  serviceName,
  currentUsage,
  limit,
  actions,
  timestamp,
  onResolve
}) => {
  const usagePercentage = limit <= 0 ? 0 : Math.min(100, Math.round((currentUsage / limit) * 100));

  const getUsageColor = () => {
    if (usagePercentage >= 90) return 'var(--status-error)';
    if (usagePercentage >= 75) return 'var(--status-warning)';
    return 'var(--crystal-cyan-400)';
  };

  return (
    <motion.div
      className="interrupt-card rate-limit-card glass-panel"
      variants={interruptAnimation}
      initial="hidden"
      animate="visible"
    >
      <div className="interrupt-header">
        <div className="header-icon rate-limit-icon">
          <Clock className="w-5 h-5" />
        </div>
        <div className="header-text">
          <h4 className="interrupt-title">{title}</h4>
          <span className="service-name">{serviceName}</span>
        </div>
      </div>

      <div className="interrupt-content">
        <p className="interrupt-message">{message}</p>

        <div className="usage-meter-section">
          <div className="meter-header">
            <span className="meter-label">Current Usage</span>
            <span className="meter-value">{currentUsage} / {limit}</span>
          </div>
          <div className="meter-bar-container">
            <motion.div
              className="meter-bar"
              style={{ backgroundColor: getUsageColor() }}
              initial={{ width: 0 }}
              animate={{ width: `${usagePercentage}%` }}
              transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
            />
          </div>
          <div className="meter-footer">
            <span className={`percentage-label ${usagePercentage >= 90 ? 'critical' : usagePercentage >= 75 ? 'warning' : 'normal'}`}>
              {usagePercentage}% utilized
            </span>
          </div>
        </div>

        <div className="actions-section">
          <h5 className="actions-title">Choose an action:</h5>
          <div className="actions-grid">
            {actions.map((action) => (
              <motion.button
                key={action.id}
                className="action-option"
                onClick={() => onResolve({
                  interruptId: id,
                  action: action.id
                })}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {action.icon && <div className="action-icon">{action.icon}</div>}
                <div className="action-content">
                  <span className="action-label">{action.label}</span>
                  <span className="action-description">{action.description}</span>
                </div>
              </motion.button>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
};