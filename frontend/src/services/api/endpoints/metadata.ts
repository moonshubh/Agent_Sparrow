import { apiClient } from "@/services/api/api-client";

export type LinkPreviewMode = "screenshot" | "og" | "fallback";
export type LinkPreviewStatus = "ok" | "degraded";

export interface LinkPreviewResponse {
  url: string;
  resolvedUrl: string;
  title: string | null;
  description: string | null;
  siteName: string | null;
  imageUrl: string | null;
  screenshotUrl: string | null;
  mode: LinkPreviewMode;
  status: LinkPreviewStatus;
  retryable: boolean;
}

export const metadataAPI = {
  async getLinkPreview(url: string): Promise<LinkPreviewResponse> {
    const params = new URLSearchParams({ url });
    return apiClient.get<LinkPreviewResponse>(
      `/api/v1/metadata/link-preview?${params.toString()}`,
    );
  },
};

