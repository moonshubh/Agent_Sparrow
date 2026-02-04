/**
 * Crystalline Animation Library
 * Shared animation configurations for the Agent Sparrow UI
 * Uses Framer Motion for React components
 */

import { Variants, Transition } from "framer-motion";

// ============================================
// Animation Timing Functions
// ============================================
export const easings = {
  crystalForm: [0.4, 0.0, 0.2, 1],
  neuralPulse: [0.7, 0.0, 0.3, 1],
  smooth: [0.25, 0.1, 0.25, 1],
  bounce: [0.68, -0.55, 0.265, 1.55],
} as const;

// ============================================
// Tool Evidence Card Animations
// ============================================
export const crystalCardAnimation: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.8,
    filter: "blur(10px)",
    y: 20,
  },
  visible: {
    opacity: 1,
    scale: 1,
    filter: "blur(0px)",
    y: 0,
    transition: {
      duration: 0.6,
      ease: easings.crystalForm,
    },
  },
  hover: {
    scale: 1.02,
    boxShadow: "0 0 30px rgba(255, 215, 0, 0.2)",
    transition: {
      duration: 0.2,
      ease: easings.smooth,
    },
  },
  tap: {
    scale: 0.98,
    transition: {
      duration: 0.1,
      ease: easings.smooth,
    },
  },
};

// Stagger children for list animations
export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
};

// ============================================
// Neural Network / Memory Animations
// ============================================
export const neuralPulseAnimation: Variants = {
  idle: {
    boxShadow: "0 0 10px rgba(255, 215, 0, 0.2)",
  },
  pulse: {
    boxShadow: [
      "0 0 10px rgba(255, 215, 0, 0.2)",
      "0 0 30px rgba(255, 215, 0, 0.4)",
      "0 0 50px rgba(255, 215, 0, 0.3)",
      "0 0 10px rgba(255, 215, 0, 0.2)",
    ],
    transition: {
      duration: 2,
      ease: easings.neuralPulse,
      repeat: Infinity,
    },
  },
};

export const memoryNodeAnimation: Variants = {
  dormant: {
    scale: 0.8,
    opacity: 0.3,
  },
  retrieved: {
    scale: [0.8, 1.2, 1],
    opacity: [0.3, 1, 0.8],
    transition: {
      duration: 0.6,
      ease: easings.bounce,
    },
  },
  writing: {
    scale: [1, 1.3, 1.1],
    opacity: 1,
    rotate: [0, 180, 360],
    transition: {
      duration: 0.8,
      ease: easings.crystalForm,
    },
  },
};

// ============================================
// Thinking / Reasoning Animations
// ============================================
export const thinkingDotsAnimation: Variants = {
  idle: { opacity: 0 },
  thinking: {
    opacity: 1,
    transition: {
      staggerChildren: 0.2,
    },
  },
};

export const thinkingDotAnimation: Variants = {
  idle: {
    y: 0,
    opacity: 0.3,
  },
  thinking: {
    y: [-5, -10, -5, 0],
    opacity: [0.3, 1, 1, 0.3],
    transition: {
      duration: 1.5,
      ease: easings.smooth,
      repeat: Infinity,
    },
  },
};

// ============================================
// Progress & Loading Animations
// ============================================
export const progressBarAnimation: Variants = {
  empty: {
    scaleX: 0,
    originX: 0,
  },
  filling: (progress: number) => ({
    scaleX: progress / 100,
    transition: {
      duration: 0.3,
      ease: easings.smooth,
    },
  }),
  complete: {
    scaleX: 1,
    background: "linear-gradient(90deg, #00D4FF 0%, #FFD700 100%)",
    transition: {
      duration: 0.5,
      ease: easings.crystalForm,
    },
  },
};

// ============================================
// Timeline Animations
// ============================================
export const timelineNodeAnimation: Variants = {
  future: {
    scale: 0.95,
    opacity: 0.35,
  },
  current: {
    scale: 1,
    opacity: 1,
    transition: {
      duration: 0.2,
      ease: easings.smooth,
    },
  },
  past: {
    scale: 1,
    opacity: 0.65,
    transition: {
      duration: 0.2,
      ease: easings.smooth,
    },
  },
};

export const timelineBranchAnimation: Variants = {
  hidden: {
    pathLength: 0,
    opacity: 0,
  },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: {
      pathLength: {
        duration: 0.8,
        ease: easings.crystalForm,
      },
      opacity: {
        duration: 0.3,
      },
    },
  },
};

// ============================================
// Model Selection Animations
// ============================================
export const modelBadgeAnimation: Variants = {
  idle: {
    scale: 1,
    rotate: 0,
  },
  selected: {
    scale: [1, 1.2, 1.1],
    rotate: [0, 5, -5, 0],
    transition: {
      duration: 0.4,
      ease: easings.bounce,
    },
  },
  fallback: {
    scale: [1, 0.9, 1],
    opacity: [1, 0.7, 1],
    transition: {
      duration: 0.3,
      ease: easings.smooth,
    },
  },
};

// ============================================
// Interrupt Card Animations
// ============================================
export const interruptAnimation: Variants = {
  hidden: {
    scale: 0.5,
    opacity: 0,
    rotateX: -90,
  },
  visible: {
    scale: 1,
    opacity: 1,
    rotateX: 0,
    transition: {
      duration: 0.5,
      ease: easings.bounce,
    },
  },
  urgent: {
    scale: [1, 1.05, 1],
    boxShadow: [
      "0 0 20px rgba(255, 71, 87, 0.3)",
      "0 0 40px rgba(255, 71, 87, 0.5)",
      "0 0 20px rgba(255, 71, 87, 0.3)",
    ],
    transition: {
      duration: 1,
      ease: easings.smooth,
      repeat: Infinity,
    },
  },
};

