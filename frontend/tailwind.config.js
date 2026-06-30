/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Monochrome, white-dominant palette. `ink` is text (#0A0A0A) — named
        // `ink` rather than `text` to avoid clashing with Tailwind's text-* utils.
        ground: '#FFFFFF', // chat / app surface (pure white where contrast helps)
        'ground-2': '#FAFAFA', // app background, sidebar, empty canvas
        bubble: '#F4F4F4', // user message bubble + code block background
        'bubble-hover': '#ECECEC',
        hover: '#F3F3F3', // generic hover fill (rows, New chat)
        ink: '#0A0A0A', // primary text / near-black accent
        muted: '#6B7280', // secondary text, tok/s, captions
        line: '#ECECEC', // 1px hairline borders
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          '"Cascadia Code"',
          '"Cascadia Mono"',
          'Consolas',
          '"SF Mono"',
          'Menlo',
          'monospace',
        ],
      },
      borderRadius: {
        control: '8px',
        bubble: '10px',
        card: '12px',
      },
      maxWidth: {
        content: '720px',
      },
      boxShadow: {
        // The ONLY shadow in the app — on the composer.
        composer:
          '0 1px 2px rgba(10,10,10,0.04), 0 4px 14px rgba(10,10,10,0.05)',
      },
      keyframes: {
        caret: { '0%,49%': { opacity: '1' }, '50%,100%': { opacity: '0' } },
        dotPulse: {
          '0%,80%,100%': { opacity: '0.25', transform: 'translateY(0)' },
          '40%': { opacity: '1', transform: 'translateY(-1px)' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        fadeInFast: { from: { opacity: '0' }, to: { opacity: '1' } },
      },
      animation: {
        caret: 'caret 1.05s step-end infinite',
        'dot-pulse': 'dotPulse 1.2s ease-in-out infinite',
        'fade-in': 'fadeIn 0.28s ease-out both',
        'fade-in-fast': 'fadeInFast 0.15s ease-out both',
      },
    },
  },
  plugins: [],
}
