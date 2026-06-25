/**
 * Single source of truth for the "Tinder for your ex" visual identity (spec §2).
 * Tailwind config mirrors these tokens; this module exposes them for inline use
 * (framer-motion variants, gradient strings, dynamic styles).
 */

export const gradient = {
  start: "#B0451F",
  mid: "#9A3B1A",
  end: "#7E2F12",
} as const;

/** Rich deep-oxblood feature surface (hero / "moment" screens). */
export const tinderGradient = `linear-gradient(165deg, ${gradient.start} 0%, ${gradient.end} 58%, #6B2710 100%)`;
export const tinderGradient135 = `linear-gradient(135deg, #B0451F 0%, #8F3416 100%)`;

export const colors = {
  ...gradient,
  oxblood: "#B0451F",
  ink: "#1C1A17",
  muted: "#6E665A",
  line: "#E4DCCC",
  neutralbg: "#F4EFE6",
  card: "#FBF8F1",
} as const;

export const radii = {
  pill: 9999,
  card: 16,
  avatar: 16,
} as const;

export const fonts = {
  display: '"Fraunces", "Songti SC", Georgia, serif',
  body: '"Hanken Grotesk", "PingFang SC", ui-sans-serif, system-ui, sans-serif',
} as const;

/** Shared framer-motion presets so motion feels consistent across the wizard. */
export const motionPresets = {
  // Card entrance — soft fade + lift.
  cardIn: {
    initial: { opacity: 0, y: 24, scale: 0.98 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, y: -24, scale: 0.98 },
    transition: { type: "spring", stiffness: 320, damping: 30 },
  },
  // Page-level fade for route changes.
  pageIn: {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -12 },
    transition: { duration: 0.32, ease: "easeOut" },
  },
  // Chat bubble pop-in.
  bubbleIn: {
    initial: { opacity: 0, y: 8, scale: 0.96 },
    animate: { opacity: 1, y: 0, scale: 1 },
    transition: { type: "spring", stiffness: 420, damping: 28 },
  },
} as const;

/** Playful, knowing microcopy (spec §2 — the locked strings live here). */
export const microcopy = {
  tagline: "Swipe right on your ex 💔",
  matchMade: "It's a match… sort of",
  buildingBlurb: "Reading your chats. Learning their voice.",
} as const;
