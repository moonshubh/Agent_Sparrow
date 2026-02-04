"use client";

import React, { useMemo } from "react";

type ResearchStatus = "idle" | "running" | "stuck" | "failed";

interface ResearchProgressProps {
  progress: number;
  status: ResearchStatus;
  visible: boolean;
  attached?: boolean;
}

const clampProgress = (value: number): number => {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
};

export function ResearchProgress({
  progress,
  status,
  visible,
  attached = false,
}: ResearchProgressProps) {
  const displayPercent = useMemo(() => {
    const snapped = Math.round(clampProgress(progress) / 10) * 10;
    return Math.min(100, Math.max(0, snapped));
  }, [progress]);

  if (!visible || status === "idle") {
    return null;
  }

  const label =
    status === "stuck"
      ? "It is stuck"
      : status === "failed"
        ? "It is not working"
        : `Researching ${displayPercent}%`;

  const anchorClassName = attached
    ? "lc-research-progress-anchor lc-research-progress-anchor--attached"
    : "lc-research-progress-anchor";

  return (
    <div className={anchorClassName} role="status" aria-live="polite">
      <div className="lc-research-progress" data-status={status}>
        <span className="lc-research-pulse" aria-hidden="true" />
        <div className="lc-research-bar" aria-hidden="true">
          <div
            className="lc-research-fill"
            style={{ width: `${displayPercent}%` }}
          />
        </div>
        <span className="lc-research-label">{label}</span>
      </div>
    </div>
  );
}

export default ResearchProgress;
