"use client";

import * as HoverCard from "@radix-ui/react-hover-card";
import {
  AlertCircle,
  ExternalLink,
  Globe2,
  ImageOff,
  Loader2,
} from "lucide-react";
import React, { useCallback, useMemo, useState } from "react";

import { metadataAPI, type LinkPreviewResponse } from "@/services/api/endpoints/metadata";
import { cn } from "@/shared/lib/utils";

interface LinkPreviewProps {
  url?: string | null;
  children: React.ReactElement;
  className?: string;
  preload?: boolean;
}

type TriggerElementProps = {
  onMouseEnter?: (event: React.MouseEvent<Element>) => void;
  onFocus?: (event: React.FocusEvent<Element>) => void;
  onTouchStart?: (event: React.TouchEvent<Element>) => void;
  [key: string]: unknown;
};

type PreviewCacheEntry = {
  preview: LinkPreviewResponse;
  expiresAt: number;
};

const PREVIEW_CACHE = new Map<string, PreviewCacheEntry>();
const PREVIEW_INFLIGHT = new Map<string, Promise<LinkPreviewResponse>>();
const PREVIEW_WAITERS: Array<() => void> = [];
let PREVIEW_ACTIVE_REQUESTS = 0;

const FALLBACK_DESCRIPTION = "Preview unavailable. Open the link to view details.";
const DEFAULT_OPEN_DELAY_MS = 90;
const DEFAULT_CLOSE_DELAY_MS = 90;
const PRELOAD_DELAY_MS = 80;
const PRELOAD_IDLE_TIMEOUT_MS = 700;
const PREVIEW_CACHE_TTL_MS = 30 * 60 * 1000;
const PREVIEW_CACHE_MAX_ENTRIES = 2000;
const PREVIEW_NETWORK_CONCURRENCY = 8;

const normalizeExternalUrl = (value?: string | null): string | null => {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
    return null;
  } catch {
    return null;
  }
};

const toSiteName = (url: string): string => {
  try {
    return (new URL(url).hostname || url).replace(/^www\./i, "");
  } catch {
    return url;
  }
};

const buildFallbackPreview = (
  url: string,
  retryable: boolean,
): LinkPreviewResponse => ({
  url,
  resolvedUrl: url,
  title: null,
  description: FALLBACK_DESCRIPTION,
  siteName: toSiteName(url),
  imageUrl: null,
  screenshotUrl: null,
  mode: "fallback",
  status: "degraded",
  retryable,
});

const prunePreviewCache = (): void => {
  const now = Date.now();
  for (const [key, entry] of PREVIEW_CACHE.entries()) {
    if (entry.expiresAt <= now) {
      PREVIEW_CACHE.delete(key);
    }
  }
  while (PREVIEW_CACHE.size > PREVIEW_CACHE_MAX_ENTRIES) {
    const oldestKey = PREVIEW_CACHE.keys().next().value as string | undefined;
    if (!oldestKey) break;
    PREVIEW_CACHE.delete(oldestKey);
  }
};

const getCachedPreview = (url: string): LinkPreviewResponse | null => {
  const entry = PREVIEW_CACHE.get(url);
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) {
    PREVIEW_CACHE.delete(url);
    return null;
  }
  return entry.preview;
};

const setCachedPreview = (url: string, preview: LinkPreviewResponse): void => {
  PREVIEW_CACHE.delete(url);
  PREVIEW_CACHE.set(url, {
    preview,
    expiresAt: Date.now() + PREVIEW_CACHE_TTL_MS,
  });
  prunePreviewCache();
};

const acquirePreviewRequestSlot = async (): Promise<void> => {
  if (PREVIEW_ACTIVE_REQUESTS < PREVIEW_NETWORK_CONCURRENCY) {
    PREVIEW_ACTIVE_REQUESTS += 1;
    return;
  }
  await new Promise<void>((resolve) => {
    PREVIEW_WAITERS.push(resolve);
  });
  PREVIEW_ACTIVE_REQUESTS += 1;
};

const releasePreviewRequestSlot = (): void => {
  PREVIEW_ACTIVE_REQUESTS = Math.max(0, PREVIEW_ACTIVE_REQUESTS - 1);
  const next = PREVIEW_WAITERS.shift();
  if (next) next();
};

const requestPreview = async (url: string): Promise<LinkPreviewResponse> => {
  const cached = getCachedPreview(url);
  if (cached) return cached;

  const inflight = PREVIEW_INFLIGHT.get(url);
  if (inflight) return inflight;

  const request = (async () => {
    await acquirePreviewRequestSlot();
    try {
      const response = await metadataAPI.getLinkPreview(url);
      const normalized: LinkPreviewResponse = {
        ...response,
        title: response.title ?? null,
        description: response.description ?? null,
        siteName: response.siteName ?? toSiteName(response.resolvedUrl || url),
        imageUrl: response.imageUrl ?? null,
        screenshotUrl: response.screenshotUrl ?? null,
      };
      setCachedPreview(url, normalized);
      return normalized;
    } catch (error) {
      console.warn("[LinkPreview] Failed to fetch preview", error);
      const fallback = buildFallbackPreview(url, true);
      setCachedPreview(url, fallback);
      return fallback;
    } finally {
      releasePreviewRequestSlot();
      PREVIEW_INFLIGHT.delete(url);
    }
  })();

  PREVIEW_INFLIGHT.set(url, request);
  return request;
};

