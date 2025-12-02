"use client";

import React from "react";
import { SettingsButtonV2 } from "@/shared/ui/SettingsButtonV2";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Button } from "@/shared/ui/button";
import { ModelSelector } from "./ModelSelector";
import { ProviderSelector } from "./ProviderSelector";
import { AgentSelector } from "./AgentSelector";
import type { AgentChoice } from "@/features/ag-ui/hooks/useAgentSelection";
import { Activity, PanelsTopLeft, Sparkles } from "lucide-react";
import type { Provider, ProviderAvailability } from "@/services/api/endpoints/models";
import { useArtifactStore } from "./artifacts/ArtifactContext";

interface ChatHeaderProps {
  agentType: AgentChoice;
  memoryEnabled: boolean;
  onMemoryToggle: (enabled: boolean) => void;
  provider: Provider;
  onProviderChange: (provider: Provider) => void;
  availableProviders: ProviderAvailability;
  model: string;
  onModelChange: (model: string) => void;
  models: string[];
  onAgentChange?: (v: AgentChoice) => void;
  modelHelperText?: string;
  recommendedModel?: string;
  activeTools?: string[];
  hasActiveConversation?: boolean;
  resolvedTaskType?: string;
}

/**
 * Chat Header for the AG-UI client.
 * Dark Academia Theme - Scholarly Warmth
 */
export function ChatHeader({
  agentType,
  memoryEnabled,
  onMemoryToggle,
  provider,
  onProviderChange,
  availableProviders,
  model,
  onModelChange,
  models,
  onAgentChange,
  modelHelperText,
  recommendedModel,
  activeTools,
  hasActiveConversation = false,
  resolvedTaskType,
}: ChatHeaderProps) {
  const router = useRouter();
  const activeToolCount = activeTools?.length ?? 0;
  const hasActiveTools = activeToolCount > 0;
  const agentBadge =
    resolvedTaskType === "log_analysis" || agentType === "log_analysis"
      ? "Log Analysis"
      : resolvedTaskType === "research" || agentType === "research"
        ? "Research"
        : agentType === "auto"
          ? "Auto Route"
          : "Primary Support";
  const handleFeedMe = () => {
    router.push("/feedme");
  };

  // Artifact store for showing generated images
  const { artifactsById, setArtifactsVisible, setCurrentArtifact } = useArtifactStore();
  const artifactCount = Object.keys(artifactsById).length;
  const hasArtifacts = artifactCount > 0;

  const handleOpenArtifacts = () => {
    // Open the most recent artifact
    const artifactIds = Object.keys(artifactsById);
    if (artifactIds.length > 0) {
      setCurrentArtifact(artifactIds[artifactIds.length - 1]);
      setArtifactsVisible(true);
    }
  };

  return (
    <div className="w-full z-50 border-b border-border bg-background/90 backdrop-blur-sm transition-all duration-300">
      <div className="max-w-7xl mx-auto px-6 py-2.5">
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Branding + status */}
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center gap-3">
                <div className="relative w-10 h-10 rounded-organic bg-secondary border border-border overflow-hidden shadow-academia-sm">
                  <Image
                    src="/Sparrow_logo_cropped.png"
                    alt="Agent Sparrow"
                    fill
                    className="object-cover"
                    sizes="40px"
                    priority
                  />
                </div>
                <h2 className="text-base font-semibold text-foreground tracking-tight leading-tight">Agent Sparrow</h2>
              </div>

              <div className="flex items-center gap-2 pl-3 border-l border-border text-xs text-muted-foreground">
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
                  <span className="text-xs font-medium px-2.5 py-1 rounded-organic-sm bg-secondary text-secondary-foreground border border-border">
                    {agentBadge}
                  </span>
                )}
                {hasActiveTools && (
                  <span className="flex items-center gap-2 px-2.5 py-1 rounded-organic-sm bg-sage-600/15 border border-sage-600/25 text-xs font-medium text-sage-300">
                    <Activity className="w-3 h-3 text-sage-400 animate-pulse" />
                    {activeToolCount} tool{activeToolCount === 1 ? '' : 's'}
                  </span>
                )}
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => onMemoryToggle(!memoryEnabled)}
                className={`text-xs font-medium px-3 py-1.5 rounded-organic transition-all duration-200 border whitespace-nowrap ${memoryEnabled
                  ? "bg-sage-600/15 border-sage-500/30 text-sage-300 shadow-sage-glow"
                  : "bg-secondary border-border text-muted-foreground hover:text-foreground"
                  }`}
                aria-pressed={memoryEnabled}
              >
                Memory {memoryEnabled ? "On" : "Off"}
              </button>

              {/* Artifact indicator button - shows when images/articles are generated */}
              {hasArtifacts && (
                <button
                  onClick={handleOpenArtifacts}
                  className="text-xs font-medium px-3 py-1.5 rounded-organic border border-terracotta-500/30 bg-terracotta-500/15 text-terracotta-300 hover:bg-terracotta-500/25 transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap shadow-sm"
                  aria-label={`View ${artifactCount} generated artifact${artifactCount !== 1 ? 's' : ''}`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  {artifactCount} Artifact{artifactCount !== 1 ? 's' : ''}
                </button>
              )}

              <button
                onClick={handleFeedMe}
                className="text-xs font-medium px-3 py-1.5 rounded-organic border border-border bg-secondary text-secondary-foreground hover:text-foreground transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap"
                aria-label="Open Feed Me"
              >
                <PanelsTopLeft className="w-3.5 h-3.5 text-muted-foreground" />
                Feed Me
              </button>

              <ProviderSelector
                provider={provider}
                onChangeProvider={onProviderChange}
                availableProviders={availableProviders}
                align="right"
              />

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
            <div className="flex sm:hidden justify-center items-center gap-2 px-3 py-2 rounded-organic bg-sage-600/15 border border-sage-600/25 text-xs font-medium text-sage-300 w-fit mx-auto">
              <Activity className="w-3 h-3 text-sage-400 animate-pulse" />
              {activeToolCount} tool{activeToolCount === 1 ? '' : 's'} active
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
