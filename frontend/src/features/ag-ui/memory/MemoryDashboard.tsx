/**
 * Memory Visualization Dashboard
 * Displays memory as a constellation of connected facts with crystalline effects
 */

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain,
  Database,
  TrendingUp,
  Star,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize2,
  X,
  Clock,
  Hash
} from 'lucide-react';
import {
  memoryNodeAnimation,
  neuralPulseAnimation,
  crystalCardAnimation,
  floatAnimation
} from '@/shared/animations/crystalline-animations';
import './memory-dashboard.css';

export interface MemoryFact {
  id: string;
  fact: string;
  relevanceScore?: number;
  createdAt: string;
  retrievedCount?: number;
  category?: string;
  connections?: string[]; // IDs of related facts
}

export interface MemoryDashboardProps {
  sessionId: string;
  facts: MemoryFact[];
  recentlyRetrieved?: string[]; // IDs of recently retrieved facts
  recentlyWritten?: string[]; // IDs of recently written facts
  isLoading?: boolean;
  onFactClick?: (fact: MemoryFact) => void;
  className?: string;
}

// Helper function to calculate hours since creation
const getHoursSinceCreation = (createdAt: string): number => {
  return Math.round((Date.now() - new Date(createdAt).getTime()) / (1000 * 60 * 60));
};

