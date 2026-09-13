/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep command-centre navy. `surface` is the page ground, `raised` the
        // translucent glass panels sit on top of it.
        surface: {
          DEFAULT: '#040a14',
          deep: '#02060d',
          raised: 'rgba(12, 26, 44, 0.72)',
          solid: '#0a1524',
          border: 'rgba(56, 189, 248, 0.18)',
          hairline: 'rgba(56, 189, 248, 0.10)',
        },
        // Holographic accent ramp used for chrome, glows and active states.
        hud: {
          DEFAULT: '#22d3ee',
          bright: '#67e8f9',
          dim: '#0e7490',
          glow: 'rgba(34, 211, 238, 0.35)',
        },
        tier: {
          normal: '#22c55e',
          watch: '#eab308',
          warning: '#f97316',
          critical: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Rajdhani', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        hud: '0 0 0 1px rgba(56, 189, 248, 0.12), 0 18px 40px -24px rgba(0, 0, 0, 0.9)',
        'hud-glow': '0 0 18px -2px rgba(34, 211, 238, 0.45)',
        'inset-top': 'inset 0 1px 0 0 rgba(103, 232, 249, 0.18)',
      },
      keyframes: {
        'hud-sweep': {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '15%': { opacity: '0.6' },
          '100%': { transform: 'translateY(400%)', opacity: '0' },
        },
        'hud-pulse': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.45', transform: 'scale(0.82)' },
        },
        'hud-spin': {
          to: { transform: 'rotate(360deg)' },
        },
        'hud-flicker': {
          '0%, 100%': { opacity: '0.85' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'hud-sweep': 'hud-sweep 5.5s linear infinite',
        'hud-pulse': 'hud-pulse 1.8s ease-in-out infinite',
        'hud-spin': 'hud-spin 14s linear infinite',
        'hud-flicker': 'hud-flicker 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
