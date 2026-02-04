"use client";

import React from "react";
import { Search, Database, FileSearch, Globe, Wrench } from "lucide-react";

interface ToolIndicatorProps {
  tools: string[];
}

function getToolIcon(toolName: string) {
  const name = toolName.toLowerCase();
  if (name.includes("kb") || name.includes("knowledge")) {
    return <Database size={14} />;
  }
  if (name.includes("file") || name.includes("log")) {
    return <FileSearch size={14} />;
  }
  if (name.includes("search") || name.includes("web")) {
    return <Globe size={14} />;
  }
  if (name.includes("lookup") || name.includes("find")) {
    return <Search size={14} />;
  }
  return <Wrench size={14} />;
}

function getToolDisplayName(toolName: string) {
  const displayNames: Record<string, string> = {
    web_search: "Searching the web",
    kb_search: "Searching knowledge base",
    search_mailbird_kb: "Searching knowledge base",
    tavily_search: "Searching with Tavily",
    firecrawl_extract: "Extracting from webpage",
    analyze_logs: "Analyzing logs",
    generate_image: "Generating image",
    write_todos: "Updating tasks",
  };

  return displayNames[toolName] || `Running ${toolName.replace(/_/g, " ")}`;
}

export function ToolIndicator({ tools }: ToolIndicatorProps) {
  if (tools.length === 0) {
    return null;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      {tools.map((tool, index) => (
        <div key={`${tool}-${index}`} className="lc-tool-indicator">
          <div className="lc-tool-spinner" />
          {getToolIcon(tool)}
          <span>{getToolDisplayName(tool)}</span>
        </div>
      ))}
    </div>
  );
}

export default ToolIndicator;
