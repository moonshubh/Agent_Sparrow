'use client'

import React, { Children, cloneElement, useEffect, useMemo, useRef, useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform, AnimatePresence, type MotionValue } from 'framer-motion'
import './Dock.css'

export type DockItemData = {
  icon: React.ReactNode
  label: React.ReactNode
  onClick?: () => void
  className?: string
}

export type DockProps = {
  items: DockItemData[]
  className?: string
  distance?: number
  panelHeight?: number
  baseItemSize?: number
  dockHeight?: number
  magnification?: number
  spring?: Parameters<typeof useSpring>[1]
}

type DockItemProps = {
  className?: string
  children: React.ReactNode
  onClick?: () => void
  mouseX: MotionValue<number>
  spring: Parameters<typeof useSpring>[1]
  distance: number
  baseItemSize: number
  magnification: number
}

function DockItem({ children, className = '', onClick, mouseX, spring, distance, magnification, baseItemSize }: DockItemProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isHovered = useMotionValue(0)

  const mouseDistance = useTransform(mouseX, (val) => {
    const rect = ref.current?.getBoundingClientRect() ?? { x: 0, width: baseItemSize }
    return val - rect.x - baseItemSize / 2
  })

  const targetSize = useTransform(mouseDistance, [-distance, 0, distance], [baseItemSize, magnification, baseItemSize])
  const size = useSpring(targetSize, spring)

  return (
    <motion.div
      ref={ref}
      style={{ width: size, height: size }}
      onHoverStart={() => isHovered.set(1)}
      onHoverEnd={() => isHovered.set(0)}
      onFocus={() => isHovered.set(1)}
      onBlur={() => isHovered.set(0)}
      onClick={onClick}
      className={`dock-item ${className}`}
      tabIndex={0}
      role="button"
      aria-haspopup="true"
    >
      {Children.map(children, (child) => cloneElement(child as React.ReactElement, { isHovered }))}
    </motion.div>
  )
}

type DockLabelProps = { className?: string; children: React.ReactNode } & { isHovered?: MotionValue<number> }

function DockLabel({ children, className = '', isHovered }: DockLabelProps) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!isHovered) return
    const unsub = isHovered.on('change', (latest) => setIsVisible(latest === 1))
    return () => unsub()
  }, [isHovered])

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 0 }}
          animate={{ opacity: 1, y: -10 }}
          exit={{ opacity: 0, y: 0 }}
          transition={{ duration: 0.2 }}
          className={`dock-label ${className}`}
          role="tooltip"
          style={{ x: '-50%' }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

type DockIconProps = { className?: string; children: React.ReactNode } & { isHovered?: MotionValue<number> }
function DockIcon({ children, className = '' }: DockIconProps) {
  // Simple icon-only circular glyph container (styled in Dock.css)
  return (
    <div className={`dock-icon ${className}`}>
      <div className="dock-glyph">{children}</div>
    </div>
  )
}

export default function Dock({
  items,
  className = '',
  spring = { mass: 0.1, stiffness: 150, damping: 12 },
  magnification = 108,
  distance = 200,
  panelHeight = 68,
  dockHeight = 240,
  baseItemSize = 72,
}: DockProps) {
  const mouseX = useMotionValue(Infinity)
  // Keep dock container height static to avoid hover jitter near bottom

  return (
    <motion.div style={{ height: panelHeight, scrollbarWidth: 'none' }} className="dock-outer">
      <motion.div
        onMouseMove={({ pageX }) => {
          mouseX.set(pageX)
        }}
        onMouseLeave={() => {
          mouseX.set(Infinity)
        }}
        className={`dock-panel ${className}`}
        style={{ height: panelHeight }}
        role="toolbar"
        aria-label="Application dock"
      >
        {items.map((item, index) => (
          <DockItem
            key={index}
            onClick={item.onClick}
            className={item.className}
            mouseX={mouseX}
            spring={spring}
            distance={distance}
            magnification={magnification}
            baseItemSize={baseItemSize}
          >
            <DockIcon>
              {item.icon}
            </DockIcon>
            <DockLabel>{item.label}</DockLabel>
          </DockItem>
        ))}
      </motion.div>
    </motion.div>
  )
}
