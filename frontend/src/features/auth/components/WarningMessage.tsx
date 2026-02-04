"use client";

import React from "react";

interface WarningMessageProps {
  title: string;
  children: React.ReactNode;
  variant?: "warning" | "error" | "info";
}

// Helper function to get variant styles - moved outside component for performance
const getVariantStyles = (variant: "warning" | "error" | "info") => {
  switch (variant) {
    case "error":
      return {
        container:
          "bg-red-50 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800",
        indicator: "bg-red-500",
      };
    case "info":
      return {
        container:
          "bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-900/20 dark:text-blue-200 dark:border-blue-800",
        indicator: "bg-blue-500",
      };
    case "warning":
    default:
      return {
        container:
          "bg-yellow-50 text-yellow-800 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-200 dark:border-yellow-800",
        indicator: "bg-yellow-500",
      };
  }
};

export const WarningMessage: React.FC<WarningMessageProps> = ({
  title,
  children,
  variant = "warning",
}) => {
  const styles = getVariantStyles(variant);

  return (
    <div
      className={`rounded-md p-4 text-sm border ${styles.container}`}
      role="alert"
      aria-live="polite"
    >
      <div className="flex items-center space-x-2">
        <div className={`h-4 w-4 rounded-full ${styles.indicator}`} />
        <span className="font-medium">{title}</span>
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
};
