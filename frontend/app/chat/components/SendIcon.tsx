import React from 'react'

interface SendIconProps {
  className?: string
}

export function SendIcon({ className = "w-5 h-5" }: SendIconProps) {
  return (
    <svg 
      className={className} 
      viewBox="0 0 24 24" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
    >
      <path 
        d="M7 11L12 6L17 11M12 18V6" 
        stroke="currentColor" 
        strokeWidth="2" 
        strokeLinecap="round" 
        strokeLinejoin="round"
      />
    </svg>
  )
}