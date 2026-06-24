/**
 * Single source of truth for the "Tinder for your ex" visual identity (spec §2).
 * Tailwind config mirrors these tokens; this module exposes them for inline use
 * (framer-motion variants, gradient strings, dynamic styles).
 */

export const gradient = {
  start: "#FD297B",
  mid: "#FF5864",
  end: "#FF655B",
} as const;

/** Vertical coral->pink gradient — the locked brand surface. */
export const tinderGradient = `linear-gradient(180deg, ${gradient.start} 0%, ${gradient.mid} 55%, ${gradient.end} 100%)`;
export const tinderGradient135 = `linear-gradient(135deg, ${gradient.start} 0%, ${gradient.mid} 55%, ${gradient.end} 100%)`;

export const colors = {
  ...gradient,
  ink: "#1F1A24",
  muted: "#6B6470",
  neutralbg: "#FBF7F4",
  card: "#FFFFFF",
} as const;

export const radii = {
  pill: 9999,
  card: 28,
  avatar: 32,
} as const;

export const fonts = {
  display: '"Poppins", "Inter", system-ui, sans-serif',
  body: '"Inter", system-ui, sans-serif',
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
