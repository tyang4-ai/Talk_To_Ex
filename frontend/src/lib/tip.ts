/**
 * Tip jar config — the ONE place to set up your Zelle tip box.
 *
 *   1. Drop your Zelle QR image at:  frontend/public/tip/zelle-qr.png
 *      (a square PNG works best; until it's there a "coming soon" placeholder shows)
 *   2. Set `zelleHandle` to your Zelle email or phone (shown under the QR).
 *   3. To hide the tip jar entirely, set `enabled: false`.
 *
 * The tip box renders on the Plan page and the Dashboard.
 */
export const tip = {
  enabled: true,
  zelleHandle: "", // e.g. "you@example.com" or "+1 (555) 123-4567"
  qrSrc: "/tip/zelle-qr.png",
} as const;
