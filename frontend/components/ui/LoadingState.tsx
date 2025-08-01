"use client"

import React, { useMemo, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Loader2, Bot, MessageCircle, FileSearch, Search } from 'lucide-react'

/**
 * Size variants for loading components
 */
type LoadingSize = 'sm' | 'md' | 'lg'

/**
 * Visual variants for loading states
 */
type LoadingVariant = 'default' | 'card' | 'inline' | 'overlay'

/**
 * Supported agent types for specialized loading states
 */
type AgentType = 'primary' | 'log_analyst' | 'researcher'

/**
 * Props for the main LoadingState component
 */
interface LoadingStateProps {
  /** Additional CSS classes */
  className?: string
  /** Size variant */
  size?: LoadingSize
  /** Visual variant */
  variant?: LoadingVariant
  /** Optional loading message */
  message?: string
  /** Agent type for specialized styling */
  agentType?: AgentType
  /** Whether to show the loading icon */
  showIcon?: boolean
  /** Additional content to render */
  children?: React.ReactNode
}

/**
 * Props for LoadingDots component
 */
interface LoadingDotsProps {
  /** Additional CSS classes */
  className?: string
  /** Size variant */
  size?: LoadingSize
  /** Number of dots to display */
  dotCount?: number
}

/**
 * Props for LoadingProgress component
 */
interface LoadingProgressProps {
  /** Array of step names */
  steps: string[]
  /** Current step index (0-based) */
  currentStep: number
  /** Additional CSS classes */
  className?: string
}

// Move static objects outside component to prevent recreation
const AGENT_INFO = {
  primary: {
    icon: MessageCircle,
    label: 'Primary Support',
    color: 'text-blue-500'
  },
  log_analyst: {
    icon: FileSearch,
    label: 'Log Analyst',
    color: 'text-orange-500'
  },
  researcher: {
    icon: Search,
    label: 'Researcher',
    color: 'text-purple-500'
  }
} as const

// Size classes constants to prevent recreation
const SIZE_CLASSES = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8'
} as const

// Icon size constants
const ICON_SIZE_CLASSES = {
  sm: 'w-2 h-2',
  md: 'w-2 h-2', 
  lg: 'w-3 h-3'
} as const

// Dot size constants
const DOT_SIZE_CLASSES = {
  sm: 'w-1 h-1',
  md: 'w-1.5 h-1.5',
  lg: 'w-2 h-2'
} as const

export function LoadingState({ 
  className,
  size = 'md',
  variant = 'default',
  message,
  agentType,
  showIcon = true,
  children
}: LoadingStateProps) {
  // Memoize helper functions to prevent recreation
  const getAgentIcon = useCallback(() => {
    if (!agentType) return Bot
    return AGENT_INFO[agentType]?.icon || Bot
  }, [agentType])

  const getAgentLabel = useCallback(() => {
    if (!agentType) return 'Loading'
    return AGENT_INFO[agentType]?.label || 'Loading'
  }, [agentType])

  const getAgentColor = useCallback(() => {
    if (!agentType) return 'text-muted-foreground'
    return AGENT_INFO[agentType]?.color || 'text-muted-foreground'
  }, [agentType])

  // Memoize computed values
  const iconSizeClass = useMemo(() => ICON_SIZE_CLASSES[size], [size])
  const loaderSizeClass = useMemo(() => SIZE_CLASSES[size], [size])

  const renderContent = () => (
    <div className="flex items-center gap-3">
      {showIcon && (
        <div className="relative">
          <Loader2 className={cn(loaderSizeClass, "animate-spin text-primary")} />
          {agentType && size !== 'sm' && (
            <div className={cn(
              "absolute inset-0 flex items-center justify-center",
              getAgentColor()
            )}>
              {React.createElement(getAgentIcon(), { 
                className: iconSizeClass
              })}
            </div>
          )}
        </div>
      )}
      
      <div className="flex flex-col gap-1">
        {message && (
          <span className={cn(
            "text-foreground font-medium",
            size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-base' : 'text-sm'
          )}>
            {message}
          </span>
        )}
        
        {agentType && (
          <span className={cn(
            "text-muted-foreground",
            size === 'sm' ? 'text-xs' : 'text-sm'
          )}>
            {getAgentLabel()} is working...
          </span>
        )}
        
        {children}
      </div>
    </div>
  )

  const baseClasses = "flex items-center justify-center"

  switch (variant) {
    case 'card':
      return (
        <div className={cn(
          baseClasses,
          "bg-muted/30 border border-border/50 rounded-lg p-6",
          className
        )}>
          {renderContent()}
        </div>
      )

    case 'inline':
      return (
        <div className={cn(
          "inline-flex items-center gap-2",
          className
        )}>
          {renderContent()}
        </div>
      )

    case 'overlay':
      return (
        <div className={cn(
          "absolute inset-0 bg-background/80 backdrop-blur-sm",
          baseClasses,
          "z-50",
          className
        )}>
          <div className="bg-background border border-border/50 rounded-lg p-4 shadow-lg">
            {renderContent()}
          </div>
        </div>
      )

    default:
      return (
        <div className={cn(baseClasses, className)}>
          {renderContent()}
        </div>
      )
  }
}

