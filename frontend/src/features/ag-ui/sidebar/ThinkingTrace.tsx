'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BrainCircuit,
  Maximize2,
  Minimize2,
  ChevronDown,
  ChevronRight,
  Circle,
  Terminal,
  Search,
  Zap,
  Clock,
  PauseCircle,
} from 'lucide-react';
import type { TraceStep } from '../types/thinkingTrace';
import '../timeline/agentic-timeline.css';

interface ThinkingTraceProps {
  steps: TraceStep[];
  activeStepId?: string;
  collapsed?: boolean;
  onCollapseToggle?: () => void;
  onStepFocus?: (stepId?: string) => void;
  className?: string;
}

const TypeIcon = ({ type, size = 'w-3 h-3' }: { type: TraceStep['type']; size?: string }) => {
  const sizeClass = size;
  switch (type) {
    case 'action':
      return <Terminal className={sizeClass} />;
    case 'result':
      return <Zap className={sizeClass} />;
    default:
      return <Search className={sizeClass} />;
  }
};

const StatusGlyph = ({ isActive, type }: { isActive: boolean; type: TraceStep['type'] }) => {
  return (
    <div className={`relative flex items-center justify-center w-5 h-5 rounded-full border-2 ${
      isActive 
        ? 'border-purple-400 bg-purple-400/10 animate-pulse' 
        : 'border-white/20 bg-white/5'
    }`}>
      <TypeIcon type={type} size="w-2.5 h-2.5" />
    </div>
  );
};

