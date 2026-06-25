import { useState } from "react";
import { tip } from "../lib/tip";

/**
 * Optional Zelle tip jar (the app is free; this just lets fans chip in).
 * Renders nothing when `tip.enabled` is false. Falls back to a friendly
 * placeholder until the QR image exists at `tip.qrSrc`.
 */
export default function TipJar({ className = "" }: { className?: string }) {
  const [imgOk, setImgOk] = useState(true);
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
          <img
            src={tip.qrSrc}
            alt="Zelle tip QR code"
            onError={() => setImgOk(false)}
            className="h-44 w-44 rounded-md border border-hairline object-contain"
          />
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
    </div>
  );
}
