import React from 'react';

interface ShinyTextProps {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
  /**
   * Adds a subtle Mailbird blue gradient under the shine.
   * Enabled by default to match brand accent.
   */
  accentBlue?: boolean;
}

const ShinyText: React.FC<ShinyTextProps> = ({ text, disabled = false, speed = 5, className = '', accentBlue = true }) => {
  const animationDuration = `${speed}s`;

  // Base subtle Mailbird blue gradient (behind the moving shine)
  const accentGradient = accentBlue
    ? 'linear-gradient(90deg, rgba(56,182,255,0.9) 0%, rgba(0,149,255,0.9) 100%)'
    : 'linear-gradient(90deg, rgba(181,181,181,0.85) 0%, rgba(181,181,181,0.85) 100%)';

  // Moving specular highlight
  const shineGradient = 'linear-gradient(120deg, rgba(255,255,255,0) 40%, rgba(255,255,255,0.85) 50%, rgba(255,255,255,0) 60%)';

  return (
    <div
      className={`text-transparent bg-clip-text inline-block ${disabled ? '' : 'animate-shine'} ${className}`}
      style={{
        backgroundImage: `${accentGradient}, ${shineGradient}`,
        backgroundSize: `100% 100%, 200% 100%`,
        backgroundRepeat: 'no-repeat',
        WebkitBackgroundClip: 'text',
        animationDuration,
      }}
    >
      {text}
    </div>
  );
};

export default ShinyText;

// tailwind.config.js
// module.exports = {
//   theme: {
//     extend: {
//       keyframes: {
//         shine: {
//           '0%': { 'background-position': '100%' },
//           '100%': { 'background-position': '-100%' },
//         },
//       },
//       animation: {
//         shine: 'shine 5s linear infinite',
//       },
//     },
//   },
//   plugins: [],
// };
