'use client';

import React from 'react';
import type { SourceType } from '../types';

interface SourceBadgeProps {
  sourceType: SourceType;
}

export function SourceBadge({ sourceType }: SourceBadgeProps) {
  const isManual = sourceType === 'manual';

  return (
    <div className={`source-badge ${isManual ? 'source-badge-manual' : 'source-badge-auto'}`}>
      <span>{isManual ? 'Manual' : 'Auto'}</span>
    </div>
  );
}
