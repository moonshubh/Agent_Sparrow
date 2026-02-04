import { supabase } from "@/services/supabase";
import { getAuthToken as getLocalToken } from "@/services/auth/local-auth";

const MEMORY_ASSET_PREFIX = "memory-asset://";
const MEMORY_API_BASE =
  process.env.NEXT_PUBLIC_MEMORY_API_BASE || "/api/v1/memory";

const signedUrlCache = new Map<
  string,
  {
    url: string;
    expiresAt: number;
  }
>();

const getAuthToken = async (): Promise<string | null> => {
  try {
    const session = await supabase.auth.getSession();
    const supaToken = session.data.session?.access_token || null;
    const localBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === "true";
    const localToken = localBypass ? getLocalToken() : null;
    return supaToken || localToken || null;
  } catch {
    return null;
  }
};

const stripAssetSuffix = (src: string): string => {
  if (!src) return src;
  const hashIndex = src.indexOf("#");
  const queryIndex = src.indexOf("?");
  const encodedHashIndex = src.indexOf("%23");
  let endIndex = src.length;
  if (hashIndex >= 0) endIndex = Math.min(endIndex, hashIndex);
  if (queryIndex >= 0) endIndex = Math.min(endIndex, queryIndex);
  if (encodedHashIndex >= 0) endIndex = Math.min(endIndex, encodedHashIndex);
  return src.slice(0, endIndex);
};

const parseMemoryAsset = (
  src: string,
): { bucket: string; path: string } | null => {
  if (!src) return null;
  const stripped = stripAssetSuffix(src);
  if (stripped.startsWith(MEMORY_ASSET_PREFIX)) {
    const trimmed = stripped.slice(MEMORY_ASSET_PREFIX.length);
    const slashIndex = trimmed.indexOf("/");
    if (slashIndex <= 0) return null;
    const bucket = trimmed.slice(0, slashIndex);
    const path = trimmed.slice(slashIndex + 1);
    if (!bucket || !path) return null;
    return { bucket, path };
  }

  const prefix = `${MEMORY_API_BASE}/assets/`;
  if (stripped.startsWith(prefix)) {
    const trimmed = stripped.slice(prefix.length);
    const slashIndex = trimmed.indexOf("/");
    if (slashIndex <= 0) return null;
    const bucket = trimmed.slice(0, slashIndex);
    const path = trimmed.slice(slashIndex + 1);
    if (!bucket || !path) return null;
    return { bucket, path };
  }

  return null;
};

const buildAssetApiUrl = (bucket: string, path: string): string =>
  `${MEMORY_API_BASE}/assets/${bucket}/${path}`;

const fetchAssetBlobUrl = async (
  assetUrl: string,
): Promise<{ url: string; revoke: () => void } | null> => {
  const token = await getAuthToken();
  const resp = await fetch(assetUrl, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!resp.ok) return null;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  return {
    url,
    revoke: () => URL.revokeObjectURL(url),
  };
};

const getSignedUrl = async (
  bucket: string,
  path: string,
): Promise<string | null> => {
  const cacheKey = `${bucket}/${path}`;
  const cached = signedUrlCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now() + 60_000) {
    return cached.url;
  }

  const token = await getAuthToken();
  const resp = await fetch(
    `${MEMORY_API_BASE}/assets/${bucket}/${path}/signed`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    },
  );
  if (!resp.ok) return null;
  const data = (await resp.json()) as {
    signed_url?: string;
    expires_at?: string;
  };
  if (!data?.signed_url) return null;
  const expiresAt = data.expires_at
    ? Date.parse(data.expires_at)
    : Date.now() + 15 * 60_000;
  signedUrlCache.set(cacheKey, {
    url: data.signed_url,
    expiresAt: Number.isNaN(expiresAt) ? Date.now() + 15 * 60_000 : expiresAt,
  });
  return data.signed_url;
};

export type ResolvedAsset = {
  src: string;
  revoke?: () => void;
  original: string;
};

export const resolveMemoryAssetUrl = async (
  src: string,
): Promise<ResolvedAsset | null> => {
  if (!src) return null;
  const asset = parseMemoryAsset(src);
  if (!asset) {
    return { src, original: src };
  }

  const assetUrl = buildAssetApiUrl(asset.bucket, asset.path);

  try {
    const blob = await fetchAssetBlobUrl(assetUrl);
    if (blob) {
      return { src: blob.url, revoke: blob.revoke, original: src };
    }
  } catch (error) {
    if (process.env.NODE_ENV !== "production") {
      console.warn("[memory-asset] Blob fetch failed", error);
    }
  }

  const signed = await getSignedUrl(asset.bucket, asset.path);
  if (signed) {
    return { src: signed, original: src };
  }

  if (process.env.NODE_ENV !== "production") {
    console.warn("[memory-asset] Signed URL fetch failed", assetUrl);
  }

  return { src: assetUrl, original: src };
};
