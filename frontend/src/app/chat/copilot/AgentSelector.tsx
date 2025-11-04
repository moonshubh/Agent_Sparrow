"use client";

import React from "react";
import type { AgentChoice } from "@/features/chat/hooks/useAgentSelection";

export function AgentSelector({
  value,
  onChange,
  disabled,
}: {
  value: AgentChoice;
  onChange: (v: AgentChoice) => void;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as AgentChoice)}
      disabled={disabled}
      className="h-8 border rounded px-2 text-sm bg-background"
      aria-label="Select agent"
    >
      <option value="auto">Auto (Router)</option>
      <option value="primary">Primary Support</option>
      <option value="log_analysis">Log Analysis</option>
      <option value="research">Research</option>
    </select>
  );
}
