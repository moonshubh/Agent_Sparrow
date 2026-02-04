/**
 * Custom FolderIcon Component
 *
 * Uses the custom folder icon from the provided image instead of Lucide icons.
 * Maintains consistent sizing and styling with the existing design system.
 */

"use client";

import React from "react";
import Image from "next/image";
import { cn } from "@/shared/lib/utils";

interface FolderIconProps {
  /**
   * Size of the icon (width and height)
   * @default "16" (4 in Tailwind = 16px)
   */
  size?: string | number;

  /**
   * Whether the folder is open/expanded
   * @default false
   */
  isOpen?: boolean;

  /**
   * Additional CSS classes
   */
  className?: string;

  /**
   * Alt text for accessibility
   */
  alt?: string;

  /**
   * Color tint to apply to the icon
   */
  color?: string;
}

export function FolderIcon({
  size = 16,
  isOpen = false,
  className,
  alt = "Folder",
  color = "#0095ff", // Mailbird blue default
}: FolderIconProps) {
  const sizeValue = typeof size === "string" ? size : `${size}px`;

  return (
    <div
      className={cn("inline-flex items-center justify-center", className)}
      style={{
        width: sizeValue,
        height: sizeValue,
        filter: color
          ? `hue-rotate(210deg) saturate(1.2) brightness(0.9)`
          : undefined,
      }}
    >
      <Image
        src="/folder-icon.png"
        alt={alt}
        width={typeof size === "number" ? size : 16}
        height={typeof size === "number" ? size : 16}
        className={cn(
          "object-contain",
          isOpen && "opacity-80", // Slightly dimmed when open
        )}
        style={{
          filter:
            color && color !== "#0095ff"
              ? `hue-rotate(${getHueRotation(color)}deg)`
              : undefined,
        }}
      />
    </div>
  );
}

/**
 * Calculate hue rotation needed to achieve target color
 * This is a simplified approximation for basic color tinting
 */
function getHueRotation(targetColor: string): number {
  // Simple color mapping for common folder colors
  const colorMap: Record<string, number> = {
    "#e74c3c": 0, // Red
    "#e67e22": 30, // Orange
    "#f1c40f": 60, // Yellow
    "#27ae60": 120, // Green
    "#3498db": 210, // Blue (default)
    "#9b59b6": 270, // Purple
    "#95a5a6": 0, // Gray
  };

  return colorMap[targetColor.toLowerCase()] || 210; // Default to blue
}

// Export a simple wrapper for backward compatibility with existing Folder/FolderOpen usage
export const CustomFolder = (props: Omit<FolderIconProps, "isOpen">) => (
  <FolderIcon {...props} isOpen={false} />
);

export const CustomFolderOpen = (props: Omit<FolderIconProps, "isOpen">) => (
  <FolderIcon {...props} isOpen={true} />
);
