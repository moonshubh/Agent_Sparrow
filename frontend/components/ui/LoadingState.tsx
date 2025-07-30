"use client"

import React from 'react'
import { cn } from '@/lib/utils'
import { Loader2, Bot, MessageCircle, FileSearch, Search } from 'lucide-react'

interface LoadingStateProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
  variant?: 'default' | 'card' | 'inline' | 'overlay'
  message?: string
  agentType?: 'primary' | 'log_analyst' | 'researcher'
  showIcon?: boolean
  children?: React.ReactNode
}

const agentInfo = {
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
}

export function LoadingState({ 
  className,
  size = 'md',
  variant = 'default',
  message,
  agentType,
  showIcon = true,
  children
}: LoadingStateProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8'
  }

  const getAgentIcon = () => {
    if (!agentType) return Bot
    return agentInfo[agentType]?.icon || Bot
  }

  const getAgentLabel = () => {
    if (!agentType) return 'Loading'
    return agentInfo[agentType]?.label || 'Loading'
  }

  const getAgentColor = () => {
    if (!agentType) return 'text-muted-foreground'
    return agentInfo[agentType]?.color || 'text-muted-foreground'
  }

  const renderContent = () => (
    <div className="flex items-center gap-3">
      {showIcon && (
        <div className="relative">
          <Loader2 className={cn(sizeClasses[size], "animate-spin text-primary")} />
          {agentType && size !== 'sm' && (
            <div className={cn(
              "absolute inset-0 flex items-center justify-center",
              getAgentColor()
            )}>
              {React.createElement(getAgentIcon(), { 
                className: cn(
                  size === 'lg' ? 'w-3 h-3' : 'w-2 h-2'
                )
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
  return (
    <div 
      className={cn(
        "h-4 bg-muted animate-pulse rounded",
        className
      )}
      style={{ width }}
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

// Loading dots animation
export function LoadingDots({ className, size = 'md' }: { className?: string, size?: 'sm' | 'md' | 'lg' }) {
  const dotSizes = {
    sm: 'w-1 h-1',
    md: 'w-1.5 h-1.5',
    lg: 'w-2 h-2'
  }

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={cn(
            dotSizes[size],
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

// Progress bar with steps
export function LoadingProgress({ 
  steps, 
  currentStep, 
  className 
}: { 
  steps: string[]
  currentStep: number
  className?: string 
}) {
  const progress = ((currentStep + 1) / steps.length) * 100

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">
          {steps[currentStep] || 'Processing...'}
        </span>
        <span className="text-muted-foreground">
          {currentStep + 1} / {steps.length}
        </span>
      </div>
      
      <div className="w-full bg-muted rounded-full h-2">
        <div 
          className="bg-primary h-2 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      
      <div className="flex justify-between text-xs text-muted-foreground">
        {steps.map((step, index) => (
          <span 
            key={index}
            className={cn(
              "px-1",
              index <= currentStep ? "text-primary font-medium" : ""
            )}
          >
            {index + 1}
          </span>
        ))}
      </div>
    </div>
  )
}