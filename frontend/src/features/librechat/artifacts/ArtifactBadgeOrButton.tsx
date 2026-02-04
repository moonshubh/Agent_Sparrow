"use client";

import React, { memo, useCallback } from "react";
import { FileCode2, GitBranch, Code, Globe } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useArtifactStore } from "./ArtifactContext";
import type { Artifact, ArtifactType } from "./types";

interface ArtifactBadgeOrButtonProps {
  /** The artifact to display */
  artifact: Artifact | null;
  /** Compact badge mode vs full button */
  variant?: "badge" | "button";
  /** Visual theme for different surfaces */
  theme?: "default" | "librechat";
  /** Additional CSS classes */
  className?: string;
}

function renderArtifactIcon(type: ArtifactType, className?: string) {
  switch (type) {
    case "mermaid":
      return <GitBranch className={className} />;
    case "react":
      return <FileCode2 className={className} />;
    case "html":
      return <Globe className={className} />;
    case "code":
    default:
      return <Code className={className} />;
  }
}

/**
 * Get display label for artifact type
 */
function getArtifactTypeLabel(type: ArtifactType): string {
  switch (type) {
    case "mermaid":
      return "Diagram";
    case "react":
      return "React Component";
    case "html":
      return "HTML";
    case "code":
    default:
      return "Code";
  }
}

/**
 * ArtifactBadgeOrButton - Inline element for artifact access
 *
 * Displays either as a compact badge or a more prominent button
 * that allows users to view the artifact in the artifacts panel.
 */
export const ArtifactBadgeOrButton = memo(function ArtifactBadgeOrButton({
  artifact,
  variant = "button",
  theme = "default",
  className,
}: ArtifactBadgeOrButtonProps) {
  const { currentArtifactId, setCurrentArtifact, setArtifactsVisible } =
    useArtifactStore();

  const isSelected = artifact?.id === currentArtifactId;

  const handleClick = useCallback(() => {
    if (!artifact) return;

    if (isSelected) {
      // Clicking selected artifact closes the panel
      setCurrentArtifact(null);
      setArtifactsVisible(false);
    } else {
      // Open the artifact panel with this artifact
      setCurrentArtifact(artifact.id);
      setArtifactsVisible(true);
    }
  }, [artifact, isSelected, setCurrentArtifact, setArtifactsVisible]);

  // Don't render if no artifact
  if (!artifact) {
    return null;
  }

  const typeLabel = getArtifactTypeLabel(artifact.type);

  if (theme === "librechat") {
    if (variant === "badge") {
      return (
        <button
          type="button"
          onClick={handleClick}
          className={cn(
            "lc-artifact-badge",
            isSelected && "selected",
            className,
          )}
          title={isSelected ? "Close artifact" : `View ${artifact.title}`}
        >
          {renderArtifactIcon(artifact.type, "lc-artifact-badge-icon")}
          <span className="lc-artifact-badge-label">{artifact.title}</span>
        </button>
      );
    }

    return (
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          "lc-artifact-button",
          isSelected && "selected",
          className,
        )}
      >
        <span className="lc-artifact-button-icon">
          {renderArtifactIcon(artifact.type)}
        </span>
        <span className="lc-artifact-button-text">
          <span className="lc-artifact-button-title">{artifact.title}</span>
          <span className="lc-artifact-button-meta">
            {isSelected
              ? "Click to close"
              : `Click to view ${typeLabel.toLowerCase()}`}
          </span>
        </span>
      </button>
    );
  }

  if (variant === "badge") {
    return (
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
          "transition-all duration-200 ease-out",
          isSelected
            ? "bg-primary/20 text-primary border border-primary/40"
            : "bg-secondary/60 text-muted-foreground border border-border/50 hover:bg-secondary hover:border-border",
          "hover:shadow-sm active:scale-95",
          className,
        )}
        title={isSelected ? "Close artifact" : `View ${artifact.title}`}
      >
        {renderArtifactIcon(artifact.type, "h-3 w-3")}
        <span className="truncate max-w-[120px]">{artifact.title}</span>
      </button>
    );
  }

  // Button variant - more prominent
  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn(
        "group relative my-4 w-fit rounded-xl text-sm",
        "overflow-hidden transition-all duration-300",
        "active:scale-[0.98]",
        isSelected
          ? "border-primary/40 bg-primary/10 shadow-lg"
          : "border-border bg-secondary/30 shadow-sm hover:border-border/80 hover:bg-secondary/50 hover:shadow-md",
        "border",
        className,
      )}
    >
      <div className="p-3">
        <div className="flex items-center gap-3">
          {/* Icon container */}
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg",
              isSelected
                ? "bg-primary/20 text-primary"
                : "bg-secondary text-muted-foreground group-hover:bg-secondary/80",
            )}
          >
            {renderArtifactIcon(artifact.type, "h-5 w-5")}
          </div>

          {/* Text content */}
          <div className="text-left overflow-hidden">
            <div className="font-medium text-foreground truncate max-w-[200px]">
              {artifact.title}
            </div>
            <div className="text-xs text-muted-foreground">
              {isSelected
                ? "Click to close"
                : `Click to view ${typeLabel.toLowerCase()}`}
            </div>
          </div>
        </div>
      </div>

      {/* Subtle gradient overlay on hover */}
      <div
        className={cn(
          "absolute inset-0 opacity-0 transition-opacity duration-300",
          "bg-gradient-to-r from-primary/5 to-transparent",
          "group-hover:opacity-100",
          isSelected && "opacity-100",
        )}
      />
    </button>
  );
});

export default ArtifactBadgeOrButton;
