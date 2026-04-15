/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef5ff',
          100: '#d9e8ff',
          200: '#bcd7ff',
          300: '#8ebeff',
          400: '#599aff',
          500: '#3374ff',
          600: '#1b52f5',
          700: '#143de1',
          800: '#1733b6',
          900: '#19308f',
          950: '#141f57',
        },
        surface: {
          50: '#f8f9fc',
          100: '#f0f2f7',
          200: '#e4e7ef',
          300: '#cdd3e0',
          400: '#9aa3b8',
          500: '#6b7690',
          600: '#555e74',
          700: '#454c5f',
          800: '#3a4050',
          900: '#343845',
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
};
