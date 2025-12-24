'use client'

import React from 'react'
import { motion } from 'motion/react'
import { LampContainer } from '@/shared/ui/lamp'
import { cn } from '@/shared/lib/utils'

type LampSectionHeaderProps = {
  title: React.ReactNode
  subtitle?: React.ReactNode
  className?: string
}

export function LampSectionHeader({ title, subtitle, className }: LampSectionHeaderProps) {
  return (
    <LampContainer
      align="left"
      className={cn(
        // Give the lamp room to render above and “focus” underneath the header
        'py-10',
        className
      )}
    >
      <div className="w-full">
        <motion.h1
          initial={{ opacity: 0.5, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            delay: 0.15,
            duration: 0.6,
            ease: 'easeInOut',
          }}
          className="bg-gradient-to-br from-foreground to-muted-foreground bg-clip-text text-left text-4xl font-semibold tracking-tight text-transparent md:text-5xl"
        >
          {title}
        </motion.h1>

        {subtitle ? (
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              delay: 0.25,
              duration: 0.6,
              ease: 'easeInOut',
            }}
            className="mt-3 max-w-[52ch] text-left text-muted-foreground"
          >
            {subtitle}
          </motion.p>
        ) : null}
      </div>
    </LampContainer>
  )
}

