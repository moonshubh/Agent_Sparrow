"use client";

import React from "react";
import Link from "next/link";
import { Button } from "@/shared/ui/button";
import { ModelSelector } from "@/app/chat/components/ModelSelector";

/**
 * Chat Header for Phase 3 CopilotKit Integration
 *
 * Contains controls positioned outside the CopilotSidebar:
 * - Agent type indicator
 * - Memory toggle
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
  provider,
  model,
  onProviderChange,
  onModelChange,
  modelsByProvider,
  mcpUrl,
  onMcpUrlChange,
}: {
  agentType: "primary" | "log_analysis";
  memoryEnabled: boolean;
  onMemoryToggle: (enabled: boolean) => void;
  provider: "google" | "openai";
  model: string;
  onProviderChange: (provider: "google" | "openai") => void;
  onModelChange: (model: string) => void;
  modelsByProvider: Record<"google" | "openai", string[]>;
  mcpUrl?: string;
  onMcpUrlChange?: (url: string) => void;
}) {
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
          </div>

          <div className="flex items-center gap-4">
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
