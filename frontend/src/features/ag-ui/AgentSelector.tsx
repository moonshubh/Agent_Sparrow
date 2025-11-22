"use client";

import React from "react";
import { AgentChoice } from "@/features/ag-ui/hooks/useAgentSelection";
import { cn } from "@/shared/lib/utils";
import { ChevronDown } from "lucide-react";

export const agentOptions: { value: AgentChoice; label: string; description: string }[] = [
  {
    value: "auto",
    label: "Auto Route",
    description: "Let Sparrow choose the right specialist",
  },
  {
    value: "primary",
    label: "Primary Support",
    description: "General troubleshooting + product context",
  },
  {
    value: "log_analysis",
    label: "Log Analysis",
    description: "Attach Mailbird logs for diagnostics",
  },
  {
    value: "research",
    label: "Research",
    description: "Deep KB + web lookups for answers",
  },
];

interface AgentSelectorProps {
  value: AgentChoice;
  onChange?: (v: AgentChoice) => void;
  disabled?: boolean;
  variant?: "cards" | "dropdown";
  showLabel?: boolean;
  className?: string;
}

export function AgentSelector({
  value,
  onChange,
  disabled,
  variant = "cards",
  showLabel = true,
  className = "",
}: AgentSelectorProps) {
  if (variant === "dropdown") {
    return (
      <div className={cn("flex flex-col gap-1.5 text-gray-400", className)}>
        {showLabel && (
          <span className="text-[11px] uppercase tracking-[0.2em]">
            Agent
          </span>
        )}
        <div className="relative">
          <select
            value={value}
            onChange={(e) => onChange?.(e.target.value as AgentChoice)}
            disabled={disabled}
            aria-label="Select agent mode"
            className="w-full h-10 appearance-none rounded-2xl border border-white/10 bg-white/5 pl-3 pr-8 text-sm text-gray-100 placeholder:text-gray-500 disabled:opacity-60 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
          >
            {agentOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2 w-full max-w-2xl", className)}>
      {showLabel && (
        <span className="text-[11px] uppercase tracking-[0.2em] text-gray-500">
          Agent Mode
        </span>
      )}

      <div className="grid grid-cols-2 gap-2">
        {agentOptions.map((option) => {
          const isActive = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange?.(option.value)}
              className={cn(
                "rounded-2xl border px-4 py-3 text-left transition-all duration-200 backdrop-blur-md",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0",
                isActive
                  ? "border-blue-500/40 bg-blue-500/20 text-white shadow-[0_0_20px_rgba(56,189,248,0.25)]"
                  : "border-white/10 bg-white/5 text-gray-300 hover:border-white/30 hover:text-white",
                disabled && "opacity-60 cursor-not-allowed hover:border-white/10 hover:text-gray-300"
              )}
              aria-pressed={isActive}
            >
              <span className="block text-sm font-semibold">
                {option.label}
              </span>
              <span className="mt-1 text-[11px] text-gray-400">
                {option.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
