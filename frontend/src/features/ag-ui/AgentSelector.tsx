"use client";

import React from "react";
import { AgentChoice } from "@/features/ag-ui/hooks/useAgentSelection";
import { cn } from "@/shared/lib/utils";
import { ChevronDown, Clock } from "lucide-react";

export const agentOptions: {
  value: AgentChoice;
  label: string;
  description: string;
  badge?: string;
  badgeTooltip?: string;
}[] = [
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
    description: "Deep analysis with Gemini Pro reasoning",
    badge: "Takes longer",
    badgeTooltip: "Uses advanced reasoning model for thorough analysis",
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
      <div className={cn("flex flex-col gap-1.5 text-muted-foreground", className)}>
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
            className="w-full h-10 appearance-none rounded-organic border border-border bg-secondary pl-3 pr-8 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-60 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400/40"
          >
            {agentOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}{option.badge ? ` (${option.badge})` : ""}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2 w-full max-w-2xl", className)}>
      {showLabel && (
        <span className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
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
                "rounded-organic border px-4 py-3 text-left transition-all duration-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0",
                isActive
                  ? "border-terracotta-400/40 bg-terracotta-500/15 text-foreground shadow-terracotta-glow"
                  : "border-border bg-secondary text-foreground/80 hover:border-border hover:text-foreground",
                disabled && "opacity-60 cursor-not-allowed hover:border-border hover:text-foreground/80"
              )}
              aria-pressed={isActive}
              title={option.badgeTooltip}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="block text-sm font-semibold">
                  {option.label}
                </span>
                {option.badge && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                    <Clock className="h-3 w-3" />
                    {option.badge}
                  </span>
                )}
              </div>
              <span className="mt-1 text-[11px] text-muted-foreground">
                {option.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
