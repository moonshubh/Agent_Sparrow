/**
 * Base Tool Evidence Card Component
 * Crystalline card design for displaying tool results with glass morphism effects
 */

import React, { useState, useRef, useEffect, ReactNode, useMemo } from 'react';
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
  FileText,
  Code
} from 'lucide-react';
import { crystalCardAnimation } from '@/shared/animations/crystalline-animations';
import { copyToClipboard } from '../utils/clipboard';
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

// Helper: Try to parse JSON from snippet
function tryParseJson(text: string): { parsed: any; isJson: boolean } {
  if (!text || typeof text !== 'string') return { parsed: null, isJson: false };
  const trimmed = text.trim();
  if (!((trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']')))) {
    return { parsed: null, isJson: false };
  }
  try {
    return { parsed: JSON.parse(trimmed), isJson: true };
  } catch {
    return { parsed: null, isJson: false };
  }
}

// Helper: Render key-value grid for flat objects
const KeyValueGrid: React.FC<{ obj: Record<string, any> }> = ({ obj }) => {
  const entries = Object.entries(obj || {}).filter(([_, v]) => v !== undefined && v !== null);
  if (!entries.length) return null;
  return (
    <div className="kv-grid">
      {entries.slice(0, 6).map(([k, v]) => (
        <div key={k} className="kv-row">
          <span className="kv-key">{k}:</span>
          <span className="kv-val" title={typeof v === 'string' ? v : undefined}>
            {typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
              ? String(v).slice(0, 80)
              : Array.isArray(v)
                ? v.slice(0, 3).map((x, i) => <span key={i} className="kv-pill">{String(x).slice(0, 20)}</span>)
                : '[object]'
            }
          </span>
        </div>
      ))}
    </div>
  );
};

// Helper: Render bullet list for arrays
const BulletList: React.FC<{ items: any[] }> = ({ items }) => {
  const trimmed = items.slice(0, 5);
  return (
    <ul className="nice-list">
      {trimmed.map((it, i) => (
        <li key={i}>
          {typeof it === 'string'
            ? it.slice(0, 100)
            : (it?.title || it?.name || it?.id || `Item ${i + 1}`)}
          {it?.snippet && <span className="muted"> — {String(it.snippet).slice(0, 80)}</span>}
        </li>
      ))}
    </ul>
  );
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
  const [isExpanded, setIsExpanded] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);
  const copyTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Parse snippet to detect JSON
  const { parsed, isJson } = useMemo(() => tryParseJson(snippet), [snippet]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    const textToCopy = fullContent || snippet;
    const success = await copyToClipboard(textToCopy);
    if (success) {
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

  // Render structured content when JSON is detected
  const renderContent = () => {
    if (!isJson || !parsed) {
      // Plain text snippet
      return (
        <div className="snippet-text">
          {snippet}
        </div>
      );
    }

    // JSON detected - render structured
    if (Array.isArray(parsed)) {
      return <BulletList items={parsed} />;
    }

    if (typeof parsed === 'object') {
      // Check for common container shapes
      const containerKeys = ['results', 'items', 'documents', 'entries', 'data'];
      for (const key of containerKeys) {
        if (Array.isArray(parsed[key])) {
          return <BulletList items={parsed[key]} />;
        }
      }
      // Flat object - render as key-value grid
      return <KeyValueGrid obj={parsed} />;
    }

    // Fallback to plain text
    return (
      <div className="snippet-text">
        {snippet}
      </div>
    );
  };

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
      <div className="card-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
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
                <span className="truncate max-w-[18ch]">{source || url}</span>
              </a>
            )}
          </div>
        </div>
        <div className="header-right">
          {getStatusBadge()}
          {timestamp && (
            <span className="timestamp">{timestamp}</span>
          )}
          <button className="expand-toggle" aria-label={isExpanded ? 'Collapse' : 'Expand'}>
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Score bars */}
      {(relevanceScore !== undefined || confidence !== undefined) && (
        <div className="scores-section">
          {relevanceScore !== undefined && getScoreBar(relevanceScore, 'Relevance', 'score-cyan')}
          {confidence !== undefined && getScoreBar(confidence, 'Confidence', 'score-amber')}
        </div>
      )}

      {/* Content Section */}
      <div className={`content-section ${isExpanded ? '' : 'single-line'}`}>
        {renderContent()}
      </div>

      {/* Expanded content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="expanded-content"
          >
            {/* Metadata section */}
            {metadata && Object.keys(metadata).length > 0 && (
              <div className="metadata-section">
                <h5 className="metadata-title">Metadata</h5>
                <div className="metadata-grid">
                  {Object.entries(metadata).map(([key, value]) => (
                    <div key={key} className="metadata-item">
                      <span className="metadata-key">{key}:</span>
                      <span className="metadata-value">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Raw JSON toggle for power users */}
            {isJson && (
              <div className="raw-json-section">
                <button
                  className="raw-json-toggle"
                  onClick={(e) => { e.stopPropagation(); setShowRawJson(!showRawJson); }}
                >
                  <Code className="w-3 h-3" />
                  {showRawJson ? 'Hide raw JSON' : 'View raw JSON'}
                </button>
                <AnimatePresence>
                  {showRawJson && (
                    <motion.pre
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="raw-json-content"
                    >
                      {JSON.stringify(parsed, null, 2)}
                    </motion.pre>
                  )}
                </AnimatePresence>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

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
