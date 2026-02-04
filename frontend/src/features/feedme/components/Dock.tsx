"use client";

import Image from "next/image";
import React, {
  createContext,
  forwardRef,
  useContext,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useSpring,
  useTransform,
  type MotionValue,
  type SpringOptions,
} from "framer-motion";
import { cn } from "@/shared/lib/utils";

type Orientation = "horizontal" | "vertical";

type DockContextValue = {
  mouseX: MotionValue<number>;
  hoveredId: string | null;
  setHoveredId: React.Dispatch<React.SetStateAction<string | null>>;
  baseSize: number;
  magnification: number;
  distance: number;
  springConfig: SpringOptions;
  orientation: Orientation;
};

const DockContext = createContext<DockContextValue | null>(null);

export function useDock() {
  const context = useContext(DockContext);
  if (!context) {
    throw new Error("useDock must be used within a <Dock> component");
  }
  return context;
}

type DockRootProps = {
  children: ReactNode;
  className?: string;
  panelClassName?: string;
  baseSize?: number;
  magnification?: number;
  distance?: number;
  springConfig?: SpringOptions;
  orientation?: Orientation;
};

const DEFAULT_SPRING: SpringOptions = {
  stiffness: 340,
  damping: 24,
  mass: 0.3,
};

const PANEL_STYLES =
  "relative flex items-end gap-10 rounded-full ring-1 ring-white/5 border border-white/8 bg-[linear-gradient(140deg,rgba(21,30,46,0.22),rgba(21,30,46,0.12))] px-8 py-3 shadow-[0_18px_60px_rgba(15,23,42,0.35)] backdrop-blur-xl";

const INNER_STYLES = "flex items-end gap-10";

const GlassGlow = () => (
  <div
    aria-hidden="true"
    className="pointer-events-none absolute inset-0 rounded-full bg-[radial-gradient(120%_140%_at_30%_0%,rgba(255,255,255,0.18),rgba(255,255,255,0.06)40%,transparent_70%)] opacity-60"
  />
);

const PanelOutline = () => (
  <div
    aria-hidden="true"
    className="pointer-events-none absolute inset-[0.75px] rounded-full border border-white/10"
  />
);

function DockRoot({
  children,
  className,
  panelClassName,
  baseSize = 76,
  magnification = 1.55,
  distance = 180,
  springConfig = DEFAULT_SPRING,
  orientation = "horizontal",
}: DockRootProps) {
  const mouseX = useMotionValue(Infinity);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const contextValue = useMemo<DockContextValue>(
    () => ({
      mouseX,
      hoveredId,
      setHoveredId,
      baseSize,
      magnification,
      distance,
      springConfig,
      orientation,
    }),
    [
      hoveredId,
      baseSize,
      magnification,
      distance,
      springConfig,
      orientation,
      mouseX,
    ],
  );

  return (
    <DockContext.Provider value={contextValue}>
      <motion.div
        onMouseMove={(event) => mouseX.set(event.clientX)}
        onMouseLeave={() => {
          mouseX.set(Infinity);
          setHoveredId(null);
        }}
        className={cn(
          "group/dock relative flex w-full justify-center",
          orientation === "horizontal" ? "py-4" : "py-4",
          className,
        )}
        role="toolbar"
        aria-label="FeedMe quick actions"
      >
        <div className={cn(PANEL_STYLES, panelClassName)}>
          <GlassGlow />
          <PanelOutline />
          <div
            className={cn(
              INNER_STYLES,
              orientation === "vertical" &&
                "flex-col items-center justify-center gap-4",
            )}
          >
            {children}
          </div>
        </div>
      </motion.div>
    </DockContext.Provider>
  );
}

type DockCardProps = {
  id: string;
  label: string;
  onClick?: () => void;
  className?: string;
  children: ReactNode;
};

const tooltipVariants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 4 },
};

