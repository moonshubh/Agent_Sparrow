'use client';

import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { supabase } from '@/services/supabase';
import { getAuthToken as getLocalToken } from '@/services/auth/local-auth';

const MEMORY_ASSET_PREFIX = 'memory-asset://';
const MEMORY_API_BASE =
  process.env.NEXT_PUBLIC_MEMORY_API_BASE || '/api/v1/memory';

const buildAssetUrl = (src: string): string | null => {
  if (!src) return null;
  if (src.startsWith(MEMORY_ASSET_PREFIX)) {
    const trimmed = src.slice(MEMORY_ASSET_PREFIX.length);
    const slashIndex = trimmed.indexOf('/');
    if (slashIndex <= 0) return null;
    const bucket = trimmed.slice(0, slashIndex);
    const path = trimmed.slice(slashIndex + 1);
    if (!bucket || !path) return null;
    return `${MEMORY_API_BASE}/assets/${bucket}/${path}`;
  }
  if (src.startsWith(`${MEMORY_API_BASE}/assets/`)) {
    return src;
  }
  return null;
};

const getAuthToken = async (): Promise<string | null> => {
  try {
    const session = await supabase.auth.getSession();
    const supaToken = session.data.session?.access_token || null;
    const localBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true';
    const localToken = localBypass ? getLocalToken() : null;
    return supaToken || localToken || null;
  } catch {
    return null;
  }
};

const AuthenticatedImage = ({
  src,
  alt,
}: {
  src?: string;
  alt?: string;
}) => {
  const assetUrl = useMemo(() => (src ? buildAssetUrl(src) : null), [src]);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!assetUrl) {
      setBlobUrl(null);
      return;
    }

    let active = true;
    let objectUrl: string | null = null;
    const controller = new AbortController();

    const fetchAsset = async () => {
      const token = await getAuthToken();
      const resp = await fetch(assetUrl, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        signal: controller.signal,
      });
      if (!resp.ok) {
        throw new Error(`Asset fetch failed (${resp.status})`);
      }
      const blob = await resp.blob();
      const newObjectUrl = URL.createObjectURL(blob);
      if (active) {
        objectUrl = newObjectUrl;
        setBlobUrl(newObjectUrl);
      } else {
        URL.revokeObjectURL(newObjectUrl);
      }
    };

    fetchAsset().catch((err) => {
      if (!active) return;
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setBlobUrl(null);
    });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [assetUrl]);

  const finalSrc = blobUrl || src || '';
  return <img src={finalSrc} alt={alt || ''} />;
};

export default function MemoryMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        img: ({ src, alt }) => <AuthenticatedImage src={src} alt={alt} />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
