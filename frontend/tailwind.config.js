/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Airbnb design system (VoltAgent DESIGN.md). Rausch is the single warm
        // accent — used sparingly on a clean white canvas. The `tinder`/`oxblood`
        // keys alias Rausch so legacy accent classes re-theme without churn.
        rausch: { DEFAULT: "#ff385c", active: "#e00b41", disabled: "#ffd1da" },
        tinder: { start: "#ff385c", mid: "#ff385c", end: "#e00b41" },
        oxblood: { DEFAULT: "#ff385c", deep: "#e00b41" },

        ink: "#222222", // primary text / headlines
        body: "#3f3f3f", // secondary running text
        muted: "#6a6a6a", // subtitles, inactive
        mutedsoft: "#929292", // disabled links

        canvas: "#ffffff", // default page background
        surfacesoft: "#f7f7f7", // hover / disabled field bg
        surfacestrong: "#f2f2f2", // circular icon buttons
        neutralbg: "#ffffff", // legacy alias -> white canvas
        card: "#ffffff", // card surface

        hairline: "#dddddd", // 1px borders
        hairlinesoft: "#ebebeb", // lighter dividers
        borderstrong: "#c1c1c1", // heavy strokes
        error: "#c13515",
        success: "#008a05", // Airbnb green — online / active / confirmations
        warning: "#ffb400", // Airbnb gold — draft / pending status
      },
      fontFamily: {
        // Airbnb Cereal, substituted by Plus Jakarta Sans (the closest free
        // geometric-humanist analog) for rendering. One family across the app,
        // Airbnb-style; CJK falls back to system serif/sans.
        display: [
          '"Airbnb Cereal VF"',
          '"Plus Jakarta Sans"',
          "-apple-system",
          "system-ui",
          '"PingFang SC"',
          '"Helvetica Neue"',
          "sans-serif",
        ],
        body: [
          '"Airbnb Cereal VF"',
          '"Plus Jakarta Sans"',
          "-apple-system",
          "system-ui",
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
      },
      fontSize: {
        // Display sizes scaled up from the Airbnb tokens for marketing impact,
        // keeping the tight tracking the system prescribes.
        "display-xl": ["2.75rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
        "display-lg": ["2rem", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
        "display-md": ["1.375rem", { lineHeight: "1.2", letterSpacing: "-0.015em" }],
      },
      borderRadius: {
        none: "0px",
        xs: "4px",
        sm: "8px",
        md: "14px",
        lg: "20px",
        xl: "32px",
        pill: "9999px",
        card: "14px",
        avatar: "9999px", // circular avatars, Airbnb-style
      },
      boxShadow: {
        // The single Airbnb elevation tier (hairline + soft lift).
        card: "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.04) 0 2px 6px, rgba(0,0,0,0.10) 0 4px 8px",
        soft: "rgba(0,0,0,0.04) 0 1px 3px, rgba(0,0,0,0.06) 0 6px 16px",
        pill: "0 1px 2px rgba(0,0,0,0.08)",
      },
      backgroundImage: {
        // Airbnb's pink-red brand-orb gradient — a touch of life for accent fills
        // (avatar, selected chips, the "you" chat bubble). Near-flat, on-brand.
        "tinder-gradient": "linear-gradient(135deg, #ff385c 0%, #e61e4d 100%)",
        "tinder-gradient-135": "linear-gradient(135deg, #ff385c 0%, #e61e4d 100%)",
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
