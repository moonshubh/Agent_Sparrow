'use client'
import React from 'react'
import { motion } from 'motion/react'
import { cn } from '@/shared/lib/utils'

export type LampContainerProps = {
  children: React.ReactNode
  className?: string
  align?: 'center' | 'left' | 'right'
}

/**
 * Aceternity-style Lamp with proper cone-shaped glow
 * - Uses concentric radial gradients for natural light falloff
 * - Warm amber color scheme
 * - Lamp bar anchors the effect at the top
 */
export function LampContainer({ children, className, align = 'center' }: LampContainerProps) {
  const justifyClass =
    align === 'left' ? 'justify-start' : align === 'right' ? 'justify-end' : 'justify-center'

  return (
    <div className={cn('relative w-full', justifyClass, className)}>
      {/* Lamp effect layer - positioned at top */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center">
        {/* Lamp bar */}
        <motion.div
          initial={{ width: '15rem', opacity: 0 }}
          whileInView={{ width: '30rem', opacity: 1 }}
          transition={{
            delay: 0.2,
            duration: 0.8,
            ease: 'easeInOut',
          }}
          className="absolute top-0 z-20 h-0.5 bg-amber-400"
        />

        {/* Light glow container - clips everything above the lamp bar */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{
            delay: 0.25,
            duration: 1.2,
            ease: 'easeOut',
          }}
          className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px]"
          style={{ clipPath: 'inset(0 0 0 0)' }}
        >
          {/* ============================================
              3D LIGHT PHYSICS MODEL:
              - Light source: lamp bar (linear, horizontal)
              - Emission direction: downward only
              - Intensity falloff: inverse with distance
              - Spread: expands as distance increases
              - No light above the source
              ============================================ */}

          {/* ZONE A: Source emission (0-5px below bar) */}
          {/* Brightest zone - light just leaving the source */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-[480px] h-[50px]"
            style={{
              top: '2px',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(255,252,240,0.5) 20%, rgba(253,245,200,0.3) 50%, rgba(253,235,160,0.15) 80%, transparent 100%)',
              filter: 'blur(8px)',
              maskImage: 'linear-gradient(90deg, transparent 0%, white 15%, white 85%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, white 15%, white 85%, transparent 100%)',
            }}
          />

          {/* ZONE B: Near field (5-80px) - primary illumination */}
          {/* Center bright column */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-[280px] h-[200px]"
            style={{
              top: '8px',
              background: 'linear-gradient(180deg, rgba(255,252,235,0.55) 0%, rgba(253,240,180,0.35) 25%, rgba(253,225,140,0.2) 50%, rgba(253,212,112,0.08) 75%, transparent 100%)',
              filter: 'blur(30px)',
              borderRadius: '0 0 50% 50%',
            }}
          />

          {/* Left near-field spread */}
          <div
            className="absolute w-[200px] h-[180px]"
            style={{
              top: '10px',
              left: 'calc(50% - 220px)',
              background: 'linear-gradient(160deg, rgba(253,240,180,0.4) 0%, rgba(253,225,140,0.2) 30%, rgba(253,212,112,0.08) 60%, transparent 100%)',
              filter: 'blur(35px)',
              borderRadius: '0 0 40% 60%',
            }}
          />

          {/* Right near-field spread */}
          <div
            className="absolute w-[200px] h-[180px]"
            style={{
              top: '10px',
              right: 'calc(50% - 220px)',
              background: 'linear-gradient(200deg, rgba(253,240,180,0.4) 0%, rgba(253,225,140,0.2) 30%, rgba(253,212,112,0.08) 60%, transparent 100%)',
              filter: 'blur(35px)',
              borderRadius: '0 0 60% 40%',
            }}
          />

          {/* ZONE C: Mid field (80-200px) - diffused spread */}
          {/* Center mid-field cone */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-[380px] h-[280px]"
            style={{
              top: '50px',
              background: 'radial-gradient(ellipse 100% 80% at 50% 0%, rgba(253,225,140,0.3) 0%, rgba(253,212,112,0.12) 40%, rgba(250,204,21,0.05) 70%, transparent 90%)',
              filter: 'blur(50px)',
            }}
          />

          {/* Left mid-field wrap */}
          <div
            className="absolute w-[180px] h-[220px]"
            style={{
              top: '60px',
              left: 'calc(50% - 280px)',
              background: 'radial-gradient(ellipse 70% 80% at 80% 0%, rgba(253,220,130,0.25) 0%, rgba(250,204,21,0.08) 50%, transparent 85%)',
              filter: 'blur(45px)',
            }}
          />

          {/* Right mid-field wrap */}
          <div
            className="absolute w-[180px] h-[220px]"
            style={{
              top: '60px',
              right: 'calc(50% - 280px)',
              background: 'radial-gradient(ellipse 70% 80% at 20% 0%, rgba(253,220,130,0.25) 0%, rgba(250,204,21,0.08) 50%, transparent 85%)',
              filter: 'blur(45px)',
            }}
          />

          {/* ZONE D: Far field (200px+) - ambient scatter */}
          {/* Wide ambient base */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-[550px] h-[300px]"
            style={{
              top: '100px',
              background: 'radial-gradient(ellipse 100% 60% at 50% 0%, rgba(253,212,112,0.18) 0%, rgba(250,204,21,0.06) 50%, transparent 80%)',
              filter: 'blur(60px)',
            }}
          />

          {/* Far left scatter */}
          <div
            className="absolute w-[140px] h-[200px]"
            style={{
              top: '80px',
              left: 'calc(50% - 320px)',
              background: 'linear-gradient(150deg, rgba(253,215,120,0.15) 0%, rgba(250,204,21,0.05) 50%, transparent 100%)',
              filter: 'blur(40px)',
            }}
          />

          {/* Far right scatter */}
          <div
            className="absolute w-[140px] h-[200px]"
            style={{
              top: '80px',
              right: 'calc(50% - 320px)',
              background: 'linear-gradient(210deg, rgba(253,215,120,0.15) 0%, rgba(250,204,21,0.05) 50%, transparent 100%)',
              filter: 'blur(40px)',
            }}
          />

          {/* ZONE E: Ground reflection - light bouncing back */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-[420px] h-[100px]"
            style={{
              top: '280px',
              background: 'radial-gradient(ellipse 100% 50% at 50% 0%, rgba(253,230,160,0.15) 0%, rgba(250,210,100,0.05) 60%, transparent 90%)',
              filter: 'blur(40px)',
            }}
          />
        </motion.div>
      </div>

      {/* Content */}
      <div className={cn('relative z-10 flex h-full w-full flex-col px-6 pt-8 text-center', justifyClass === 'justify-center' ? 'items-center' : justifyClass === 'justify-start' ? 'items-start' : 'items-end')}>
        {children}
      </div>
    </div>
  )
}

export default LampContainer
