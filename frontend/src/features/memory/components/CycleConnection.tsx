"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";

export function CycleConnection({
  points,
}: {
  points: [number, number, number][];
}) {
  const lineRef = useRef<React.ElementRef<typeof Line> | null>(null);

  useFrame((state) => {
    const line = lineRef.current as unknown as {
      material?: { dashOffset?: number };
    } | null;
    if (!line?.material) return;
    if (typeof line.material.dashOffset !== "number") return;
    line.material.dashOffset = -state.clock.elapsedTime * 0.8;
  });

  return (
    <Line
      ref={lineRef}
      points={points}
      color="#00bcd4"
      lineWidth={1}
      dashed
      dashSize={0.45}
      gapSize={0.35}
      transparent
      opacity={0.6}
    />
  );
}