const DockCard = forwardRef<HTMLButtonElement, DockCardProps>(
  ({ id, label, onClick, className, children }, forwardedRef) => {
    const {
      mouseX,
      hoveredId,
      setHoveredId,
      baseSize,
      magnification,
      distance,
      springConfig,
      orientation,
    } = useDock();

    const localRef = useRef<HTMLButtonElement>(null);

    useImperativeHandle(
      forwardedRef,
      () => localRef.current as HTMLButtonElement,
      [],
    );

    const distanceFromMouse = useTransform(mouseX, (value) => {
      const element = localRef.current;
      if (!element) return distance * 2;
      const bounds = element.getBoundingClientRect();
      const center = bounds.x + bounds.width / 2;
      return value - center;
    });

    const targetSize = useTransform(
      distanceFromMouse,
      [-distance, 0, distance],
      [baseSize, baseSize * magnification, baseSize],
    );
    const animatedSize = useSpring(targetSize, springConfig);
    const translateY = useTransform(animatedSize, (size) =>
      orientation === "horizontal" ? -Math.max(0, size - baseSize) * 0.42 : 0,
    );
    const isActive = hoveredId === id;

    return (
      <motion.button
        ref={localRef}
        type="button"
        className={cn(
          "dock-card group relative flex h-full w-full min-w-[72px] items-center justify-center text-white transition-transform duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-black",
          className,
        )}
        style={{
          width: animatedSize,
          height: animatedSize,
          y: translateY,
        }}
        whileTap={{ scale: 0.98 }}
        onClick={onClick}
        onMouseEnter={() => setHoveredId(id)}
        onMouseLeave={() => setHoveredId(null)}
        onFocus={() => setHoveredId(id)}
        onBlur={() =>
          setHoveredId((current) => (current === id ? null : current))
        }
        aria-label={label}
      >
        <div className="relative flex size-full items-center justify-center overflow-hidden rounded-full">
          {children}
        </div>

        <AnimatePresence>
          {isActive && (
            <motion.span
              {...tooltipVariants}
              className="pointer-events-none absolute left-1/2 bottom-[calc(100%+16px)] z-20 w-max -translate-x-1/2 rounded-full border border-white/10 bg-black/90 px-4 py-1 text-sm font-medium text-white shadow-[0_12px_32px_rgba(0,0,0,0.35)]"
              style={{ x: "-50%" }}
            >
              {label}
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
    );
  },
);
DockCard.displayName = "DockCard";

type CardProps = {
  src?: string;
  alt?: string;
  children?: ReactNode;
  className?: string;
};

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ src, alt, children, className }, forwardedRef) => (
    <div
      ref={forwardedRef}
      className={cn(
        "relative flex size-full items-center justify-center overflow-visible",
        className,
      )}
    >
      {src ? (
        <Image
          src={src}
          alt={alt ?? ""}
          width={160}
          height={160}
          className="h-full w-full object-contain"
        />
      ) : null}
      {children ? (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
          {children}
        </span>
      ) : null}
    </div>
  ),
);
Card.displayName = "Card";

type DockDividerProps = {
  className?: string;
};

function DockDivider({ className }: DockDividerProps) {
  const { orientation, baseSize } = useDock();
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative flex items-center justify-center",
        orientation === "horizontal"
          ? "h-[70%] w-[1.5px]"
          : "h-[1.5px] w-[70%]",
        className,
      )}
      style={{
        margin:
          orientation === "horizontal"
            ? `0 ${Math.max(4, baseSize * 0.08)}px`
            : `${Math.max(6, baseSize * 0.08)}px 0`,
      }}
    >
      <span
        className={cn(
          "size-full rounded-full bg-gradient-to-b from-white/40 via-white/10 to-white/35 opacity-80",
          orientation === "vertical" && "bg-gradient-to-r",
        )}
      />
    </div>
  );
}

const Dock = Object.assign(DockRoot, {
  Card,
  DockCard,
  DockDivider,
});

export { Card, DockCard, DockDivider };

export default Dock;
