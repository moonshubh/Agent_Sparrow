"use client";

import React, { useState, useCallback, memo } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { copyToClipboard } from "../utils/clipboard";

interface CopyCodeButtonProps {
  /** Text content to copy to clipboard */
  text: string;
  /** Additional CSS classes */
  className?: string;
  /** Size variant */
  size?: "sm" | "md";
}

/**
 * CopyCodeButton - A button that copies text to clipboard with visual feedback.
 *
 * Displays a Copy icon by default, switches to Check icon on successful copy,
 * then reverts after a timeout.
 */
export const CopyCodeButton = memo(function CopyCodeButton({
  text,
  className,
  size = "sm",
}: CopyCodeButtonProps) {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = useCallback(
    async (e: React.MouseEvent<HTMLButtonElement>) => {
      e.preventDefault();
      e.stopPropagation();

      const success = await copyToClipboard(text);
      if (success) {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2500);
      }
    },
    [text],
  );

  const iconSize = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const buttonSize = size === "sm" ? "p-1.5" : "p-2";

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={isCopied ? "Copied!" : "Copy to clipboard"}
      aria-label={isCopied ? "Copied to clipboard" : "Copy code to clipboard"}
      className={cn(
        "rounded-md transition-all duration-200",
        "text-muted-foreground hover:text-foreground",
        "hover:bg-secondary/80 focus:outline-none focus:ring-2 focus:ring-primary/50",
        buttonSize,
        isCopied && "text-green-500 hover:text-green-500",
        className,
      )}
    >
      {isCopied ? (
        <Check className={cn(iconSize, "transition-transform duration-200")} />
      ) : (
        <Copy className={cn(iconSize, "transition-transform duration-200")} />
      )}
    </button>
  );
});

export default CopyCodeButton;
