"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import Image from "next/image";

interface AnimatedFeedMeLogoProps {
  className?: string;
  animationDuration?: number;
  loop?: boolean;
  autoPlay?: boolean;
  onAnimationComplete?: () => void;
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
];

export default function AnimatedFeedMeLogo({
  className = "",
  animationDuration = 2000,
  loop = true,
  autoPlay = true,
  onAnimationComplete,
}: AnimatedFeedMeLogoProps) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(autoPlay);
  const shouldReduceMotion = useReducedMotion();

  const frameDuration = animationDuration / KEYFRAMES.length;

  useEffect(() => {
    if (!isPlaying || shouldReduceMotion) return;

    const interval = setInterval(() => {
      setCurrentFrame((prev) => {
        const nextFrame = prev + 1;

        if (nextFrame >= KEYFRAMES.length) {
          if (loop) {
            return 0;
          } else {
            setIsPlaying(false);
            onAnimationComplete?.();
            return prev;
          }
        }

        return nextFrame;
      });
    }, frameDuration);

    return () => clearInterval(interval);
  }, [isPlaying, frameDuration, loop, onAnimationComplete, shouldReduceMotion]);

  useEffect(() => {
    KEYFRAMES.forEach((src) => {
      const img = new window.Image();
      img.src = src;
    });
  }, []);

  if (shouldReduceMotion) {
    return (
      <div className={`relative ${className}`}>
        <Image
          src={KEYFRAMES[0]}
          alt="FeedMe Logo"
          fill
          className="object-contain"
          priority
        />
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <AnimatePresence mode="wait">
        <motion.div
          key={currentFrame}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{
            duration: frameDuration / 2000,
            ease: "easeInOut",
          }}
          className="absolute inset-0"
        >
          <Image
            src={KEYFRAMES[currentFrame]}
            alt={`FeedMe Logo Frame ${currentFrame + 1}`}
            fill
            className="object-contain"
            priority={currentFrame === 0}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