export const MemoryDashboard: React.FC<MemoryDashboardProps> = ({
  sessionId,
  facts,
  recentlyRetrieved = [],
  recentlyWritten = [],
  isLoading = false,
  onFactClick,
  className = ''
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [selectedFact, setSelectedFact] = useState<MemoryFact | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  // Calculate node positions for constellation layout
  const getNodePosition = (index: number, total: number) => {
    const radius = 120;
    const angle = (index / total) * Math.PI * 2;
    const spiralFactor = 1 + (index / total) * 0.5;

    return {
      x: Math.cos(angle) * radius * spiralFactor + 200,
      y: Math.sin(angle) * radius * spiralFactor + 200
    };
  };

  // Determine node state (dormant, retrieved, writing)
  const getNodeState = (factId: string): 'dormant' | 'retrieved' | 'writing' => {
    if (recentlyWritten.includes(factId)) return 'writing';
    if (recentlyRetrieved.includes(factId)) return 'retrieved';
    return 'dormant';
  };

  // Get color based on recency
  const getNodeColor = (createdAt: string) => {
    const hoursSinceCreation = getHoursSinceCreation(createdAt);

    if (hoursSinceCreation < 1) return 'var(--accent-gold-400)'; // Very recent - gold
    if (hoursSinceCreation < 24) return 'var(--accent-amber-400)'; // Recent - amber
    return 'var(--crystal-cyan-400)'; // Older - cyan
  };

  const handleFactClick = (fact: MemoryFact) => {
    setSelectedFact(fact);
    onFactClick?.(fact);
  };

  const totalFacts = facts.length;
  const retrievalRate = totalFacts === 0
    ? 0
    : Math.round((recentlyRetrieved.length / totalFacts) * 100);

  return (
    <motion.div
      className={`memory-dashboard glass-panel ${isExpanded ? 'expanded' : 'collapsed'} ${className}`}
      variants={crystalCardAnimation}
      initial="hidden"
      animate="visible"
      layout
    >
      {/* Dashboard Header */}
      <div className="dashboard-header">
        <div className="header-left">
          <motion.div
            className="brain-icon"
            variants={neuralPulseAnimation}
            animate="pulse"
          >
            <Brain className="w-5 h-5" />
          </motion.div>
          <div className="header-text">
            <h3 className="dashboard-title">Memory Constellation</h3>
            <p className="dashboard-subtitle">
              {totalFacts} facts • {retrievalRate}% active
            </p>
          </div>
        </div>
        <div className="header-actions">
          {!isExpanded && (
            <button
              className="action-btn"
              onClick={() => setIsExpanded(true)}
              aria-label="Expand memory dashboard"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
          )}
          {isExpanded && (
            <>
              <button
                className="action-btn"
                onClick={() => setZoom(Math.min(zoom + 0.2, 2))}
                aria-label="Zoom in"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                className="action-btn"
                onClick={() => setZoom(Math.max(zoom - 0.2, 0.5))}
                aria-label="Zoom out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <button
                className="action-btn"
                onClick={() => setIsExpanded(false)}
                aria-label="Close memory dashboard"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Stats Bar */}
      <div className="stats-bar">
        <StatItem
          icon={<Database className="w-4 h-4" />}
          label="Total Facts"
          value={totalFacts}
          color="cyan"
        />
        <StatItem
          icon={<TrendingUp className="w-4 h-4" />}
          label="Retrieved"
          value={recentlyRetrieved.length}
          color="amber"
        />
        <StatItem
          icon={<Star className="w-4 h-4" />}
          label="Recently Added"
          value={recentlyWritten.length}
          color="gold"
        />
      </div>

      {/* Constellation View */}
      {isExpanded && (
        <motion.div
          className="constellation-container"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 400 }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div
            ref={canvasRef}
            className="constellation-canvas"
            style={{ transform: `scale(${zoom})` }}
          >
            {/* Connection Lines */}
            <svg className="connections-layer">
              {facts.map((fact, index) => {
                if (!fact.connections) return null;

                const start = getNodePosition(index, totalFacts);

                return fact.connections.map((targetId) => {
                  const targetIndex = facts.findIndex(f => f.id === targetId);
                  if (targetIndex === -1) return null;

                  const end = getNodePosition(targetIndex, totalFacts);

                  return (
                    <motion.line
                      key={`${fact.id}-${targetId}`}
                      x1={start.x}
                      y1={start.y}
                      x2={end.x}
                      y2={end.y}
                      className="connection-line"
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 0.3 }}
                      transition={{ duration: 0.8, delay: index * 0.05 }}
                    />
                  );
                });
              })}
            </svg>

            {/* Fact Nodes */}
            {facts.map((fact, index) => {
              const position = getNodePosition(index, totalFacts);
              const nodeState = getNodeState(fact.id);
              const color = getNodeColor(fact.createdAt);

              return (
                <motion.div
                  key={fact.id}
                  className={`fact-node ${nodeState}`}
                  style={{
                    left: position.x,
                    top: position.y,
                    '--node-color': color
                  } as React.CSSProperties}
                  variants={memoryNodeAnimation}
                  animate={nodeState}
                  onClick={() => handleFactClick(fact)}
                  whileHover={{ scale: 1.3 }}
                  whileTap={{ scale: 0.9 }}
                >
                  <div className="node-inner">
                    {nodeState === 'writing' ? (
                      <Sparkles className="w-3 h-3" />
                    ) : (
                      <Star className="w-3 h-3" />
                    )}
                  </div>
                  {fact.relevanceScore && (
                    <div className="relevance-badge">
                      {Math.round(fact.relevanceScore)}%
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>

          {/* Loading Overlay */}
          {isLoading && (
            <div className="loading-overlay">
              <motion.div
                className="loading-spinner"
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
              >
                <Brain className="w-8 h-8" />
              </motion.div>
              <p className="loading-text">Retrieving memories...</p>
            </div>
          )}
        </motion.div>
      )}

      {/* Selected Fact Detail Panel */}
      <AnimatePresence>
        {selectedFact && isExpanded && (
          <FactDetailPanel
            fact={selectedFact}
            onClose={() => setSelectedFact(null)}
          />
        )}
      </AnimatePresence>

      {/* Compact View (when collapsed) */}
      {!isExpanded && (
        <motion.div
          className="compact-view"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          <div className="recent-facts">
            <h4 className="section-title">Recent Activity</h4>
            {facts.slice(0, 3).map((fact, index) => (
              <motion.div
                key={fact.id}
                className="fact-preview"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <div className="fact-icon">
                  {recentlyWritten.includes(fact.id) ? (
                    <Sparkles className="w-3 h-3 text-gold" />
                  ) : (
                    <Star className="w-3 h-3 text-cyan" />
                  )}
                </div>
                <p className="fact-text">
                  {fact.fact.length > 50 ? `${fact.fact.slice(0, 50)}...` : fact.fact}
                </p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </motion.div>
  );
};

// Stat Item Component
const StatItem: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: number;
  color: 'cyan' | 'amber' | 'gold';
}> = ({ icon, label, value, color }) => {
  return (
    <div className={`stat-item stat-${color}`}>
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  );
};

// Fact Detail Panel
const FactDetailPanel: React.FC<{
  fact: MemoryFact;
  onClose: () => void;
}> = ({ fact, onClose }) => {
  const hoursSinceCreation = getHoursSinceCreation(fact.createdAt);

  return (
    <motion.div
      className="fact-detail-panel glass-panel"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.3 }}
    >
      <div className="detail-header">
        <h4 className="detail-title">Memory Detail</h4>
        <button className="close-btn" onClick={onClose}>
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="detail-content">
        <p className="fact-content">{fact.fact}</p>

        <div className="fact-metadata">
          {fact.relevanceScore && (
            <div className="metadata-item">
              <TrendingUp className="w-3 h-3" />
              <span>Relevance: {Math.round(fact.relevanceScore)}%</span>
            </div>
          )}
          <div className="metadata-item">
            <Clock className="w-3 h-3" />
            <span>
              {hoursSinceCreation < 1
                ? 'Just now'
                : hoursSinceCreation < 24
                ? `${hoursSinceCreation}h ago`
                : `${Math.floor(hoursSinceCreation / 24)}d ago`}
            </span>
          </div>
          {fact.retrievedCount && (
            <div className="metadata-item">
              <Hash className="w-3 h-3" />
              <span>Retrieved {fact.retrievedCount}x</span>
            </div>
          )}
        </div>

        {fact.category && (
          <div className="fact-category">
            <span className="category-badge">{fact.category}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
};