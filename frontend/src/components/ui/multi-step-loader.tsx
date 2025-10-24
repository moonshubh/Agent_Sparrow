"use client";
import { cn } from "@/shared/lib/utils/index";
import { AnimatePresence, motion } from "motion/react";
import { useState, useEffect } from "react";

const CheckIcon = ({ className }: { className?: string }) => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={cn("w-6 h-6 ", className)}
    >
      <path d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
};

const CheckFilled = ({ className }: { className?: string }) => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={cn("w-6 h-6 ", className)}
    >
      <path
        fillRule="evenodd"
        d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm13.36-1.814a.75.75 0 1 0-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 0 0-1.06 1.06l2.25 2.25a.75.75 0 0 0 1.14-.094l3.75-5.25Z"
        clipRule="evenodd"
      />
    </svg>
  );
};

type LoadingState = {
  text: string;
};

const LoaderCore = ({
  loadingStates,
  value = 0,
  compact = false,
  alignLeft = false,
}: {
  loadingStates: LoadingState[];
  value?: number;
  compact?: boolean;
  alignLeft?: boolean;
}) => {
  return (
    <div className={cn(
      "flex relative justify-start flex-col",
      alignLeft ? "mx-0" : "mx-auto",
      compact ? "mt-0 w-full" : "mt-40 max-w-xl",
    )}>
      {loadingStates.map((loadingState, index) => {
        const distance = Math.abs(index - value);
        const opacity = Math.max(1 - distance * 0.2, 0); // Minimum opacity is 0, keep it 0.2 if you're sane.

        return (
          <motion.div
            key={index}
            className={cn("text-left flex gap-2 mb-4")}
            initial={{ opacity: 0, y: -(value * 40) }}
            animate={{ opacity: opacity, y: -(value * 40) }}
            transition={{ duration: 0.5 }}
          >
            <div>
              {index > value && (
                <CheckIcon className="text-black dark:text-white" />
              )}
              {index <= value && (
                <motion.div
                  animate={value === index ? { scale: [1, 1.05, 1] } : undefined}
                  transition={value === index ? { duration: 1.0, repeat: Infinity, ease: "easeInOut" } : undefined}
                >
                  <CheckFilled
                    className={cn(
                      "text-black dark:text-white",
                      value === index &&
                        "text-black dark:text-lime-500 opacity-100"
                    )}
                  />
                </motion.div>
              )}
            </div>
            {value === index ? (
              <motion.span
                className={cn(
                  "text-black dark:text-white",
                  "text-black dark:text-lime-500 opacity-100"
                )}
                animate={{ opacity: [0.6, 1, 0.6] }}
                transition={{ duration: 1.2, repeat: Infinity }}
              >
                {loadingState.text}
              </motion.span>
            ) : (
              <span className={cn("text-black dark:text-white")}>{loadingState.text}</span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
};

export const MultiStepLoader = ({
  loadingStates,
  loading,
  duration = 2000,
  loop = true,
  activeIndex,
  variant = "overlay",
  className,
}: {
  loadingStates: LoadingState[];
  loading?: boolean;
  duration?: number;
  loop?: boolean;
  activeIndex?: number;
  variant?: "overlay" | "inline";
  className?: string;
}) => {
  const [currentState, setCurrentState] = useState(0);

  useEffect(() => {
    if (!loading || loadingStates.length === 0) {
      setCurrentState(0);
      return;
    }

    if (typeof activeIndex === "number" && Number.isFinite(activeIndex)) {
      const clamped = Math.max(0, Math.min(activeIndex, loadingStates.length - 1));
      if (clamped !== currentState) {
        setCurrentState(clamped);
      }
      return;
    }

    const timeout = setTimeout(() => {
      setCurrentState((prevState) =>
        loop
          ? prevState === loadingStates.length - 1
            ? 0
            : prevState + 1
          : Math.min(prevState + 1, loadingStates.length - 1)
      );
    }, duration);

    return () => clearTimeout(timeout);
  }, [currentState, loading, loop, loadingStates.length, duration]);
  return (
    <AnimatePresence mode="wait">
      {loading && (
        variant === "overlay" ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full h-full fixed inset-0 z-[100] flex items-center justify-center backdrop-blur-2xl"
          >
            <div className="h-96 relative">
              <LoaderCore value={currentState} loadingStates={loadingStates} />
            </div>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className={cn(className)}
          >
            <div className="relative w-full">
              <div className="h-1 w-full bg-muted/40 rounded overflow-hidden mb-2">
                <motion.div
                  className="h-full w-1/3 bg-gradient-to-r from-primary/40 via-primary to-primary/40"
                  animate={{ x: ["-100%", "100%"] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
                />
              </div>
              <LoaderCore value={currentState} loadingStates={loadingStates} compact alignLeft />
            </div>
          </motion.div>
        )
      )}
    </AnimatePresence>
  );
};
