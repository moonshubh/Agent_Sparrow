"use client";

import React from "react";
import Link from "next/link";
import { Button } from "@/shared/ui/button";
import { ModelSelector } from "@/app/chat/components/ModelSelector";
import { AgentSelector } from "./AgentSelector";
import type { AgentChoice } from "@/features/chat/hooks/useAgentSelection";

/**
 * Chat Header for Phase 3 + Phase 4 CopilotKit Integration
 *
 * Contains controls positioned outside the CopilotSidebar:
 * - Agent type indicator
 * - Memory toggle
 * - Knowledge source toggles (KB, FeedMe) - Phase 4
 * - Model/provider selector
 * - Navigation links (Settings, FeedMe)
 * - Optional MCP URL input
 *
 * These controls affect the properties passed to CopilotKit via the parent component.
 */
export function ChatHeader({
  agentType,
  memoryEnabled,
  onMemoryToggle,
  kbEnabled,
  onKbToggle,
  feedmeEnabled,
  onFeedmeToggle,
  provider,
  model,
  onProviderChange,
  onModelChange,
  modelsByProvider,
  mcpUrl,
  onMcpUrlChange,
  // Phase 5: Multi-agent selection (optional)
  selectedAgent,
  onAgentChange,
}: {
  agentType: "primary" | "log_analysis";
  memoryEnabled: boolean;
  onMemoryToggle: (enabled: boolean) => void;
  // Phase 4: Knowledge source toggles
  kbEnabled?: boolean;
  onKbToggle?: (enabled: boolean) => void;
  feedmeEnabled?: boolean;
  onFeedmeToggle?: (enabled: boolean) => void;
  provider: "google" | "openai";
  model: string;
  onProviderChange: (provider: "google" | "openai") => void;
  onModelChange: (model: string) => void;
  modelsByProvider: Record<"google" | "openai", string[]>;
  mcpUrl?: string;
  onMcpUrlChange?: (url: string) => void;
  // Phase 5 (optional)
  selectedAgent?: AgentChoice;
  onAgentChange?: (v: AgentChoice) => void;
}) {
  // Show knowledge toggles if handlers are provided
  const showKnowledgeToggles = onKbToggle !== undefined || onFeedmeToggle !== undefined;
  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="max-w-7xl mx-auto px-4 py-3 space-y-3">
        {/* Top row: Title and navigation */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Agent Sparrow</h2>
            <span className="text-xs px-2 py-1 rounded border bg-muted/40">
              {agentType === "log_analysis" ? "Log Analysis" : "Primary"} Agent
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Button asChild variant="outline" className="h-8 px-3">
              <Link href="/settings" aria-label="Open Settings">
                Settings
              </Link>
            </Button>
            <Button asChild variant="secondary" className="h-8 px-3">
              <Link href="/feedme-revamped" aria-label="Open FeedMe">
                FeedMe
              </Link>
            </Button>
          </div>
        </div>

        {/* Bottom row: Controls */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {/* Memory toggle */}
            <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                aria-label="Use server memory"
                className="accent-primary cursor-pointer"
                checked={memoryEnabled}
                onChange={(e) => onMemoryToggle(e.target.checked)}
              />
              <span>Server Memory</span>
            </label>

            {/* Phase 4: Knowledge Source Toggles */}
            {showKnowledgeToggles && (
              <div className="flex items-center gap-3 pl-4 border-l">
                <span className="text-xs font-medium text-muted-foreground">
                  Knowledge Sources:
                </span>

                {onKbToggle && (
                  <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      aria-label="Enable Knowledge Base documents"
                      className="accent-primary cursor-pointer"
                      checked={kbEnabled ?? true}
                      onChange={(e) => onKbToggle(e.target.checked)}
                    />
                    <span>KB</span>
                  </label>
                )}

                {onFeedmeToggle && (
                  <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      aria-label="Enable FeedMe conversations"
                      className="accent-primary cursor-pointer"
                      checked={feedmeEnabled ?? true}
                      onChange={(e) => onFeedmeToggle(e.target.checked)}
                    />
                    <span>FeedMe</span>
                  </label>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            {/* Phase 5: Agent Selector (feature-flagged externally) */}
            {onAgentChange && selectedAgent && (
              <AgentSelector value={selectedAgent} onChange={onAgentChange} />
            )}
            {/* Model selector */}
            <ModelSelector
              provider={provider}
              model={model}
              onChangeProvider={onProviderChange}
              onChangeModel={onModelChange}
              align="right"
              modelsByProvider={modelsByProvider}
            />

            {/* MCP URL input (optional) */}
            {onMcpUrlChange !== undefined && (
              <input
                value={mcpUrl || ""}
                onChange={(e) => onMcpUrlChange(e.target.value)}
                placeholder="MCP SSE URL (optional)"
                className="h-8 w-56 px-2 py-1 text-xs border rounded-md bg-background"
                aria-label="MCP SSE URL"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
