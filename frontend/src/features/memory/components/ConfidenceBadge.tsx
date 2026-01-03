'use client';

import React from 'react';
import { motion } from 'framer-motion';

const HIGH_THRESHOLD = 70;
const MEDIUM_THRESHOLD = 40;
const HIGH_COLOR = '#22C55E';
const HIGH_BG_COLOR = 'rgba(34, 197, 94, 0.15)';
const MEDIUM_COLOR = '#F59E0B';
const MEDIUM_BG_COLOR = 'rgba(245, 158, 11, 0.15)';
const LOW_COLOR = '#EF4444';
const LOW_BG_COLOR = 'rgba(239, 68, 68, 0.15)';

interface ConfidenceBadgeProps {
  score: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function ConfidenceBadge({ score, showLabel = false, size = 'md' }: ConfidenceBadgeProps) {
  const safeScore = Number.isFinite(score) ? Math.min(1, Math.max(0, score)) : 0;
  const percentage = Math.round(safeScore * 100);

  let level: 'high' | 'medium' | 'low';
  let color: string;
  let bgColor: string;

  if (percentage >= HIGH_THRESHOLD) {
    level = 'high';
    color = HIGH_COLOR;
    bgColor = HIGH_BG_COLOR;
  } else if (percentage >= MEDIUM_THRESHOLD) {
    level = 'medium';
    color = MEDIUM_COLOR;
    bgColor = MEDIUM_BG_COLOR;
  } else {
    level = 'low';
    color = LOW_COLOR;
    bgColor = LOW_BG_COLOR;
  }

  const sizeClasses = {
    sm: 'confidence-badge-sm',
    md: 'confidence-badge-md',
    lg: 'confidence-badge-lg',
  };

  return (
    <motion.div
      className={`confidence-badge ${sizeClasses[size]} confidence-badge-${level}`}
      style={{ backgroundColor: bgColor }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
    >
      <div
        className="confidence-badge-indicator"
        style={{ backgroundColor: color }}
      />
      <span className="confidence-badge-value" style={{ color }}>
        {percentage}%
      </span>
      {showLabel && (
        <span className="confidence-badge-label">{level}</span>
      )}
    </motion.div>
  );
}
