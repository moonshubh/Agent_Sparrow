'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  Brain,
  GitBranch,
  Link2,
  AlertTriangle,
} from 'lucide-react';
import type { MemoryStats } from '../types';

interface StatsPanelProps {
  stats?: MemoryStats;
  isLoading?: boolean;
}

// Spring animation config for smooth, bouncy interactions
const SPRING_CONFIG = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 25,
} as const;

// Pulse animation for icons
const ICON_PULSE_VARIANTS = {
  initial: { scale: 1 },
  animate: {
    scale: [1, 1.1, 1],
    transition: {
      duration: 2,
      repeat: Infinity,
      repeatDelay: 3,
    },
  },
};

// Subtle bounce animation for stat values
const VALUE_VARIANTS = {
  initial: { opacity: 0, y: 10 },
  animate: {
    opacity: 1,
    y: 0,
    transition: SPRING_CONFIG,
  },
};

// Icon wrapper component with animations
function AnimatedIcon({
  icon: Icon,
  className,
  delay = 0,
}: {
  icon: typeof Brain;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      variants={ICON_PULSE_VARIANTS}
      initial="initial"
      animate="animate"
      whileHover={{ scale: 1.15, rotate: 5 }}
      transition={{ ...SPRING_CONFIG, delay }}
    >
      <Icon size={22} />
    </motion.div>
  );
}

export function StatsPanel({ stats, isLoading }: StatsPanelProps) {
  if (isLoading) {
    return (
      <div className="stats-panel stats-panel-loading">
        {[1, 2, 3, 4].map((i) => (
          <motion.div
            key={i}
            className="stats-card stats-card-skeleton"
            initial={{ opacity: 0.5 }}
            animate={{ opacity: [0.5, 0.8, 0.5] }}
            transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.1 }}
          />
        ))}
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  return (
    <div className="stats-panel">
      {/* Total Memories Card */}
      <motion.div
        className="stats-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...SPRING_CONFIG, delay: 0 }}
        whileHover={{ y: -4, boxShadow: '0 8px 30px rgba(0, 120, 212, 0.15)' }}
      >
        <AnimatedIcon icon={Brain} className="stats-card-icon stats-card-icon-primary" />
        <div className="stats-card-content">
          <motion.span
            className="stats-card-value"
            variants={VALUE_VARIANTS}
            initial="initial"
            animate="animate"
          >
            {stats.total_memories.toLocaleString()}
          </motion.span>
          <span className="stats-card-label">Total Memories</span>
        </div>
      </motion.div>

      {/* Entities Card */}
      <motion.div
        className="stats-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...SPRING_CONFIG, delay: 0.05 }}
        whileHover={{ y: -4, boxShadow: '0 8px 30px rgba(56, 189, 248, 0.15)' }}
      >
        <AnimatedIcon
          icon={GitBranch}
          className="stats-card-icon stats-card-icon-blue"
          delay={0.1}
        />
        <div className="stats-card-content">
          <motion.span
            className="stats-card-value"
            variants={VALUE_VARIANTS}
            initial="initial"
            animate="animate"
          >
            {stats.total_entities.toLocaleString()}
          </motion.span>
          <span className="stats-card-label">Entities</span>
        </div>
      </motion.div>

      {/* Relationships Card */}
      <motion.div
        className="stats-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...SPRING_CONFIG, delay: 0.1 }}
        whileHover={{ y: -4, boxShadow: '0 8px 30px rgba(16, 185, 129, 0.15)' }}
      >
        <AnimatedIcon
          icon={Link2}
          className="stats-card-icon stats-card-icon-green"
          delay={0.2}
        />
        <div className="stats-card-content">
          <motion.span
            className="stats-card-value"
            variants={VALUE_VARIANTS}
            initial="initial"
            animate="animate"
          >
            {stats.total_relationships.toLocaleString()}
          </motion.span>
          <span className="stats-card-label">Relationships</span>
        </div>
      </motion.div>

      {/* Pending Duplicates Card */}
      <motion.div
        className="stats-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...SPRING_CONFIG, delay: 0.15 }}
        whileHover={{
          y: -4,
          boxShadow:
            stats.pending_duplicates > 0
              ? '0 8px 30px rgba(245, 158, 11, 0.15)'
              : '0 8px 30px rgba(107, 114, 128, 0.1)',
        }}
      >
        <motion.div
          className={`stats-card-icon ${
            stats.pending_duplicates > 0 ? 'stats-card-icon-orange' : 'stats-card-icon-gray'
          }`}
          animate={
            stats.pending_duplicates > 0
              ? {
                  scale: [1, 1.1, 1],
                  transition: { duration: 0.8, repeat: Infinity, repeatDelay: 2 },
                }
              : {}
          }
          whileHover={{ scale: 1.15, rotate: 5 }}
          transition={SPRING_CONFIG}
        >
          <AlertTriangle size={22} />
        </motion.div>
        <div className="stats-card-content">
          <motion.span
            className="stats-card-value"
            variants={VALUE_VARIANTS}
            initial="initial"
            animate="animate"
          >
            {stats.pending_duplicates}
          </motion.span>
          <span className="stats-card-label">Pending Duplicates</span>
        </div>
      </motion.div>

    </div>
  );
}
