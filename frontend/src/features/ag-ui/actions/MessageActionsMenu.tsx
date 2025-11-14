/**
 * Message Actions Menu
 * Radial hover menu with quick actions for messages
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Copy,
  RotateCcw,
  Info,
  ExternalLink,
  FileText,
  Check,
  MoreVertical
} from 'lucide-react';
import { crystalCardAnimation } from '@/shared/animations/crystalline-animations';
import './message-actions-menu.css';

export interface MessageAction {
  id: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}

export interface MessageActionsMenuProps {
  messageId: string;
  messageContent: string;
  hasMetadata?: boolean;
  hasSources?: boolean;
  canRegenerate?: boolean;
  onCopy?: () => void;
  onRegenerate?: () => void;
  onViewMetadata?: () => void;
  onShowSources?: () => void;
  onCopyAsMarkdown?: () => void;
  className?: string;
}

export const MessageActionsMenu: React.FC<MessageActionsMenuProps> = ({
  messageId,
  messageContent,
  hasMetadata = false,
  hasSources = false,
  canRegenerate = false,
  onCopy,
  onRegenerate,
  onViewMetadata,
  onShowSources,
  onCopyAsMarkdown,
  className = ''
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copiedAction, setCopiedAction] = useState<string | null>(null);

  const handleCopy = async () => {
    try {
      if (!navigator.clipboard) {
        console.error('Clipboard API not available');
        return;
      }
      await navigator.clipboard.writeText(messageContent);
      setCopiedAction('copy');
      onCopy?.();
      setTimeout(() => setCopiedAction(null), 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  const handleCopyMarkdown = async () => {
    try {
      if (!navigator.clipboard) {
        console.error('Clipboard API not available');
        return;
      }
      const markdown = `**Message (${messageId})**\n\n${messageContent}`;
      await navigator.clipboard.writeText(markdown);
      setCopiedAction('markdown');
      onCopyAsMarkdown?.();
      setTimeout(() => setCopiedAction(null), 2000);
    } catch (error) {
      console.error('Failed to copy markdown:', error);
    }
  };

  const actions: MessageAction[] = [
    {
      id: 'copy',
      label: 'Copy Text',
      icon: copiedAction === 'copy' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />,
      onClick: handleCopy
    },
    {
      id: 'copy-markdown',
      label: 'Copy as Markdown',
      icon: copiedAction === 'markdown' ? <Check className="w-4 h-4" /> : <FileText className="w-4 h-4" />,
      onClick: handleCopyMarkdown
    },
    {
      id: 'regenerate',
      label: 'Regenerate Response',
      icon: <RotateCcw className="w-4 h-4" />,
      onClick: () => onRegenerate?.(),
      disabled: !canRegenerate
    },
    {
      id: 'metadata',
      label: 'View Metadata',
      icon: <Info className="w-4 h-4" />,
      onClick: () => onViewMetadata?.(),
      disabled: !hasMetadata
    },
    {
      id: 'sources',
      label: 'Show Sources',
      icon: <ExternalLink className="w-4 h-4" />,
      onClick: () => onShowSources?.(),
      disabled: !hasSources
    }
  ];

  const radialPositions = [
    { angle: -90, radius: 70 },  // Top
    { angle: -45, radius: 70 },  // Top-right
    { angle: 0, radius: 70 },    // Right
    { angle: 45, radius: 70 },   // Bottom-right
    { angle: 90, radius: 70 }    // Bottom
  ];

  return (
    <div className={`message-actions-container ${className}`}>
      {/* Trigger Button */}
      <motion.button
        className="actions-trigger"
        onClick={() => setIsOpen(!isOpen)}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        aria-label="Message actions"
      >
        <MoreVertical className="w-4 h-4" />
      </motion.button>

      {/* Radial Menu */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              className="actions-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />

            {/* Action Buttons in Radial Layout */}
            <div className="radial-menu">
              {actions.map((action, index) => {
                const position = radialPositions[index];
                const x = Math.cos((position.angle * Math.PI) / 180) * position.radius;
                const y = Math.sin((position.angle * Math.PI) / 180) * position.radius;

                return (
                  <motion.button
                    key={action.id}
                    className={`action-button glass-panel ${action.disabled ? 'disabled' : ''}`}
                    disabled={action.disabled}
                    onClick={() => {
                      if (!action.disabled) {
                        action.onClick();
                        setIsOpen(false);
                      }
                    }}
                    initial={{
                      scale: 0,
                      opacity: 0,
                      x: 0,
                      y: 0
                    }}
                    animate={{
                      scale: 1,
                      opacity: action.disabled ? 0.3 : 1,
                      x,
                      y
                    }}
                    exit={{
                      scale: 0,
                      opacity: 0,
                      x: 0,
                      y: 0
                    }}
                    transition={{
                      delay: index * 0.05,
                      type: 'spring',
                      stiffness: 300,
                      damping: 20
                    }}
                    whileHover={!action.disabled ? {
                      scale: 1.15,
                      boxShadow: '0 0 25px var(--crystal-cyan-400)'
                    } : {}}
                    aria-label={action.label}
                  >
                    <div className="action-icon">
                      {action.icon}
                    </div>
                    <div className="action-tooltip glass-panel">
                      {action.label}
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

// Compact inline version for message list
export const MessageActionsInline: React.FC<MessageActionsMenuProps> = ({
  messageId,
  messageContent,
  hasMetadata = false,
  hasSources = false,
  canRegenerate = false,
  onCopy,
  onRegenerate,
  onViewMetadata,
  onShowSources,
  className = ''
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      if (!navigator.clipboard) {
        console.error('Clipboard API not available');
        return;
      }
      await navigator.clipboard.writeText(messageContent);
      setCopied(true);
      onCopy?.();
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  return (
    <div className={`message-actions-inline ${className}`}>
      <motion.button
        className="inline-action-btn glass-panel"
        onClick={handleCopy}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        aria-label="Copy message"
      >
        {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      </motion.button>

      {canRegenerate && (
        <motion.button
          className="inline-action-btn glass-panel"
          onClick={onRegenerate}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          aria-label="Regenerate response"
        >
          <RotateCcw className="w-3 h-3" />
        </motion.button>
      )}

      {hasMetadata && (
        <motion.button
          className="inline-action-btn glass-panel"
          onClick={onViewMetadata}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          aria-label="View metadata"
        >
          <Info className="w-3 h-3" />
        </motion.button>
      )}

      {hasSources && (
        <motion.button
          className="inline-action-btn glass-panel"
          onClick={onShowSources}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          aria-label="Show sources"
        >
          <ExternalLink className="w-3 h-3" />
        </motion.button>
      )}
    </div>
  );
};
