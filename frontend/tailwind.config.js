/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx}",
    "./src/app/components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: 'var(--primary-color)',
        player1: 'var(--player1-color)',
        player2: 'var(--player2-color)',
        background: 'var(--background-color)',
        card: 'var(--card-background)',
        textColor: 'var(--text-color)',
        border: 'var(--border-color)',
      },
    },
  },
  plugins: [],
}; 