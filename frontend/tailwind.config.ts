import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";
import typography from "@tailwindcss/typography";
import plugin from "tailwindcss/plugin";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/shared/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/services/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/state/**/*.{js,ts,jsx,tsx,mdx}",
    "*.{js,ts,jsx,tsx,mdx}",
  ],
  safelist: [
    // Ensure mb-blue-300 variants are always generated
    "bg-mb-blue-300",
    "hover:bg-mb-blue-300",
    "hover:bg-mb-blue-300/10",
    "hover:bg-mb-blue-300/15",
    "hover:bg-mb-blue-300/20",
    "focus:bg-mb-blue-300/20",
    "ring-mb-blue-300",
    "focus-visible:ring-mb-blue-300",
    "text-mb-blue-400",
    "text-mb-blue-500",
    "hover:text-mb-blue-400",
    // Ensure arbitrary width used by beams is generated
    "w-[2px]",
  ],
  theme: {
    extend: {
      /* ============================================================
		   DARK ACADEMIA THEME EXTENSION
		   Warm, scholarly aesthetic with organic natural elements
		   ============================================================ */
      fontFamily: {
        // Primary: System sans-serif for native look
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        serif: ['"Lora"', '"Source Serif Pro"', "Georgia", "serif"],
        // Fallback sans for UI elements
        ui: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: ['"JetBrains Mono"', '"Fira Code"', "ui-monospace", "monospace"],
      },
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },

        // === DARK ACADEMIA COLOR SCALES ===
        // Terracotta - Primary accent (fireplace warmth)
        terracotta: {
          300: "hsl(var(--terracotta-300, 200.4 98% 39.4%))",
          400: "hsl(var(--terracotta-400, 200.4 98% 45%))",
          500: "hsl(var(--terracotta-500, 200.4 98% 38%))",
          600: "hsl(var(--terracotta-600, 200.4 98% 28%))",
        },
        // Sage - Secondary accent (nature's wisdom)
        sage: {
          300: "hsl(var(--sage-300, 135 18% 65%))",
          400: "hsl(var(--sage-400, 135 22% 50%))",
          500: "hsl(var(--sage-500, 135 25% 40%))",
          600: "hsl(var(--sage-600, 135 20% 30%))",
        },
        // Gold - Tertiary accent (candlelight)
        gold: {
          300: "hsl(var(--gold-300, 40 50% 70%))",
          400: "hsl(var(--gold-400, 40 60% 55%))",
          500: "hsl(var(--gold-500, 40 65% 45%))",
          600: "hsl(var(--gold-600, 40 60% 35%))",
        },
        // Stone - Neutral accent
        stone: {
          300: "hsl(var(--stone-300, 25 5% 65%))",
          400: "hsl(var(--stone-400, 25 6% 50%))",
          500: "hsl(var(--stone-500, 25 8% 35%))",
          600: "hsl(var(--stone-600, 25 10% 25%))",
        },
        // Cream - Text colors
        cream: {
          50: "hsl(var(--cream-50, 40 20% 97%))",
          100: "hsl(var(--cream-100, 40 15% 92%))",
        },

        // Legacy compatibility (warm-shifted)
        "mb-blue-300": "hsl(var(--terracotta-300, 200.4 98% 39.4%))",
        "mb-blue-400": "hsl(var(--terracotta-400, 200.4 98% 45%))",
        "mb-blue-500": "hsl(var(--primary))",

        // Neutral base
        neutral: {
          base: "hsl(var(--neutral-base))",
          card: "hsl(var(--neutral-card))",
        },
        // Severity colors (earth-toned)
        severity: {
          critical: "hsl(var(--critical))",
          high: "hsl(var(--high))",
          medium: "hsl(var(--medium))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        chart: {
          "1": "hsl(var(--terracotta-500, 200.4 98% 38%))",
          "2": "hsl(var(--sage-500, 135 25% 40%))",
          "3": "hsl(var(--gold-500, 40 65% 45%))",
          "4": "hsl(var(--stone-400, 25 6% 50%))",
          "5": "hsl(var(--terracotta-300, 200.4 98% 39.4%))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
        "code-block": "hsl(var(--code-block-bg))",
        chat: {
          background: "hsl(var(--chat-background))",
          "user-bg": "hsl(var(--chat-user-bg))",
          "user-text": "hsl(var(--chat-user-text))",
          "agent-bg": "hsl(var(--chat-agent-bg))",
          "agent-text": "hsl(var(--chat-agent-text))",
          "input-bg": "hsl(var(--chat-input-bg))",
          "input-text": "hsl(var(--chat-input-text))",
          metadata: "hsl(var(--chat-metadata))",
        },
      },
      // Soft organic border radius
      borderRadius: {
        "organic-sm": "var(--radius-sm, 8px)",
        organic: "var(--radius-md, 12px)",
        "organic-lg": "var(--radius-lg, 16px)",
        "organic-xl": "var(--radius-xl, 20px)",
        "organic-2xl": "var(--radius-2xl, 24px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      // Typography scale
      fontSize: {
        "academia-xs": [
          "var(--text-xs, 0.8125rem)",
          { lineHeight: "var(--leading-normal)" },
        ],
        "academia-sm": [
          "var(--text-sm, 0.9375rem)",
          { lineHeight: "var(--leading-normal)" },
        ],
        "academia-base": [
          "var(--text-base, 1.0625rem)",
          { lineHeight: "var(--leading-normal)" },
        ],
        "academia-lg": [
          "var(--text-lg, 1.1875rem)",
          { lineHeight: "var(--leading-snug)" },
        ],
        "academia-xl": [
          "var(--text-xl, 1.375rem)",
          { lineHeight: "var(--leading-tight)" },
        ],
        "academia-2xl": [
          "var(--text-2xl, 1.625rem)",
          { lineHeight: "var(--leading-tight)" },
        ],
      },
      // Warm shadows
      boxShadow: {
        "academia-sm": "0 2px 4px hsla(30, 15%, 5%, 0.12)",
        "academia-md":
          "0 4px 8px hsla(30, 15%, 5%, 0.1), 0 2px 4px hsla(30, 15%, 5%, 0.06)",
        "academia-lg":
          "0 8px 24px hsla(30, 15%, 5%, 0.12), 0 4px 8px hsla(30, 15%, 5%, 0.08)",
        "terracotta-glow": "0 0 20px hsla(200.4, 98%, 39.4%, 0.25)",
        "sage-glow": "0 0 20px hsla(135, 25%, 40%, 0.2)",
        "gold-glow": "0 0 20px hsla(40, 65%, 45%, 0.25)",
      },
      keyframes: {
        shine: {
          "0%": { backgroundPosition: "200% 0%" },
          "100%": { backgroundPosition: "-200% 0%" },
        },
        "accordion-down": {
          from: {
            height: "0",
          },
          to: {
            height: "var(--radix-accordion-content-height)",
          },
        },
        "accordion-up": {
          from: {
            height: "var(--radix-accordion-content-height)",
          },
          to: {
            height: "0",
          },
        },
      },
      animation: {
        shine: "shine 5s linear infinite",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [
    tailwindcssAnimate,
    typography,
    plugin(({ addUtilities }) => {
      addUtilities({
        ".animation-delay-0": { "animation-delay": "0ms" },
        ".animation-delay-200": { "animation-delay": "200ms" },
        ".animation-delay-400": { "animation-delay": "400ms" },
      });
    }),
  ],
};
export default config;
