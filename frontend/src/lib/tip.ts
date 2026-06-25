/**
 * Tip jar config. Personal data is kept OUT of the (public) repo:
 *
 *   1. Drop your Zelle QR at:  frontend/public/tip/zelle-qr.png   (gitignored)
 *      (a square PNG works best; until it's there a "coming soon" placeholder shows)
 *   2. Set your handle in:     frontend/.env.local                (gitignored)
 *        VITE_ZELLE_HANDLE=(408) 210-6451
 *   3. To hide the tip jar entirely, set `enabled: false`.
 *
 * The tip box renders on the Plan page and the Dashboard.
 */
export const tip = {
  enabled: true,
  zelleHandle: import.meta.env.VITE_ZELLE_HANDLE ?? "",
  qrSrc: "/tip/zelle-qr.png",
} as const;
