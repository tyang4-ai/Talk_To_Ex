/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tinder vertical gradient stops (spec §2 — locked)
        tinder: {
          start: "#FD297B",
          mid: "#FF5864",
          end: "#FF655B",
        },
        ink: "#1F1A24", // bold display ink over soft neutral
        muted: "#6B6470",
        neutralbg: "#FBF7F4", // soft neutral background
        card: "#FFFFFF",
      },
      fontFamily: {
        // Poppins for tight bold display, Inter for body (spec §2)
        display: ['"Poppins"', '"Inter"', "system-ui", "sans-serif"],
        body: ['"Inter"', "system-ui", "sans-serif"],
      },
      fontSize: {
        // Tight, bold display scale — mobile-first
        "display-xl": ["3.25rem", { lineHeight: "1.02", letterSpacing: "-0.03em" }],
        "display-lg": ["2.5rem", { lineHeight: "1.04", letterSpacing: "-0.025em" }],
        "display-md": ["1.875rem", { lineHeight: "1.08", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        pill: "9999px",
        card: "1.75rem",
        avatar: "2rem",
      },
      boxShadow: {
        card: "0 18px 50px -12px rgba(253, 41, 123, 0.35)",
        pill: "0 10px 24px -8px rgba(255, 88, 100, 0.55)",
        soft: "0 8px 30px -10px rgba(31, 26, 36, 0.18)",
      },
      backgroundImage: {
        "tinder-gradient":
          "linear-gradient(180deg, #FD297B 0%, #FF5864 55%, #FF655B 100%)",
        "tinder-gradient-135":
          "linear-gradient(135deg, #FD297B 0%, #FF5864 55%, #FF655B 100%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-heart": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.12)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out both",
        "pulse-heart": "pulse-heart 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
