'use client'

import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import Image from 'next/image'

interface EnhancedAnimatedLogoProps {
  className?: string
  animationDuration?: number
  loop?: boolean
  autoPlay?: boolean
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

export default function EnhancedAnimatedLogo({
  className = '',
  animationDuration = 6000, // Increased from 2400 to 6000 for slower transitions
  loop = true,
  autoPlay = true,
}: EnhancedAnimatedLogoProps) {
  const [currentFrame, setCurrentFrame] = useState(0)
  const [isPlaying, setIsPlaying] = useState(autoPlay)
  const [imagesLoaded, setImagesLoaded] = useState(false)
  const shouldReduceMotion = useReducedMotion()

  // Slower frame duration for smoother transitions
  const frameDuration = animationDuration / KEYFRAMES.length

  useEffect(() => {
    const loadImages = async () => {
      const promises = KEYFRAMES.map((src) => {
        return new Promise<void>((resolve, reject) => {
          const img = new window.Image()
          img.onload = () => resolve()
          img.onerror = reject
          img.src = src
        })
      })

      try {
        await Promise.all(promises)
        setImagesLoaded(true)
      } catch (error) {
        console.error('Error loading keyframe images:', error)
        setImagesLoaded(true)
      }
    }

    loadImages()
  }, [])

  useEffect(() => {
    if (!isPlaying || shouldReduceMotion || !imagesLoaded) return

    const interval = setInterval(() => {
      setCurrentFrame((prev) => {
        const nextFrame = prev + 1

        if (nextFrame >= KEYFRAMES.length) {
          if (loop) {
            return 0
          } else {
            setIsPlaying(false)
            return prev
          }
        }

        return nextFrame
      })
    }, frameDuration)

    return () => clearInterval(interval)
  }, [isPlaying, frameDuration, loop, shouldReduceMotion, imagesLoaded])

  if (!imagesLoaded) {
    return (
      <motion.div
        className={`relative ${className}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <div className="flex items-center justify-center w-full h-full">
          <div className="text-white/50 text-lg animate-pulse">Loading...</div>
        </div>
      </motion.div>
    )
  }

  if (shouldReduceMotion) {
    return (
      <motion.div
        className={`relative ${className}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <Image
          src={KEYFRAMES[0]}
          alt="FeedMe"
          fill
          className="object-contain"
          priority
        />
      </motion.div>
    )
  }

  return (
    <motion.div
      className={`relative ${className}`}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{
        opacity: 1,
        scale: 1,
        y: [0, -12, 0], // Gentle floating animation
      }}
      transition={{
        opacity: { duration: 0.8 },
        scale: { duration: 0.8, ease: "easeOut" },
        y: {
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut"
        }
      }}
    >
      {/* Dynamic glow effect */}
      <div className="absolute inset-0 -z-10">
        <motion.div
          className="absolute inset-0 rounded-full blur-3xl"
          style={{
            background: "radial-gradient(circle, rgba(251, 191, 36, 0.2) 0%, rgba(251, 146, 60, 0.1) 50%, transparent 100%)",
          }}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.6, 0.3],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      </div>

      {/* Particle effects */}
      <div className="absolute inset-0 pointer-events-none">
        {[...Array(6)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-1 h-1 bg-yellow-400/60 rounded-full"
            initial={{
              x: "50%",
              y: "50%",
            }}
            animate={{
              x: `${50 + Math.cos(i * 60 * Math.PI / 180) * 80}%`,
              y: `${50 + Math.sin(i * 60 * Math.PI / 180) * 80}%`,
              opacity: [0, 1, 0],
              scale: [0, 1.5, 0],
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              delay: i * 0.5,
              ease: "easeOut",
            }}
          />
        ))}
      </div>

      {/* Main logo with smooth transitions */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentFrame}
          className="relative w-full h-full"
          initial={{
            opacity: 0,
            scale: 0.95,
            filter: "blur(8px)",
          }}
          animate={{
            opacity: 1,
            scale: 1,
            filter: "blur(0px)",
          }}
          exit={{
            opacity: 0,
            scale: 1.05,
            filter: "blur(8px)",
          }}
          transition={{
            duration: frameDuration / 1500, // Slower transition between frames
            ease: [0.4, 0, 0.2, 1], // Custom easing for smooth transitions
          }}
        >
          {/* Shadow effect */}
          <div className="absolute inset-0 translate-y-2 opacity-30 blur-xl">
            <Image
              src={KEYFRAMES[currentFrame]}
              alt=""
              fill
              className="object-contain"
            />
          </div>

          {/* Main image */}
          <Image
            src={KEYFRAMES[currentFrame]}
            alt="FeedMe"
            fill
            className="object-contain drop-shadow-2xl"
            priority={currentFrame === 0}
          />

          {/* Shimmer effect */}
          <motion.div
            className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent"
            animate={{
              x: ["-100%", "100%"],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              repeatDelay: 4,
              ease: "easeInOut",
            }}
            style={{
              maskImage: "linear-gradient(to right, transparent, black, transparent)",
              WebkitMaskImage: "linear-gradient(to right, transparent, black, transparent)",
            }}
          />
        </motion.div>
      </AnimatePresence>

    </motion.div>
  )
}