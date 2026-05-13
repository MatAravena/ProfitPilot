import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0A0A0F',
        surface: '#111118',
        'surface-2': '#1A1A24',
        border: '#1E293B',
        primary: '#2563EB',
        'primary-hover': '#3B82F6',
        accent: '#F97316',
        'accent-hover': '#FB923C',
        text: '#E2E8F0',
        'text-muted': '#64748B',
        success: '#22C55E',
        danger: '#EF4444',
        warning: '#F59E0B',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)',
        'card-hover': '0 4px 6px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.6)',
        glow: '0 0 20px rgba(37,99,235,0.15)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out',
      },
    },
  },
  plugins: [],
}

export default config
