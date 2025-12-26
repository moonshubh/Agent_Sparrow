"use client"

import React, { useCallback, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/shared/lib/utils'
import { Check } from 'lucide-react'

interface SpatialColorPickerProps {
    selectedColor: string
    onChange: (color: string) => void
    // We ignore the passed colors prop now to enforce our specific multi-layer design
    colors?: string[]
    // Optional: start with picker already open
    initialOpen?: boolean
    // Optional: callback when picker closes
    onClose?: () => void
    // Optional: compact mode for inline use
    compact?: boolean
}

// Define layers
const CENTER_COLOR = '#ffffff'

const INNER_RING_COLORS = [
    '#fbcfe8', // pink-200
    '#e9d5ff', // purple-200
    '#bfdbfe', // blue-200
    '#bae6fd', // sky-200
    '#a7f3d0', // emerald-200
    '#fde68a', // amber-200
    '#fecaca', // red-200
]

const OUTER_RING_COLORS = [
    '#db2777', // pink-600
    '#9333ea', // purple-600
    '#4f46e5', // indigo-600
    '#2563eb', // blue-600
    '#0ea5e9', // sky-500
    '#06b6d4', // cyan-500
    '#10b981', // emerald-500
    '#84cc16', // lime-500
    '#eab308', // yellow-500
    '#f97316', // orange-500
    '#ef4444', // red-500
    '#be185d', // rose-700
]

const COLOR_LABELS: Record<string, string> = {
    '#ffffff': 'white',
    '#fbcfe8': 'soft pink',
    '#e9d5ff': 'lavender',
    '#bfdbfe': 'light blue',
    '#bae6fd': 'sky blue',
    '#a7f3d0': 'mint',
    '#fde68a': 'amber',
    '#fecaca': 'rose',
    '#db2777': 'magenta',
    '#9333ea': 'violet',
    '#4f46e5': 'indigo',
    '#2563eb': 'blue',
    '#0ea5e9': 'sky',
    '#06b6d4': 'cyan',
    '#10b981': 'emerald',
    '#84cc16': 'lime',
    '#eab308': 'yellow',
    '#f97316': 'orange',
    '#ef4444': 'red',
    '#be185d': 'deep rose',
}

const describeColor = (hex: string): string => COLOR_LABELS[hex.toLowerCase()] || hex

export const SpatialColorPicker = ({
    selectedColor,
    onChange,
    initialOpen = false,
    onClose,
    compact = false,
}: SpatialColorPickerProps) => {
    const [isOpen, setIsOpen] = useState(initialOpen)

    // Configuration - use smaller sizes in compact mode
    const centerSize = compact ? 32 : 42
    const nodeSize = compact ? 20 : 26
    const innerRadius = compact ? 28 : 36
    const outerRadius = compact ? 50 : 66

    const handleClose = useCallback(() => {
        setIsOpen(false)
        onClose?.()
    }, [onClose])

    return (
        <div className="relative flex items-center justify-center overflow-visible" style={{ width: compact ? 40 : 56, height: compact ? 40 : 56 }}>
            {/* Backdrop to close when clicking outside */}
            {isOpen && (
                <div
                    className="fixed inset-0 z-40"
                    onClick={handleClose}
                />
            )}

            {/* Dark background circle that appears when open */}
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.5 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.5 }}
                        className="absolute z-40 bg-neutral-900/90 backdrop-blur-sm border border-white/10 shadow-2xl"
                        style={{
                            width: outerRadius * 2 + nodeSize + 16,
                            height: (outerRadius * 2 + nodeSize + 16) / 2 + 20, // Half height + padding
                            borderRadius: '0 0 1000px 1000px', // Semi-circle pointing down
                            top: '50%', // Start from the middle
                            marginTop: -20, // Slight overlap with center
                        }}
                    />
                )}
            </AnimatePresence>

            <div className="relative z-50 flex items-center justify-center">
                {/* Central Trigger Button / Center Color */}
                <motion.button
                    layoutId="active-color"
                    className={cn(
                        "relative flex items-center justify-center rounded-full shadow-lg ring-2 ring-offset-2 ring-offset-background transition-shadow z-50",
                        "hover:shadow-xl focus:outline-none"
                    )}
                    type="button"
                    style={{
                        backgroundColor: isOpen ? CENTER_COLOR : selectedColor,
                        borderColor: 'rgba(255,255,255,0.2)',
                        width: centerSize,
                        height: centerSize,
                    }}
                    aria-label={
                        isOpen
                            ? 'Close color picker'
                            : `Color picker, current color: ${describeColor(selectedColor)}`
                    }
                    aria-expanded={isOpen}
                    aria-haspopup="dialog"
                    aria-controls="color-picker-popup"
                    onClick={() => {
                        if (isOpen) {
                            onChange(CENTER_COLOR)
                            handleClose()
                        } else {
                            setIsOpen(true)
                        }
                    }}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                >
                    {/* If open, this center button acts as the white/center color option */}
                    {isOpen && selectedColor === CENTER_COLOR && (
                        <Check className="w-5 h-5 text-black/70" strokeWidth={3} />
                    )}
                </motion.button>

                {/* Color Rings */}
                <AnimatePresence>
                    {isOpen && (
                        <div
                            id="color-picker-popup"
                            className="absolute inset-0 flex items-center justify-center pointer-events-none"
                            role="dialog"
                            aria-label="Color picker options"
                        >
                            {/* Inner Ring */}
                            {INNER_RING_COLORS.map((color, index) => {
                                const count = INNER_RING_COLORS.length
                                const angle = (index / (count - 1)) * Math.PI

                                const x = Math.cos(angle) * innerRadius
                                const y = Math.sin(angle) * innerRadius

                                return (
                                    <ColorNode
                                        key={`inner-${color}`}
                                        color={color}
                                        x={x}
                                        y={y}
                                        isSelected={selectedColor === color}
                                        onClick={() => {
                                            onChange(color)
                                            handleClose()
                                        }}
                                        delay={index * 0.02}
                                        size={nodeSize}
                                    />
                                )
                            })}

                            {/* Outer Ring */}
                            {OUTER_RING_COLORS.map((color, index) => {
                                const count = OUTER_RING_COLORS.length
                                const angle = (index / (count - 1)) * Math.PI

                                const x = Math.cos(angle) * outerRadius
                                const y = Math.sin(angle) * outerRadius

                                return (
                                    <ColorNode
                                        key={`outer-${color}`}
                                        color={color}
                                        x={x}
                                        y={y}
                                        isSelected={selectedColor === color}
                                        onClick={() => {
                                            onChange(color)
                                            handleClose()
                                        }}
                                        delay={0.1 + index * 0.02}
                                        size={nodeSize}
                                    />
                                )
                            })}
                        </div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}

interface ColorNodeProps {
    color: string
    x: number
    y: number
    isSelected: boolean
    onClick: () => void
    delay: number
    size: number
}

const ColorNode = ({ color, x, y, isSelected, onClick, delay, size }: ColorNodeProps) => {
    return (
        <motion.button
            className="absolute rounded-full shadow-md pointer-events-auto flex items-center justify-center ring-1 ring-white/10"
            type="button"
            style={{
                backgroundColor: color,
                width: size,
                height: size,
            }}
            initial={{ x: 0, y: 0, opacity: 0, scale: 0 }}
            animate={{
                x,
                y,
                opacity: 1,
                scale: 1,
                transition: {
                    type: "spring",
                    damping: 25,
                    stiffness: 120,
                    delay: delay
                }
            }}
            exit={{
                x: 0,
                y: 0,
                opacity: 0,
                scale: 0,
                transition: { duration: 0.2 }
            }}
            whileHover={{
                scale: 1.3,
                zIndex: 60,
                boxShadow: "0 0 15px rgba(0,0,0,0.3)"
            }}
            onClick={onClick}
            aria-label={`Select ${describeColor(color)} color`}
            aria-pressed={isSelected}
        >
            {isSelected && (
                <Check className="w-4 h-4 text-white/90 drop-shadow-md" strokeWidth={3} />
            )}
        </motion.button>
    )
}
