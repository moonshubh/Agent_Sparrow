"use client";

import React, { useState, useEffect } from "react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";
import styles from "./CenterHero.module.css";

type AnimatedCenterHeroProps = {
  className?: string;
  animationDuration?: number;
  loop?: boolean;
  autoPlay?: boolean;
};

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

export default function AnimatedCenterHero({
  className = "",
  animationDuration = 2400,
  loop = true,
  autoPlay = true,
}: AnimatedCenterHeroProps) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(autoPlay);
  const [imagesLoaded, setImagesLoaded] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  const frameDuration = animationDuration / KEYFRAMES.length;

  useEffect(() => {
    const loadImages = async () => {
      const promises = KEYFRAMES.map((src) => {
        return new Promise<void>((resolve, reject) => {
          const img = new window.Image();
          img.onload = () => resolve();
          img.onerror = reject;
          img.src = src;
        });
      });

      try {
        await Promise.all(promises);
        setImagesLoaded(true);
      } catch (error) {
        console.error("Error loading keyframe images:", error);
        setImagesLoaded(true);
      }
    };

    loadImages();
  }, []);

  useEffect(() => {
    if (!isPlaying || shouldReduceMotion || !imagesLoaded) return;

    const interval = setInterval(() => {
      setCurrentFrame((prev) => {
        const nextFrame = prev + 1;

        if (nextFrame >= KEYFRAMES.length) {
          if (loop) {
            return 0;
          } else {
            setIsPlaying(false);
            return prev;
          }
        }

        return nextFrame;
      });
    }, frameDuration);

    return () => clearInterval(interval);
  }, [isPlaying, frameDuration, loop, shouldReduceMotion, imagesLoaded]);

  const animate = shouldReduceMotion
    ? { opacity: 1, scale: 1 }
    : {
        opacity: 1,
        scale: 1,
        y: [0, -8, 0],
        transition: {
          duration: 3,
          ease: "easeInOut" as const,
          repeat: Infinity,
        },
      };

  if (!imagesLoaded) {
    return (
      <motion.div
        className={`${styles.heroWrap} ${className}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <div className={styles.ring}>
          <span className={styles.sweep}></span>
          <div className={styles.imgWrap}>
            <div className="flex items-center justify-center w-full h-full">
              <div className="animate-pulse text-white/50">Loading...</div>
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  if (shouldReduceMotion) {
    return (
      <motion.div
        className={`${styles.heroWrap} ${className}`}
        initial={{ opacity: 0, scale: 1.05 }}
        animate={animate}
      >
        <div className={styles.ring}>
          <span className={styles.sweep}></span>
          <div className={styles.imgWrap}>
            <img src={KEYFRAMES[0]} alt="FeedMe" />
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className={`${styles.heroWrap} ${className}`}
      initial={{ opacity: 0, scale: 1.05 }}
      animate={animate}
    >
      <div className={styles.ring}>
        <span className={styles.sweep}></span>
        <div className={styles.imgWrap}>
          <AnimatePresence mode="sync">
            <motion.img
              key={currentFrame}
              src={KEYFRAMES[currentFrame]}
              alt="FeedMe"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              transition={{
                duration: frameDuration / 2000,
                ease: "easeInOut",
              }}
              style={{
                position: "absolute",
                width: "100%",
                height: "100%",
                objectFit: "contain",
              }}
            />
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
