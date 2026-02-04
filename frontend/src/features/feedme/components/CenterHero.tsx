"use client";

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import styles from "./CenterHero.module.css";

type CenterHeroProps = {
  src: string;
  className?: string;
};

export default function CenterHero({ src, className = "" }: CenterHeroProps) {
  const reduced = useReducedMotion();
  const animate = reduced
    ? { opacity: 1, scale: 1 }
    : {
        opacity: 1,
        scale: 1,
        y: [0, -6, 0],
        transition: { duration: 3, ease: "easeInOut" as const },
      };

  return (
    <motion.div
      className={`${styles.heroWrap} ${className}`}
      initial={{ opacity: 0, scale: 1.05 }}
      animate={animate}
    >
      <div className={styles.ring}>
        <span className={styles.sweep}></span>
        <div className={styles.imgWrap}>
          <img src={src} alt="FeedMe" />
        </div>
      </div>
    </motion.div>
  );
}