// Skeleton loading components
export function SkeletonLine({ className, width }: { className?: string, width?: string }) {
  // Use CSS custom property for consistency with other components
  const style = useMemo(() => ({ '--skeleton-width': width } as React.CSSProperties), [width])
  
  return (
    <div 
      className={cn(
        "h-4 bg-muted animate-pulse rounded",
        width && "[width:var(--skeleton-width)]",
        className
      )}
      style={width ? style : undefined}
    />
  )
}

export function SkeletonText({ lines = 3, className }: { lines?: number, className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine 
          key={i}
          width={i === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn(
      "border border-border/50 rounded-lg p-4 space-y-3",
      className
    )}>
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-muted animate-pulse rounded-full" />
        <div className="space-y-1 flex-1">
          <SkeletonLine width="40%" />
          <SkeletonLine width="60%" />
        </div>
      </div>
      <SkeletonText lines={2} />
    </div>
  )
}

/**
 * Loading dots animation component with configurable dot count
 */
export function LoadingDots({ 
  className, 
  size = 'md', 
  dotCount = 3 
}: LoadingDotsProps) {
  // Memoize dot size class
  const dotSizeClass = useMemo(() => DOT_SIZE_CLASSES[size], [size])
  
  // Memoize dots array to prevent recreation
  const dots = useMemo(() => 
    Array.from({ length: dotCount }, (_, i) => i), 
    [dotCount]
  )

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {dots.map((i) => (
        <div
          key={i}
          className={cn(
            dotSizeClass,
            "bg-current rounded-full animate-bounce"
          )}
          style={{
            animationDelay: `${i * 0.1}s`
          }}
        />
      ))}
    </div>
  )
}

/**
 * Progress bar with steps - includes bounds checking and safe display
 */
export function LoadingProgress({ 
  steps, 
  currentStep, 
  className 
}: LoadingProgressProps) {
  // Add bounds checking for safety
  const safeCurrentStep = Math.max(0, Math.min(currentStep, steps.length - 1))
  const safeStepsLength = Math.max(1, steps.length) // Prevent division by zero
  
  // Memoize progress calculation
  const progress = useMemo(() => 
    ((safeCurrentStep + 1) / safeStepsLength) * 100, 
    [safeCurrentStep, safeStepsLength]
  )

  // Memoize current step text with bounds checking
  const currentStepText = useMemo(() => {
    if (steps.length === 0) return 'Processing...'
    return steps[safeCurrentStep] || 'Processing...'
  }, [steps, safeCurrentStep])
  
  // Memoize step count display with zero-length handling
  const stepCountText = useMemo(() => {
    if (steps.length === 0) return '0 / 0'
    return `${safeCurrentStep + 1} / ${steps.length}`
  }, [safeCurrentStep, steps.length])

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">
          {currentStepText}
        </span>
        <span className="text-muted-foreground">
          {stepCountText}
        </span>
      </div>
      
      <div className="w-full bg-muted rounded-full h-2">
        <div 
          className="bg-primary h-2 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      
      {steps.length > 0 && (
        <div className="flex justify-between text-xs text-muted-foreground">
          {steps.map((step, index) => (
            <span 
              key={index}
              className={cn(
                "px-1",
                index <= safeCurrentStep ? "text-primary font-medium" : ""
              )}
            >
              {index + 1}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}