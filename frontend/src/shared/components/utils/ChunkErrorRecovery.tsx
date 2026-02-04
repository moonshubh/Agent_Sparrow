"use client";

import { useEffect } from "react";

export function ChunkErrorRecovery() {
  useEffect(() => {
    const handler = (e: any) => {
      const msg = (e?.reason?.message || e?.message || "").toString();
      const name = (e?.reason?.name || e?.name || "").toString();
      const isChunkError =
        /ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module/i.test(
          msg + " " + name,
        );
      if (isChunkError) {
        // Attempt a hard reload to fetch fresh chunks
        try {
          console.warn(
            "Detected chunk load error. Reloading page to recover...",
          );
        } catch {}
        window.location.reload();
      }
    };

    window.addEventListener("unhandledrejection", handler);
    window.addEventListener("error", handler);
    return () => {
      window.removeEventListener("unhandledrejection", handler);
      window.removeEventListener("error", handler);
    };
  }, []);

  return null;
}
