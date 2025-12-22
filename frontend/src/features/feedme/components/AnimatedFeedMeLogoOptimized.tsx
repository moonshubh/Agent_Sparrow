'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

interface AnimatedFeedMeLogoOptimizedProps {
  className?: string
  animationDuration?: number
  loop?: boolean
  autoPlay?: boolean
  fps?: number
  easing?: 'linear' | 'easeIn' | 'easeOut' | 'easeInOut' | 'bounce'
  pauseOnHover?: boolean
  onAnimationComplete?: () => void
}

const KEYFRAMES = [
  '/feedme-keyframes/Keyframe_1.png',
  '/feedme-keyframes/Keyframe_2.png',
  '/feedme-keyframes/Keyframe_3.png',
  '/feedme-keyframes/Keyframe_4.png',
  '/feedme-keyframes/Keyframe_5.png',
  '/feedme-keyframes/Keyframe_6.png',
  '/feedme-keyframes/Keyframe_7.png',
  '/feedme-keyframes/Keyframe_8.png',
]

const easingFunctions = {
  linear: (t: number) => t,
  easeIn: (t: number) => t * t,
  easeOut: (t: number) => t * (2 - t),
  easeInOut: (t: number) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t),
  bounce: (t: number) => {
    if (t < 1 / 2.75) {
      return 7.5625 * t * t
    } else if (t < 2 / 2.75) {
      t -= 1.5 / 2.75
      return 7.5625 * t * t + 0.75
    } else if (t < 2.5 / 2.75) {
      t -= 2.25 / 2.75
      return 7.5625 * t * t + 0.9375
    } else {
      t -= 2.625 / 2.75
      return 7.5625 * t * t + 0.984375
    }
  },
}

export default function AnimatedFeedMeLogoOptimized({
  className = '',
  animationDuration = 2000,
  loop = true,
  autoPlay = true,
  easing = 'linear',
  pauseOnHover = false,
  onAnimationComplete,
}: AnimatedFeedMeLogoOptimizedProps) {
  const [isPlaying, setIsPlaying] = useState(autoPlay)
  const [isHovered, setIsHovered] = useState(false)
  const [imagesLoaded, setImagesLoaded] = useState(false)
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0)

  const shouldReduceMotion = useReducedMotion()
  const animationRef = useRef<number | null>(null)
  const startTimeRef = useRef<number | null>(null)
  const animateRef = useRef<(timestamp: number) => void>(() => {})
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imagesRef = useRef<HTMLImageElement[]>([])

  const loadImages = useCallback(async () => {
    const promises = KEYFRAMES.map((src, index) => {
      return new Promise<void>((resolve, reject) => {
        const img = new Image()
        img.onload = () => {
          imagesRef.current[index] = img
          resolve()
        }
        img.onerror = reject
        img.src = src
      })
    })

    try {
      await Promise.all(promises)
      setImagesLoaded(true)
    } catch (error) {
      console.error('Error loading keyframe images:', error)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadImages()
  }, [loadImages])

  useEffect(() => {
    animateRef.current = (timestamp: number) => {
      // Get canvas and context inside the callback
      const canvas = canvasRef.current
      const ctx = canvas?.getContext('2d')

      if (startTimeRef.current === null) {
        startTimeRef.current = timestamp
      }

      const elapsed = timestamp - (startTimeRef.current ?? timestamp)
      const progress = (elapsed % animationDuration) / animationDuration
      const easedProgress = easingFunctions[easing](progress)
      const frameIndex = Math.floor(easedProgress * KEYFRAMES.length) % KEYFRAMES.length

      setCurrentFrameIndex(frameIndex)

      if (canvas && ctx && imagesRef.current[frameIndex]) {
        ctx.clearRect(0, 0, canvas.width, canvas.height)

        const img = imagesRef.current[frameIndex]
        const aspectRatio = img.width / img.height
        let drawWidth = canvas.width
        let drawHeight = canvas.height

        if (aspectRatio > 1) {
          drawHeight = canvas.width / aspectRatio
        } else {
          drawWidth = canvas.height * aspectRatio
        }

        const x = (canvas.width - drawWidth) / 2
        const y = (canvas.height - drawHeight) / 2

        ctx.drawImage(img, x, y, drawWidth, drawHeight)
      }

      if (!loop && elapsed >= animationDuration) {
        setIsPlaying(false)
        onAnimationComplete?.()
        return
      }

      if (isPlaying && !(pauseOnHover && isHovered)) {
        animationRef.current = requestAnimationFrame((nextTimestamp) => animateRef.current(nextTimestamp))
      }
    }
  }, [animationDuration, easing, isPlaying, isHovered, loop, onAnimationComplete, pauseOnHover])

  useEffect(() => {
    if (!imagesLoaded || shouldReduceMotion) return

    if (isPlaying && !(pauseOnHover && isHovered)) {
      animationRef.current = requestAnimationFrame((timestamp) => animateRef.current(timestamp))
    }

    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isPlaying, isHovered, imagesLoaded, shouldReduceMotion, pauseOnHover])

  const handlePlay = () => setIsPlaying(true)
  const handlePause = () => setIsPlaying(false)
  const handleReset = () => {
    startTimeRef.current = null
    setCurrentFrameIndex(0)
  }

  if (shouldReduceMotion || !imagesLoaded) {
    return (
      <div className={`relative ${className}`}>
        <img
          src={KEYFRAMES[0]}
          alt="FeedMe Logo"
          className="w-full h-full object-contain"
        />
      </div>
    )
  }

  return (
    <motion.div
      className={`relative ${className}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        width={300}
        height={300}
      />

      {/* Fallback for non-canvas browsers */}
      <noscript>
        <img
          src={KEYFRAMES[currentFrameIndex]}
          alt="FeedMe Logo"
          className="absolute inset-0 w-full h-full object-contain"
        />
      </noscript>

      {/* Optional controls for debugging */}
      {process.env.NODE_ENV === 'development' && (
        <div className="absolute bottom-0 left-0 right-0 flex justify-center gap-2 p-2 bg-black/50">
          <button
            onClick={handlePlay}
            className="px-2 py-1 text-xs text-white bg-blue-500 rounded"
            disabled={isPlaying}
          >
            Play
          </button>
          <button
            onClick={handlePause}
            className="px-2 py-1 text-xs text-white bg-red-500 rounded"
            disabled={!isPlaying}
          >
            Pause
          </button>
          <button
            onClick={handleReset}
            className="px-2 py-1 text-xs text-white bg-gray-500 rounded"
          >
            Reset
          </button>
          <span className="px-2 py-1 text-xs text-white">
            Frame: {currentFrameIndex + 1}/{KEYFRAMES.length}
          </span>
        </div>
      )}
    </motion.div>
  )
}
