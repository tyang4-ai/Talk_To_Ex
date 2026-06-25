import { useEffect, useState } from "react";
import { tip } from "../lib/tip";

/**
 * Optional Zelle tip jar (the app is free; this just lets fans chip in).
 * Renders nothing when `tip.enabled` is false. Falls back to a friendly
 * placeholder until the QR image exists at `tip.qrSrc`. Clicking the QR opens a
 * fullscreen lightbox (click anywhere / Esc to close).
 */
export default function TipJar({ className = "" }: { className?: string }) {
  const [imgOk, setImgOk] = useState(true);
  const [zoomed, setZoomed] = useState(false);

  // Esc closes the fullscreen QR.
  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  if (!tip.enabled) return null;

  return (
    <div
      className={`rounded-card border border-hairline bg-white p-5 text-center ${className}`}
    >
      <p className="font-display text-lg font-bold text-ink">Enjoying this? Tip the dev ☕</p>
      <p className="mt-1 text-sm text-muted">
        It's free — this just keeps the GPU humming. Totally optional.
      </p>

      <div className="mt-4 flex justify-center">
        {imgOk ? (
          <button
            type="button"
            onClick={() => setZoomed(true)}
            aria-label="Enlarge the Zelle QR code"
            className="rounded-md outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ink"
          >
            <img
              src={tip.qrSrc}
              alt="Zelle tip QR code"
              onError={() => setImgOk(false)}
              className="h-44 w-44 cursor-zoom-in rounded-md border border-hairline object-contain"
            />
          </button>
        ) : (
          <div className="flex h-44 w-44 items-center justify-center rounded-md border-2 border-dashed border-hairline px-3 text-xs text-muted">
            Drop your Zelle QR at public/tip/zelle-qr.png
          </div>
        )}
      </div>

      {tip.zelleHandle && (
        <p className="mt-3 text-sm font-semibold text-ink">
          Zelle <span className="text-rausch">·</span> {tip.zelleHandle}
        </p>
      )}

      {/* Fullscreen lightbox — click anywhere or press Esc to close. */}
      {zoomed && imgOk && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Zelle QR code"
          onClick={() => setZoomed(false)}
          className="fixed inset-0 z-50 flex cursor-zoom-out flex-col items-center justify-center gap-5 bg-black/85 p-6 backdrop-blur-sm"
        >
          <img
            src={tip.qrSrc}
            alt="Zelle tip QR code"
            className="max-h-[80vh] w-auto max-w-[90vw] rounded-xl bg-white p-4 shadow-card"
          />
          {tip.zelleHandle && (
            <p className="font-display text-lg font-semibold text-white">
              Zelle · {tip.zelleHandle}
            </p>
          )}
          <p className="text-sm text-white/70">tap anywhere to close</p>
        </div>
      )}
    </div>
  );
}