const PreviewCard = ({ preview }: { preview: LinkPreviewResponse }) => {
  const imageUrl = preview.screenshotUrl || preview.imageUrl;
  const [imageFailed, setImageFailed] = useState(false);

  return (
    <div className="w-[320px] rounded-xl border border-border bg-card shadow-xl overflow-hidden">
      {imageUrl && !imageFailed ? (
        <img
          src={imageUrl}
          alt={preview.title || preview.siteName || "Preview image"}
          className="block h-36 w-full object-cover bg-secondary/20"
          loading="lazy"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className="h-24 w-full bg-secondary/30 border-b border-border/60 flex items-center justify-center gap-2 text-muted-foreground text-xs">
          <ImageOff className="h-4 w-4" />
          No preview image
        </div>
      )}

      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Globe2 className="h-3.5 w-3.5" />
          <span className="truncate">{preview.siteName || toSiteName(preview.url)}</span>
        </div>

        <p className="text-sm font-medium text-foreground line-clamp-2">
          {preview.title || "Open external link"}
        </p>
        <p className="text-xs text-muted-foreground line-clamp-3">
          {preview.description || FALLBACK_DESCRIPTION}
        </p>

        {preview.status === "degraded" && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-400 flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">
              {preview.retryable
                ? "Preview degraded. You can retry later."
                : "Preview degraded for this link."}
            </span>
          </div>
        )}

        <a
          href={preview.resolvedUrl || preview.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 underline underline-offset-4"
        >
          Open link
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    </div>
  );
};

export function LinkPreview({
  url,
  children,
  className,
  preload = false,
}: LinkPreviewProps) {
  const normalizedUrl = useMemo(() => normalizeExternalUrl(url), [url]);
  const [preview, setPreview] = useState<LinkPreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const ensurePreview = useCallback(async () => {
    if (!normalizedUrl) return;
    if (preview) return;

    const cached = getCachedPreview(normalizedUrl);
    if (cached) {
      setPreview(cached);
      return;
    }

    setIsLoading(true);
    try {
      const next = await requestPreview(normalizedUrl);
      setPreview(next);
    } finally {
      setIsLoading(false);
    }
  }, [normalizedUrl, preview]);

  const triggerPrefetch = useCallback(() => {
    if (!normalizedUrl) return;
    // Start request as soon as user intent is detected (hover/focus/touch).
    void requestPreview(normalizedUrl).then((next) => {
      setPreview((current) => current ?? next);
    });
  }, [normalizedUrl]);

  const trigger = useMemo(() => {
    const typedChild = children as React.ReactElement<TriggerElementProps>;
    const childProps = typedChild.props;

    return React.cloneElement(typedChild, {
      onMouseEnter: (event: React.MouseEvent<Element>) => {
        childProps.onMouseEnter?.(event);
        triggerPrefetch();
      },
      onFocus: (event: React.FocusEvent<Element>) => {
        childProps.onFocus?.(event);
        triggerPrefetch();
      },
      onTouchStart: (event: React.TouchEvent<Element>) => {
        childProps.onTouchStart?.(event);
        triggerPrefetch();
      },
    });
  }, [children, triggerPrefetch]);

  React.useEffect(() => {
    if (!normalizedUrl || !preload) return;

    let cancelled = false;
    let idleId: number | null = null;
    let timeoutId: number | null = null;

    const startPrefetch = () => {
      if (cancelled) return;
      const cached = getCachedPreview(normalizedUrl);
      if (cached) {
        return;
      }
      void requestPreview(normalizedUrl);
    };

    if (
      typeof window !== "undefined" &&
      "requestIdleCallback" in window &&
      typeof (window as any).requestIdleCallback === "function"
    ) {
      idleId = (window as any).requestIdleCallback(startPrefetch, {
        timeout: PRELOAD_IDLE_TIMEOUT_MS,
      }) as number;
    } else if (typeof window !== "undefined") {
      timeoutId = window.setTimeout(startPrefetch, PRELOAD_DELAY_MS);
    }

    return () => {
      cancelled = true;
      if (
        idleId !== null &&
        typeof window !== "undefined" &&
        "cancelIdleCallback" in window &&
        typeof (window as any).cancelIdleCallback === "function"
      ) {
        (window as any).cancelIdleCallback(idleId);
      }
      if (timeoutId !== null && typeof window !== "undefined") {
        window.clearTimeout(timeoutId);
      }
    };
  }, [normalizedUrl, preload]);

  if (!normalizedUrl) {
    return children;
  }

  return (
    <HoverCard.Root
      openDelay={DEFAULT_OPEN_DELAY_MS}
      closeDelay={DEFAULT_CLOSE_DELAY_MS}
      onOpenChange={(open) => {
        if (open) {
          void ensurePreview();
        }
      }}
    >
      <HoverCard.Trigger asChild>{trigger}</HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          align="start"
          sideOffset={8}
          className={cn("z-[1200] outline-none", className)}
        >
          {isLoading ? (
            <div className="w-[320px] rounded-xl border border-border bg-card shadow-xl p-3 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading preview...
            </div>
          ) : preview ? (
            <PreviewCard preview={preview} />
          ) : (
            <PreviewCard preview={buildFallbackPreview(normalizedUrl, true)} />
          )}
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
