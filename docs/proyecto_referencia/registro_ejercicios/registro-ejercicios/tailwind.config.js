/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      colors: {
        'semaforo-green': '#22c55e',
        'semaforo-yellow': '#eab308',
        'semaforo-red': '#ef4444',
      },
    },
  },
  plugins: [],
}
