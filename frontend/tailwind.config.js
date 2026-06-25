/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // The brand accent, refined from candy-coral to a deep oxblood. Kept under
        // the `tinder` key so existing accent classes (text-tinder-*, the gradient)
        // re-theme app-wide without touching every call site.
        tinder: {
          start: "#B0451F",
          mid: "#9A3B1A",
          end: "#7E2F12",
        },
        oxblood: { DEFAULT: "#B0451F", deep: "#8F3416" },
        ink: "#1C1A17", // near-black warm ink
        muted: "#6E665A", // warm grey
        line: "#E4DCCC", // hairline on paper
        neutralbg: "#F4EFE6", // warm paper background
        card: "#FBF8F1", // warm off-white surface
      },
      fontFamily: {
        // Fraunces (variable serif) for display; Hanken Grotesk for body — a
        // deliberate editorial pairing, not the Inter/Poppins default. CJK falls
        // back to system serif/sans so mixed zh/en stays cohesive.
        display: ['"Fraunces"', '"Songti SC"', '"Noto Serif SC"', "Georgia", "serif"],
        body: ['"Hanken Grotesk"', '"PingFang SC"', '"Microsoft YaHei"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        "display-xl": ["3.4rem", { lineHeight: "1.0", letterSpacing: "-0.02em" }],
        "display-lg": ["2.6rem", { lineHeight: "1.04", letterSpacing: "-0.018em" }],
        "display-md": ["1.9rem", { lineHeight: "1.1", letterSpacing: "-0.012em" }],
      },
      borderRadius: {
        pill: "9999px",
        card: "1rem",
        avatar: "1rem",
      },
      boxShadow: {
        // Neutral, restrained depth — no candy-pink glows.
        card: "0 1px 2px rgba(28,26,23,0.04), 0 26px 50px -30px rgba(28,26,23,0.30)",
        pill: "0 10px 22px -12px rgba(126,47,18,0.45)",
        soft: "0 12px 32px -18px rgba(28,26,23,0.18)",
      },
      backgroundImage: {
        // Rich deep-oxblood feature surface (hero / "moment" screens).
        "tinder-gradient":
          "linear-gradient(165deg, #9A3B1A 0%, #7E2F12 58%, #6B2710 100%)",
        // Accent fill for buttons / badges / active tabs.
        "tinder-gradient-135":
          "linear-gradient(135deg, #B0451F 0%, #8F3416 100%)",
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
