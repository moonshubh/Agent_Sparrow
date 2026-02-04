"use client";

import { useAuth } from "@/features/auth/hooks/useAuth";

export const DevModeIndicator: React.FC = () => {
  const { user } = useAuth();
  const bypassAuth = process.env.NEXT_PUBLIC_BYPASS_AUTH === "true";
  const devMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

  // Only show in development bypass mode
  if (
    !bypassAuth ||
    !devMode ||
    !user ||
    user.app_metadata?.provider !== "bypass"
  ) {
    return null;
  }

  return (
    <div className="fixed top-4 left-4 z-50">
      <div className="bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300 dark:border-yellow-700 rounded-lg px-3 py-2 text-xs">
        <div className="flex items-center space-x-2">
          <div className="h-2 w-2 bg-yellow-500 rounded-full animate-pulse" />
          <span className="font-medium text-yellow-800 dark:text-yellow-200">
            DEV MODE - Auth Bypassed
          </span>
        </div>
        <div className="text-yellow-700 dark:text-yellow-300 mt-1">
          User: {user.user_metadata?.full_name || user.email}
        </div>
      </div>
    </div>
  );
};
