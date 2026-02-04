"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { isOAuthEnabled, oauthConfig } from "@/services/auth/oauth-config";
import { toast } from "sonner";
import { OAuthButton } from "./OAuthButton";
import { WarningMessage } from "./WarningMessage";
import { LocalDevLoginForm } from "./LocalDevLoginForm";

// Check if we're in local development mode with auth bypass
const isLocalAuthBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === "true";

// Helper function to create user-friendly error messages
const getErrorMessage = (error: unknown, provider: string): string => {
  if (error instanceof Error) {
    // Handle specific OAuth error patterns
    if (error.message.includes("popup_closed_by_user")) {
      return `${provider} login was cancelled. Please try again.`;
    }
    if (error.message.includes("unauthorized_client")) {
      return `${provider} login is not properly configured. Please contact support.`;
    }
    if (error.message.includes("access_denied")) {
      return `Access denied by ${provider}. Please check your permissions and try again.`;
    }
    if (error.message.includes("network")) {
      return "Network error occurred. Please check your connection and try again.";
    }
    // Return the original message for other errors
    return error.message;
  }

  // Fallback for unknown error types
  return `Failed to sign in with ${provider}. Please try again.`;
};

// Helper function for conditional development logging
const logError = (message: string, error: unknown, provider: string) => {
  if (process.env.NODE_ENV === "development") {
    console.error(`${provider} login error:`, error);
  } else {
    // In production, log a generic message without sensitive details
    console.error(message);
  }
};

export const LoginForm: React.FC = () => {
  // Use only authLoading from context - it already tracks OAuth login state
  const { loginWithOAuth, isLoading: authLoading } = useAuth();
  const [loadingProvider, setLoadingProvider] = useState<
    "google" | "github" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  // Debug logging
  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.log("LoginForm OAuth Config:", {
        isOAuthEnabled,
        googleEnabled: oauthConfig.google.enabled,
        githubEnabled: oauthConfig.github.enabled,
        googleClientId: oauthConfig.google.clientId,
        githubClientId: oauthConfig.github.clientId,
      });
    }
  }, []);

  // If local auth bypass is enabled, show the local login form
  if (isLocalAuthBypass) {
    return <LocalDevLoginForm />;
  }

  const handleOAuthLogin = async (provider: "google" | "github") => {
    // Pre-flight checks with user-friendly messages
    if (!isOAuthEnabled) {
      const message =
        "OAuth authentication is not enabled. Please configure OAuth providers.";
      toast.error(message);
      setError(message);
      return;
    }

    const config = oauthConfig[provider];
    if (!config.enabled) {
      const providerName = provider.charAt(0).toUpperCase() + provider.slice(1);
      const message = `${providerName} login is not configured. Please contact your administrator.`;
      toast.error(message);
      setError(message);
      return;
    }

    try {
      setLoadingProvider(provider);
      setError(null);
      await loginWithOAuth(provider);

      // Success feedback (loginWithOAuth handles redirect, so this may not be reached)
      toast.success(
        `Successfully connected to ${provider.charAt(0).toUpperCase() + provider.slice(1)}`,
      );
    } catch (error: unknown) {
      const errorMessage = getErrorMessage(
        error,
        provider.charAt(0).toUpperCase() + provider.slice(1),
      );

      // Log error with conditional detail level
      logError(errorMessage, error, provider);

      // Set user-friendly error message
      setError(errorMessage);

      // Show toast notification
      toast.error(errorMessage);
    } finally {
      setLoadingProvider(null);
    }
  };

  const isButtonDisabled = authLoading;

  return (
    <div className="space-y-4">
      {/* Error display */}
      {error && (
        <WarningMessage title="Authentication Error" variant="error">
          {error}
        </WarningMessage>
      )}

      <div className="space-y-3">
        <OAuthButton
          provider="google"
          isLoading={loadingProvider === "google"}
          disabled={isButtonDisabled || !oauthConfig.google.enabled}
          onClick={() => handleOAuthLogin("google")}
        />

        <OAuthButton
          provider="github"
          isLoading={loadingProvider === "github"}
          disabled={isButtonDisabled || !oauthConfig.github.enabled}
          onClick={() => handleOAuthLogin("github")}
        />
      </div>

      {/* Configuration warnings */}
      {!isOAuthEnabled && (
        <WarningMessage title="OAuth Not Configured">
          OAuth authentication is not enabled. Please set up OAuth providers in
          your environment configuration.
        </WarningMessage>
      )}

      {isOAuthEnabled &&
        !oauthConfig.google.enabled &&
        !oauthConfig.github.enabled && (
          <WarningMessage title="No Providers Available">
            No OAuth providers are configured. Please configure at least one
            OAuth provider.
          </WarningMessage>
        )}

      {/* Connection status indicator */}
      {isOAuthEnabled &&
        (oauthConfig.google.enabled || oauthConfig.github.enabled) && (
          <div className="flex items-center justify-center text-xs text-muted-foreground space-x-2">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            <span>Secure OAuth connection ready</span>
          </div>
        )}
    </div>
  );
};
