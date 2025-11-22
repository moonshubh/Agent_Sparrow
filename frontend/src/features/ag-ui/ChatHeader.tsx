"use client";

import React from "react";
import { SettingsButtonV2 } from "@/shared/ui/SettingsButtonV2";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Button } from "@/shared/ui/button";
import { ModelSelector } from "./ModelSelector";
import { AgentSelector } from "./AgentSelector";
import type { AgentChoice } from "@/features/ag-ui/hooks/useAgentSelection";
import { Activity, PanelsTopLeft } from "lucide-react";

interface ChatHeaderProps {
  agentType: AgentChoice;
  memoryEnabled: boolean;
  onMemoryToggle: (enabled: boolean) => void;
  model: string;
  onModelChange: (model: string) => void;
  models: string[];
  onAgentChange?: (v: AgentChoice) => void;
  modelHelperText?: string;
  recommendedModel?: string;
  activeTools?: string[];
  hasActiveConversation?: boolean;
}

/**
 * Chat Header for the AG-UI client.
 * Polished Mailbird Dark Theme
 */
export function ChatHeader({
  agentType,
  memoryEnabled,
  onMemoryToggle,
  model,
  onModelChange,
  models,
  onAgentChange,
  modelHelperText,
  recommendedModel,
  activeTools,
  hasActiveConversation = false,
}: ChatHeaderProps) {
  const router = useRouter();
  const activeToolCount = activeTools?.length ?? 0;
  const hasActiveTools = activeToolCount > 0;
  const agentBadge =
    agentType === "log_analysis"
      ? "Log Analysis"
      : agentType === "research"
        ? "Research"
        : agentType === "auto"
          ? "Auto Route"
          : "Primary Support";
  const handleFeedMe = () => {
    router.push("/feedme");
  };

  return (
    <div className="w-full z-50 border-b border-white/5 bg-[hsl(220,15%,10%)]/70 backdrop-blur-md transition-all duration-300">
      <div className="max-w-7xl mx-auto px-6 py-2.5">
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Branding + status */}
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center gap-3">
                <div className="relative w-10 h-10 rounded-2xl bg-white/5 border border-white/10 overflow-hidden shadow-lg shadow-blue-500/25">
                  <Image
                    src="/Sparrow_logo_cropped.png"
                    alt="Agent Sparrow"
                    fill
                    className="object-cover"
                    sizes="40px"
                    priority
                  />
                </div>
                <h2 className="text-base font-semibold text-white tracking-tight leading-tight">Agent Sparrow</h2>
              </div>

              <div className="flex items-center gap-2 pl-3 border-l border-white/10 text-xs text-gray-400">
                {hasActiveConversation ? (
                  <AgentSelector
                    value={agentType}
                    onChange={(value) => onAgentChange?.(value)}
                    disabled={!onAgentChange}
                    variant="dropdown"
                    showLabel={false}
                    className="min-w-[150px] !gap-0"
                  />
                ) : (
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-white/5 text-gray-300 border border-white/10">
                    {agentBadge}
                  </span>
                )}
                {hasActiveTools && (
                  <span className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs font-medium text-emerald-300">
                    <Activity className="w-3 h-3 text-emerald-300 animate-pulse" />
                    {activeToolCount} tool{activeToolCount === 1 ? '' : 's'}
                  </span>
                )}
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => onMemoryToggle(!memoryEnabled)}
                className={`text-xs font-medium px-3 py-1.5 rounded-xl transition-all duration-200 border whitespace-nowrap ${memoryEnabled
                  ? "bg-blue-500/15 border-blue-500/30 text-blue-300 shadow-[0_0_15px_rgba(56,189,248,0.2)]"
                  : "bg-white/5 border-white/10 text-gray-400 hover:text-white"
                  }`}
                aria-pressed={memoryEnabled}
              >
                Memory {memoryEnabled ? "On" : "Off"}
              </button>

              <button
                onClick={handleFeedMe}
                className="text-xs font-medium px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 text-gray-300 hover:text-white transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap"
                aria-label="Open Feed Me"
              >
                <PanelsTopLeft className="w-3.5 h-3.5 text-gray-400" />
                Feed Me
              </button>

              <div className="w-[140px]">
                <ModelSelector
                  model={model}
                  onChangeModel={onModelChange}
                  align="right"
                  models={models}
                  helperText={modelHelperText}
                  recommended={recommendedModel}
                />
              </div>

              <SettingsButtonV2 />
            </div>
          </div>

          {/* Agent Selector + mobile active status */}
          {!hasActiveConversation && (
            <div className="flex justify-center w-full">
              <AgentSelector
                value={agentType}
                onChange={(value) => onAgentChange?.(value)}
                disabled={!onAgentChange}
              />
            </div>
          )}

          {hasActiveTools && (
            <div className="flex sm:hidden justify-center items-center gap-2 px-3 py-2 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-xs font-medium text-emerald-200 w-fit mx-auto">
              <Activity className="w-3 h-3 text-emerald-200 animate-pulse" />
              {activeToolCount} tool{activeToolCount === 1 ? '' : 's'} active
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
