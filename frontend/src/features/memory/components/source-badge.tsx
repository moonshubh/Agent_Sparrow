'use client';

import React from 'react';
import { Bot, User } from 'lucide-react';
import type { SourceType } from '../types';

interface SourceBadgeProps {
  sourceType: SourceType;
}

export function SourceBadge({ sourceType }: SourceBadgeProps) {
  const isManual = sourceType === 'manual';

  return (
    <div className={`source-badge ${isManual ? 'source-badge-manual' : 'source-badge-auto'}`}>
      {isManual ? <User size={12} /> : <Bot size={12} />}
      <span>{isManual ? 'Manual' : 'Auto'}</span>
    </div>
  );
}
