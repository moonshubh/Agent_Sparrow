'use client'
import React from 'react'
import { motion } from 'motion/react'
import { cn } from '@/shared/lib/utils'

type LampContainerProps = {
  children: React.ReactNode
  className?: string
}

/**
 * Aceternity Lamp (customized for Agent Sparrow)
 * - Keeps the clean “lamp bar” + conic beams look (Serenity UI reference)
 * - Uses warm amber light to match Agent Sparrow theme
 * - Does NOT force min-h-screen; caller controls height via className
 */
export function LampContainer({ children, className }: LampContainerProps) {
  return (
    <div className={cn('relative w-full overflow-hidden', className)}>
      {/* Lamp + beams (purely decorative) */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="relative flex h-full w-full scale-y-125 items-center justify-center isolate">
          <motion.div
            initial={{ opacity: 0.5, width: '15rem' }}
            whileInView={{ opacity: 1, width: '30rem' }}
            transition={{
              delay: 0.3,
              duration: 0.8,
              ease: 'easeInOut',
            }}
            style={{
              backgroundImage: `conic-gradient(var(--conic-position), var(--tw-gradient-stops))`,
            }}
            className="absolute inset-auto right-1/2 h-56 w-[30rem] overflow-visible from-amber-200 via-transparent to-transparent [--conic-position:from_70deg_at_center_top]"
          >
            <div className="absolute bottom-0 left-0 z-20 h-40 w-full bg-background [mask-image:linear-gradient(to_top,white,transparent)]" />
            <div className="absolute bottom-0 left-0 z-20 h-full w-40 bg-background [mask-image:linear-gradient(to_right,white,transparent)]" />
          </motion.div>

          <motion.div
            initial={{ opacity: 0.5, width: '15rem' }}
            whileInView={{ opacity: 1, width: '30rem' }}
            transition={{
              delay: 0.3,
              duration: 0.8,
              ease: 'easeInOut',
            }}
            style={{
              backgroundImage: `conic-gradient(var(--conic-position), var(--tw-gradient-stops))`,
            }}
            className="absolute inset-auto left-1/2 h-56 w-[30rem] from-transparent via-transparent to-amber-200 [--conic-position:from_290deg_at_center_top]"
          >
            <div className="absolute bottom-0 right-0 z-20 h-full w-40 bg-background [mask-image:linear-gradient(to_left,white,transparent)]" />
            <div className="absolute bottom-0 right-0 z-20 h-40 w-full bg-background [mask-image:linear-gradient(to_top,white,transparent)]" />
          </motion.div>

          {/* Clean fade + glow stack */}
          <div className="absolute top-1/2 h-48 w-full translate-y-12 scale-x-150 bg-background blur-2xl" />
          <div className="absolute top-1/2 z-50 h-48 w-full bg-transparent opacity-10 backdrop-blur-md" />
          <div className="absolute inset-auto z-50 h-36 w-[28rem] -translate-y-1/2 rounded-full bg-amber-200/40 blur-3xl" />

          {/* Lamp focus */}
          <motion.div
            initial={{ width: '8rem' }}
            whileInView={{ width: '16rem' }}
            transition={{
              delay: 0.3,
              duration: 0.8,
              ease: 'easeInOut',
            }}
            className="absolute inset-auto z-30 h-36 w-64 -translate-y-[6rem] rounded-full bg-amber-100/40 blur-2xl"
          />

          {/* Lamp bar */}
          <motion.div
            initial={{ width: '15rem' }}
            whileInView={{ width: '30rem' }}
            transition={{
              delay: 0.3,
              duration: 0.8,
              ease: 'easeInOut',
            }}
            className="absolute inset-auto z-50 h-0.5 w-[30rem] -translate-y-[7rem] bg-amber-200/90"
          />

          {/* Clean top mask (hides beam tops, leaving a crisp bar origin) */}
          <div className="absolute inset-auto z-40 h-44 w-full -translate-y-[12.5rem] bg-background" />
        </div>
      </div>

      {/* Content */}
      <div className="relative z-10 flex h-full w-full flex-col items-center justify-center px-6 text-center">
        {children}
      </div>
    </div>
  )
}

export default LampContainer
