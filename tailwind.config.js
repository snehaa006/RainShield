/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Near-black ground with cards lifted by a few percent of white.
        surface: {
          DEFAULT: '#08090b',
          deep: '#000000',
          raised: '#111316',
          hover: '#171a1e',
          border: 'rgba(255, 255, 255, 0.09)',
          hairline: 'rgba(255, 255, 255, 0.06)',
        },
        // System blue for selection, the way iOS uses it.
        accent: {
          DEFAULT: '#0a84ff',
          soft: 'rgba(10, 132, 255, 0.15)',
        },
        tier: {
          normal: '#30d158',
          watch: '#ffd60a',
          warning: '#ff9f0a',
          critical: '#ff453a',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        card: '14px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(0, 0, 0, 0.6), 0 8px 24px -16px rgba(0, 0, 0, 0.9)',
        control: '0 1px 2px rgba(0, 0, 0, 0.5)',
      },
      keyframes: {
        'soft-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        'soft-pulse': 'soft-pulse 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
