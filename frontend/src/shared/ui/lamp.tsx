'use client'

import React from 'react'
import { cn } from '@/shared/lib/utils'

type LampContainerProps = {
  children: React.ReactNode
  className?: string
}

export function LampContainer({ children, className }: LampContainerProps) {
  return (
    <div className={cn('relative flex w-full justify-center', className)}>
      <div className="pointer-events-none absolute inset-x-0 -top-[220px] flex h-[460px] justify-center">
        <div className="relative h-full w-[420px]">
          <div className="absolute left-1/2 top-0 h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.32),rgba(253,212,112,0.22),transparent_70%)] blur-[140px] opacity-90" />
          <div className="absolute left-1/2 top-[120px] h-[320px] w-[320px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(253,230,138,0.32),rgba(250,204,21,0.18),transparent_70%)] blur-[110px] opacity-80" />
          <div className="absolute left-1/2 top-[210px] h-[220px] w-[220px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(255,249,195,0.55),rgba(255,255,255,0.18),transparent_75%)] blur-[80px] opacity-85" />
          <div className="absolute inset-x-10 top-[310px] h-24 rounded-full bg-gradient-to-b from-amber-100/50 via-amber-100/20 to-transparent blur-[70px] opacity-70" />
        </div>
      </div>

      <div className="relative z-10 flex w-full justify-center">
        {children}
      </div>
    </div>
  )
}

export default LampContainer
