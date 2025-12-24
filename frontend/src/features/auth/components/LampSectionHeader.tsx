'use client'

import React from 'react'
import { motion } from 'motion/react'
import { LampContainer } from '@/components/ui/lamp'
import { cn } from '@/shared/lib/utils'

export type LampSectionHeaderProps = {
  title: React.ReactNode
  subtitle?: React.ReactNode
  className?: string
}

export function LampSectionHeader({ title, subtitle, className }: LampSectionHeaderProps) {
  return (
    <LampContainer
      className={cn(
        // Compact height for the login left column; the lamp bar lives near the top.
        'h-[240px] w-full md:h-[280px]',
        className
      )}
    >
      <div className="mx-auto flex max-w-md flex-col items-center">
        <motion.h1
          initial={{ opacity: 0.5, y: 48 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{
            delay: 0.2,
            duration: 0.8,
            ease: 'easeInOut',
          }}
          className="mt-6 bg-gradient-to-br from-foreground to-muted-foreground bg-clip-text py-2 text-center text-4xl font-semibold tracking-tight text-transparent md:text-5xl"
        >
          {title}
        </motion.h1>

        {subtitle ? (
          <motion.p
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{
              delay: 0.3,
              duration: 0.7,
              ease: 'easeInOut',
            }}
            className="mt-2 text-center text-muted-foreground"
          >
            {subtitle}
          </motion.p>
        ) : null}
      </div>
    </LampContainer>
  )
}

