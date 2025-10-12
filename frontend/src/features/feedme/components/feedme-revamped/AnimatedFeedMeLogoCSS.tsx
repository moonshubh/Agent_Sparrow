'use client'

import React, { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import styles from './AnimatedFeedMeLogoCSS.module.css'

interface AnimatedFeedMeLogoCSSProps {
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

export default function AnimatedFeedMeLogoCSS({
  className = '',
  animationDuration = 2000,
  loop = true,
  autoPlay = true,
}: AnimatedFeedMeLogoCSSProps) {
  const shouldReduceMotion = useReducedMotion()
  const [imagesLoaded, setImagesLoaded] = useState(false)

  useEffect(() => {
    const loadImages = async () => {
      const promises = KEYFRAMES.map((src) => {
        return new Promise((resolve, reject) => {
          const img = new Image()
          img.onload = resolve
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
    }

    loadImages()
  }, [])

  if (shouldReduceMotion || !imagesLoaded) {
    return (
      <div className={`${styles.staticLogo} ${className}`}>
        <img src={KEYFRAMES[0]} alt="FeedMe Logo" />
      </div>
    )
  }

  const animationStyle = {
    '--animation-duration': `${animationDuration}ms`,
    '--frame-count': KEYFRAMES.length,
  } as React.CSSProperties

  return (
    <motion.div
      className={`${styles.animatedLogo} ${className}`}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      style={animationStyle}
    >
      <div className={styles.frameContainer}>
        {KEYFRAMES.map((src, index) => (
          <img
            key={index}
            src={src}
            alt={`FeedMe Frame ${index + 1}`}
            className={`${styles.frame} ${autoPlay ? styles.playing : ''} ${
              loop ? styles.loop : ''
            }`}
            style={{
              '--frame-index': index,
              animationDelay: `${(animationDuration / KEYFRAMES.length) * index}ms`,
            } as React.CSSProperties}
          />
        ))}
      </div>
    </motion.div>
  )
}