// ============================================
// Particle Effects
// ============================================
export const particleAnimation: Variants = {
  spawn: {
    scale: 0,
    opacity: 0,
    x: 0,
    y: 0,
  },
  drift: {
    scale: [0, 1, 0.5],
    opacity: [0, 0.8, 0],
    x: Math.random() * 100 - 50,
    y: -100,
    transition: {
      duration: 2 + Math.random() * 2,
      ease: easings.smooth,
    },
  },
};

// ============================================
// Glass Morphism Effects
// ============================================
export const glassRevealAnimation: Variants = {
  hidden: {
    backdropFilter: "blur(0px)",
    background: "rgba(10, 14, 39, 0)",
    border: "1px solid rgba(0, 212, 255, 0)",
  },
  visible: {
    backdropFilter: "blur(12px)",
    background: "rgba(10, 14, 39, 0.6)",
    border: "1px solid rgba(0, 212, 255, 0.2)",
    transition: {
      duration: 0.5,
      ease: easings.smooth,
    },
  },
};

// ============================================
// Message Action Menu
// ============================================
export const actionMenuAnimation: Variants = {
  hidden: {
    scale: 0,
    opacity: 0,
    rotateZ: -180,
  },
  visible: {
    scale: 1,
    opacity: 1,
    rotateZ: 0,
    transition: {
      type: "spring",
      damping: 20,
      stiffness: 300,
    },
  },
};

export const actionButtonAnimation: Variants = {
  hidden: {
    scale: 0,
    opacity: 0,
  },
  visible: (index: number) => ({
    scale: 1,
    opacity: 1,
    transition: {
      delay: index * 0.05,
      duration: 0.3,
      ease: easings.bounce,
    },
  }),
  hover: {
    scale: 1.1,
    boxShadow: "0 0 15px rgba(255, 215, 0, 0.4)",
    transition: {
      duration: 0.2,
    },
  },
};

// ============================================
// Utility Functions
// ============================================

/**
 * Creates a shimmer loading effect
 */
export const shimmerAnimation: Variants = {
  shimmer: {
    backgroundPosition: ["200% 0", "-200% 0"],
    transition: {
      duration: 2,
      ease: "linear",
      repeat: Infinity,
    },
  },
};

/**
 * Creates a gentle float animation for hovering elements
 */
export const floatAnimation: Variants = {
  float: {
    y: [0, -10, 0],
    transition: {
      duration: 3,
      ease: easings.smooth,
      repeat: Infinity,
    },
  },
};

/**
 * Creates a crystallization effect for element appearance
 */
export const crystallizeAnimation: Variants = {
  liquid: {
    filter: "blur(8px) hue-rotate(0deg)",
    scale: 1.1,
    opacity: 0.7,
  },
  solid: {
    filter: "blur(0px) hue-rotate(360deg)",
    scale: 1,
    opacity: 1,
    transition: {
      duration: 0.8,
      ease: easings.crystalForm,
    },
  },
};

// ============================================
// Composite Animations
// ============================================

/**
 * Combined animation for tool execution flow
 */
export const toolExecutionAnimation = {
  preparing: {
    opacity: 0.6,
    scale: 0.95,
  },
  executing: {
    opacity: 1,
    scale: 1,
    transition: {
      duration: 0.3,
      ease: easings.smooth,
    },
  },
  complete: {
    opacity: 1,
    scale: [1, 1.05, 1],
    transition: {
      scale: {
        duration: 0.5,
        ease: easings.bounce,
      },
    },
  },
  error: {
    opacity: 1,
    scale: 1,
    x: [0, -5, 5, -5, 5, 0],
    transition: {
      x: {
        duration: 0.4,
        ease: easings.smooth,
      },
    },
  },
};

/**
 * Quota meter filling animation
 */
export const quotaMeterAnimation: Variants = {
  healthy: {
    background: "linear-gradient(90deg, #00D4FF 0%, #00D4FF 100%)",
  },
  warning: (usage: number) => ({
    background: `linear-gradient(90deg, #00D4FF 0%, #FFBF00 ${usage}%)`,
    transition: {
      duration: 0.5,
      ease: easings.smooth,
    },
  }),
  critical: {
    background: "linear-gradient(90deg, #FFBF00 0%, #FF4757 100%)",
    animation: "pulse 1s ease-in-out infinite",
  },
};

// Export animation presets for easy use
export const animationPresets = {
  fadeIn: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },
  slideUp: {
    initial: { y: 20, opacity: 0 },
    animate: { y: 0, opacity: 1 },
    exit: { y: -20, opacity: 0 },
  },
  slideIn: {
    initial: { x: -20, opacity: 0 },
    animate: { x: 0, opacity: 1 },
    exit: { x: 20, opacity: 0 },
  },
  scaleIn: {
    initial: { scale: 0.9, opacity: 0 },
    animate: { scale: 1, opacity: 1 },
    exit: { scale: 0.9, opacity: 0 },
  },
  springIn: {
    initial: { scale: 0 },
    animate: {
      scale: 1,
      transition: {
        type: "spring",
        damping: 20,
        stiffness: 300,
      },
    },
    exit: { scale: 0 },
  },
};