const formatTimestamp = (timestamp?: string) => {
  if (!timestamp) return '';
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export const ThinkingTrace: React.FC<ThinkingTraceProps> = ({
  steps,
  activeStepId,
  collapsed = false,
  onCollapseToggle,
  onStepFocus,
  className = '',
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isMiniMode, setIsMiniMode] = useState(false);
  const [sliderIndex, setSliderIndex] = useState(0);
  const [isAutoFollow, setIsAutoFollow] = useState(true);
  const [expandedStepIds, setExpandedStepIds] = useState<Set<string>>(new Set());

  const maxIndex = Math.max(steps.length - 1, 0);

  useEffect(() => {
    if (steps.length === 0) {
      setSliderIndex(0);
      return;
    }
    if (isAutoFollow) {
      setSliderIndex(maxIndex);
    } else {
      setSliderIndex((prev) => clamp(prev, 0, maxIndex));
    }
  }, [steps.length, isAutoFollow, maxIndex]);

  useEffect(() => {
    if (!scrollContainerRef.current || !isAutoFollow) return;
    scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
  }, [sliderIndex, isAutoFollow]);

  useEffect(() => {
    if (!activeStepId || !scrollContainerRef.current) return;
    const stepElement = scrollContainerRef.current.querySelector<HTMLDivElement>(`[data-step-id="${activeStepId}"]`);
    if (stepElement && !isAutoFollow) {
      stepElement.scrollIntoView({ block: 'nearest' });
    }
  }, [activeStepId, isAutoFollow]);

  const visibleSteps = useMemo(() => {
    if (steps.length === 0) return [];
    return steps.slice(0, sliderIndex + 1);
  }, [steps, sliderIndex]);

  const handleSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(event.target.value);
    setSliderIndex(value);
    const isLive = value === maxIndex;
    setIsAutoFollow(isLive);
    const nextStep = steps[value];
    if (isLive) {
      const current = steps[maxIndex];
      onStepFocus?.(current?.id);
    } else {
      onStepFocus?.(nextStep?.id);
    }
  };

  const toggleExpanded = (id: string) => {
    setExpandedStepIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const collapseButton = (
    <button
      type="button"
      onClick={onCollapseToggle}
      className="p-1 rounded-md text-white/60 hover:text-white hover:bg-white/10 transition-colors"
      aria-label={collapsed ? 'Expand thinking trace' : 'Collapse thinking trace'}
    >
      {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
    </button>
  );

  const miniToggle = (
    <button
      type="button"
      onClick={() => setIsMiniMode((prev) => !prev)}
      className="p-1 rounded-md text-white/60 hover:text-white hover:bg-white/10 transition-colors"
      aria-label={isMiniMode ? 'Dock thinking window' : 'Pop out thinking window'}
    >
      {isMiniMode ? <Maximize2 className="w-3.5 h-3.5" /> : <Minimize2 className="w-3.5 h-3.5" />}
    </button>
  );

  const containerClasses = [
    'flex flex-col bg-neutral-900/50 border border-white/10 rounded-xl overflow-hidden backdrop-blur-sm transition-all duration-300',
    className,
    isMiniMode ? 'h-64 w-80 fixed bottom-6 right-6 z-50 shadow-2xl border-white/20' : 'h-full',
  ].join(' ');

  return (
    <div className={containerClasses}>
      <div className="flex items-center justify-between px-4 py-3 bg-white/5 border-b border-white/10">
        <div className="flex items-center gap-2 text-white/80 text-xs font-semibold uppercase tracking-wide">
          <BrainCircuit className="w-4 h-4 text-purple-300" />
          <span>Agent Thinking</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/10 text-white/60">
            {steps.length} steps
          </span>
        </div>
        <div className="flex items-center gap-1">
          {miniToggle}
          {collapseButton}
        </div>
      </div>

      <div
        ref={scrollContainerRef}
        className={`flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent ${
          collapsed ? 'max-h-64' : ''
        }`}
      >
        {visibleSteps.length === 0 ? (
          <div className="text-xs text-white/50 flex items-center gap-2">
            <PauseCircle className="w-4 h-4" />
            Waiting for activity
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {visibleSteps.map((step) => {
              const isActive = step.id === activeStepId;
              const isExpanded = !collapsed && (expandedStepIds.has(step.id) || step.type === 'thought');
              return (
                <motion.div
                  key={step.id}
                  data-step-id={step.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`group relative pl-6 border-l ${isActive ? 'border-purple-500' : 'border-white/10'}`}
                >
                  <div className="absolute -left-[10px] top-[6px] flex items-center justify-center">
                    <StatusGlyph isActive={isActive} type={step.type} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <div
                      className="flex items-center gap-2 cursor-pointer hover:bg-white/5 p-1.5 rounded-md -ml-1.5 transition-colors"
                      onClick={() => !collapsed && toggleExpanded(step.id)}
                    >
                      <div className="flex flex-col flex-1 min-w-0">
                        <span className="text-sm text-white/90 font-medium truncate">
                          {step.metadata?.toolName || step.metadata?.model || step.type}
                        </span>
                        <span className="text-[11px] text-white/40 font-mono">
                          {formatTimestamp(step.timestamp)}
                        </span>
                      </div>
                      <span className="text-xs text-white/70 truncate max-w-[120px]">
                        {step.metadata?.status || (step.type === 'thought' ? 'Reasoning' : 'Action complete')}
                      </span>
                      {!collapsed && (
                        isExpanded ? (
                          <ChevronDown className="w-3 h-3 text-white/40" />
                        ) : (
                          <ChevronRight className="w-3 h-3 text-white/40" />
                        )
                      )}
                    </div>
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="text-xs text-white/70 bg-black/20 rounded-md p-3 font-mono whitespace-pre-wrap break-words ml-6">
                            {step.content || 'No transcript yet'}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      {!collapsed && (
        <div className="px-4 py-3 bg-white/5 border-t border-white/5 flex flex-col gap-2">
          <div className="flex items-center justify-between text-[10px] text-white/50 uppercase tracking-wider font-medium">
            <span>Timeline</span>
            <span>{isAutoFollow ? 'Live' : 'History'}</span>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(maxIndex, 0)}
            value={sliderIndex}
            onChange={handleSliderChange}
            className="w-full accent-purple-400"
            disabled={steps.length === 0}
          />
          <div className="flex items-center justify-between text-[11px] text-white/40 font-mono">
            <span>{steps[sliderIndex]?.metadata?.toolName || steps[sliderIndex]?.type || 'Idle'}</span>
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{steps[sliderIndex]?.timestamp ? formatTimestamp(steps[sliderIndex]?.timestamp) : '--:--:--'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
