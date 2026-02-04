"use client";

import React, { useEffect, useState } from "react";
import { Separator } from "@/shared/ui/separator";
import { Alert, AlertDescription } from "@/shared/ui/alert";
import { AlertCircle, Info } from "lucide-react";
import { APIKeyInput } from "@/features/settings/components/APIKeyInput";
import { APIKeyInfo, APIKeyType, apiKeyService } from "@/services/api/api-keys";

export function APIKeysPanel() {
  const [apiKeys, setAPIKeys] = useState<APIKeyInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (process.env.NODE_ENV === "development") {
        // Keep dev smooth without backend wiring
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const result = await apiKeyService.listAPIKeys();
        setAPIKeys(result.api_keys);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to load API keys";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const refresh = async () => {
    try {
      const result = await apiKeyService.listAPIKeys();
      setAPIKeys(result.api_keys);
    } catch (err) {
      console.error("Failed to refresh API keys:", err);
    }
  };

  const getExistingKey = (type: APIKeyType): APIKeyInfo | undefined =>
    apiKeys.find((k) => k.api_key_type === type);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">API Keys</h2>
        <p className="text-sm text-muted-foreground">
          Enter keys for Gemini, Tavily, and Firecrawl.
        </p>
      </div>
      <Separator />

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {isLoading ? (
        <div className="py-8 text-sm text-muted-foreground">Loading keys…</div>
      ) : (
        <div className="space-y-6">
          <div className="text-xs text-muted-foreground flex items-start gap-2">
            <Info className="h-4 w-4 mt-0.5" />
            Keys are encrypted and stored securely. You can update or remove
            them at any time.
          </div>

          <div className="space-y-6">
            <div>
              <div className="text-sm font-medium mb-2">Google Gemini</div>
              <APIKeyInput
                type={APIKeyType.GEMINI}
                existingKey={getExistingKey(APIKeyType.GEMINI)}
                onSave={refresh}
                onDelete={refresh}
              />
            </div>

            <div>
              <div className="text-sm font-medium mb-2">Tavily</div>
              <APIKeyInput
                type={APIKeyType.TAVILY}
                existingKey={getExistingKey(APIKeyType.TAVILY)}
                onSave={refresh}
                onDelete={refresh}
              />
            </div>

            <div>
              <div className="text-sm font-medium mb-2">Firecrawl</div>
              <APIKeyInput
                type={APIKeyType.FIRECRAWL}
                existingKey={getExistingKey(APIKeyType.FIRECRAWL)}
                onSave={refresh}
                onDelete={refresh}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
