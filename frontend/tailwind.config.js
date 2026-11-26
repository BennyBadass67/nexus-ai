/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter Variable", "Inter", "Segoe UI Variable", "Segoe UI", "system-ui", "sans-serif"] },
      colors: { nx: { blue: "#5aa9ff", ice: "#bfe0ff", ink: "#070b14" } },
      keyframes: {
        rise: { "0%": { opacity: 0, transform: "translateY(8px)" }, "100%": { opacity: 1, transform: "none" } },
        blink: { "50%": { opacity: 0.2 } },
        pop: { "0%": { opacity: 0, transform: "scale(.96) translateY(4px)" }, "100%": { opacity: 1, transform: "none" } },
        fade: { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        drift1: { "50%": { transform: "translate(8vw,6vh) scale(1.15)" } },
        drift2: { "50%": { transform: "translate(-10vw,-8vh) scale(1.1)" } },
        drift3: { "50%": { transform: "translate(-6vw,8vh) scale(1.2)" } },
        shimmer: { "0%": { backgroundPosition: "200% 0" }, "100%": { backgroundPosition: "-200% 0" } },
      },
      animation: { rise: "rise .45s cubic-bezier(.2,.8,.2,1) both", blink: "blink 1s infinite", pop: "pop .25s cubic-bezier(.2,.9,.3,1.2) both", fade: "fade .2s ease-out both", drift1: "drift1 24s ease-in-out infinite", drift2: "drift2 30s ease-in-out infinite", drift3: "drift3 36s ease-in-out infinite", shimmer: "shimmer 2s linear infinite" },
    },
  },
  plugins: [],
};
