/**
 * Base Tool Evidence Card Component
 * Crystalline card design for displaying tool results with glass morphism effects
 */

import React, { useState, useRef, useEffect, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Copy,
  Check,
  Sparkles,
  Database,
  Globe,
  FileText
} from 'lucide-react';
import { crystalCardAnimation, shimmerAnimation } from '@/shared/animations/crystalline-animations';
import './evidence-cards.css';

export interface ToolEvidenceProps {
  type: 'knowledge' | 'research' | 'log_analysis' | 'grounding';
  title: string;
  source?: string;
  url?: string;
  snippet: string;
  fullContent?: string;
  relevanceScore?: number;
  confidence?: number;
  metadata?: Record<string, any>;
  timestamp?: string;
  status?: 'success' | 'partial' | 'fallback';
  fallbackReason?: string;
  icon?: ReactNode;
  className?: string;
}

const typeIcons = {
  knowledge: <Database className="w-5 h-5" />,
  research: <Globe className="w-5 h-5" />,
  log_analysis: <FileText className="w-5 h-5" />,
  grounding: <Sparkles className="w-5 h-5" />
};

const typeColors = {
  knowledge: 'cyan',
  research: 'amber',
  log_analysis: 'gold',
  grounding: 'cyan'
};

export const ToolEvidenceCard: React.FC<ToolEvidenceProps> = ({
  type,
  title,
  source,
  url,
  snippet,
  fullContent,
  relevanceScore,
  confidence,
  metadata,
  timestamp,
  status = 'success',
  fallbackReason,
  icon,
  className = ''
}) => {
  const [isCopied, setIsCopied] = useState(false);
  const copyTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    try {
      if (!navigator.clipboard) {
        console.error('Clipboard API not available');
        return;
      }
      const textToCopy = fullContent || snippet;
      await navigator.clipboard.writeText(textToCopy);
      setIsCopied(true);

      // Clear any existing timeout
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }

      // Set new timeout
      copyTimeoutRef.current = setTimeout(() => {
        setIsCopied(false);
        copyTimeoutRef.current = null;
      }, 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  const getStatusBadge = () => {
    if (status === 'fallback' && fallbackReason) {
      return (
        <span className="status-badge status-fallback">
          Fallback: {fallbackReason}
        </span>
      );
    }
    if (status === 'partial') {
      return <span className="status-badge status-partial">Partial Result</span>;
    }
    return null;
  };

  const getScoreBar = (score: number, label: string, colorClass: string) => (
    <div className="score-container">
      <span className="score-label">{label}</span>
      <div className="score-bar-bg">
        <motion.div
          className={`score-bar ${colorClass}`}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 0.8, ease: [0.4, 0.0, 0.2, 1] }}
        >
          <span className="score-value">{score}%</span>
        </motion.div>
      </div>
    </div>
  );

  return (
    <motion.div
      className={`tool-evidence-card glass-panel ${type}-type ${className}`}
      variants={crystalCardAnimation}
      initial="hidden"
      animate="visible"
      whileHover="hover"
      whileTap="tap"
      layout
    >
      {/* Card Header */}
      <div className="card-header">
        <div className="header-left">
          <div className={`type-icon ${typeColors[type]}-glow`}>
            {icon || typeIcons[type]}
          </div>
          <div className="header-text">
            <h4 className="card-title">{title}</h4>
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="source-link"
                onClick={(e) => e.stopPropagation()}
                aria-label={`Open source link: ${url}`}
              >
                <ExternalLink className="w-3 h-3" />
                <span className="truncate max-w-[18ch]">{url}</span>
              </a>
            )}
          </div>
        </div>
        <div className="header-right">
          {getStatusBadge()}
          {timestamp && (
            <span className="timestamp">{timestamp}</span>
          )}
        </div>
      </div>

      {/* Content Section */}
      <div className="content-section single-line">
        <div className="snippet-text">
          {snippet}
        </div>
      </div>

      {/* Card Actions */}
      <div className="card-actions">
        <motion.button
          className="action-button copy-button"
          onClick={handleCopy}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          {isCopied ? (
            <>
              <Check className="w-4 h-4 text-green-500" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              <span>Copy</span>
            </>
          )}
        </motion.button>
      </div>

      {/* Crystalline glow effect */}
      <div className="crystal-glow-effect" />
    </motion.div>
  );
};
