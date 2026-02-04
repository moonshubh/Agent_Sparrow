"use client";

import Image from "next/image";
import React, { useEffect, useState } from "react";
import { cn } from "@/shared/lib/utils";

interface EnhancedAnimatedLogoProps {
  className?: string;
  triggerAdvance?: number;
  loop?: boolean;
}

const KEYFRAMES = [
  "/feedme-keyframes/Keyframe_1.png",
  "/feedme-keyframes/Keyframe_2.png",
  "/feedme-keyframes/Keyframe_3.png",
  "/feedme-keyframes/Keyframe_4.png",
  "/feedme-keyframes/Keyframe_5.png",
  "/feedme-keyframes/Keyframe_6.png",
  "/feedme-keyframes/Keyframe_7.png",
  "/feedme-keyframes/Keyframe_8.png",
] as const;

export default function EnhancedAnimatedLogo({
  className = "",
  triggerAdvance = 0,
  loop = true,
}: EnhancedAnimatedLogoProps) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const preload = async () => {
      try {
        await Promise.all(
          KEYFRAMES.map(
            (src) =>
              new Promise<void>((resolve, reject) => {
                const img = new window.Image();
                img.onload = () => resolve();
                img.onerror = reject;
                img.src = src;
              }),
          ),
        );
      } catch (error) {
        console.warn("Failed to preload FeedMe frames", error);
      } finally {
        if (!cancelled) {
          setHasLoaded(true);
        }
      }
    };

    preload().catch(() => setHasLoaded(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (triggerAdvance === 0) return;

    // Cycle through all frames sequentially when triggered
    // Each trigger advances to the next frame, cycling through all 8 frames
    setCurrentFrame((prev) => {
      const next = prev + 1;
      if (next >= KEYFRAMES.length) {
        return loop ? 0 : KEYFRAMES.length - 1;
      }
      return next;
    });
  }, [triggerAdvance, loop]);

  const frameSrc = hasLoaded ? KEYFRAMES[currentFrame] : KEYFRAMES[0];

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      <Image
        src={frameSrc}
        alt="FeedMe"
        fill
        sizes="(max-width: 640px) 280px, (max-width: 1024px) 320px, 400px"
        className="object-contain"
        priority
      />
    </div>
  );
}
