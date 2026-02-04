"use client";

import React, { useEffect, useRef } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  type MotionValue,
} from "framer-motion";
import { cn } from "@/shared/lib/utils";

type GlowingEffectProps = {
  className?: string;
  spread?: number;
  glow?: boolean;
  disabled?: boolean;
  proximity?: number;
  inactiveZone?: number;
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

export function GlowingEffect({
  className,
  spread = 220,
  glow = true,
  disabled = false,
  proximity = 140,
  inactiveZone = 0,
}: GlowingEffectProps) {
  const effectRef = useRef<HTMLDivElement | null>(null);
  const offsetX = useMotionValue(0);
  const offsetY = useMotionValue(0);
  const opacity = useSpring(inactiveZone, { stiffness: 260, damping: 32 });
  const scale = useSpring(0.6, { stiffness: 220, damping: 30 });

  useEffect(() => {
    if (disabled) {
      opacity.set(0);
      return;
    }

    const parent = effectRef.current?.parentElement as HTMLElement | null;
    if (!parent) return;

    if (getComputedStyle(parent).position === "static") {
      parent.style.position = "relative";
    }

    const updateFromPointer = (event: PointerEvent) => {
      const rect = parent.getBoundingClientRect();
      const localX = event.clientX - rect.left;
      const localY = event.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const dx = localX - centerX;
      const dy = localY - centerY;

      offsetX.set(dx);
      offsetY.set(dy);

      const distance = Math.hypot(dx, dy);
      const maxDistance = Math.max(proximity, 1);
      const nextOpacity = clamp(1 - distance / maxDistance, inactiveZone, 1);

      opacity.set(nextOpacity);
      scale.set(0.7 + (1 - distance / maxDistance) * 0.4);
    };

    const fadeOut = () => {
      opacity.set(inactiveZone);
      scale.set(0.6);
    };

    parent.addEventListener("pointermove", updateFromPointer);
    parent.addEventListener("pointerenter", updateFromPointer);
    parent.addEventListener("pointerleave", fadeOut);

    return () => {
      parent.removeEventListener("pointermove", updateFromPointer);
      parent.removeEventListener("pointerenter", updateFromPointer);
      parent.removeEventListener("pointerleave", fadeOut);
    };
  }, [disabled, inactiveZone, opacity, offsetX, offsetY, proximity, scale]);

  const sizeStyle: Partial<
    Record<"width" | "height", MotionValue<number> | number>
  > = {
    width: spread,
    height: spread,
  };

  return (
    <div
      ref={effectRef}
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        className,
      )}
      aria-hidden="true"
    >
      <motion.div
        className={cn(
          "pointer-events-none rounded-full bg-[radial-gradient(circle,_rgba(255,255,255,0.45),_rgba(255,255,255,0.12)_55%,_rgba(255,255,255,0)_75%)] blur-3xl transition-[box-shadow] duration-300",
          glow && "shadow-[0_0_56px_rgba(148,190,255,0.4)]",
        )}
        style={{
          translateX: offsetX,
          translateY: offsetY,
          opacity,
          scale,
          ...sizeStyle,
        }}
      />
    </div>
  );
}

export default GlowingEffect;
