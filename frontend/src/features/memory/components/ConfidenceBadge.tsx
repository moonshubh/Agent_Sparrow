'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface ConfidenceBadgeProps {
  score: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function ConfidenceBadge({ score, showLabel = false, size = 'md' }: ConfidenceBadgeProps) {
  const percentage = Math.round(score * 100);

  let level: 'high' | 'medium' | 'low';
  let color: string;
  let bgColor: string;

  if (percentage >= 70) {
    level = 'high';
    color = '#22C55E';
    bgColor = 'rgba(34, 197, 94, 0.15)';
  } else if (percentage >= 40) {
    level = 'medium';
    color = '#F59E0B';
    bgColor = 'rgba(245, 158, 11, 0.15)';
  } else {
    level = 'low';
    color = '#EF4444';
    bgColor = 'rgba(239, 68, 68, 0.15)';
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
