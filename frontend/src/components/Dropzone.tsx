import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";

interface DropzoneProps {
  onFile: (file: File) => void;
  busy?: boolean;
  progress?: number; // 0-100 while uploading
  accept?: string;
  hint?: string;
}

/**
 * Drag-and-drop / tap-to-pick upload target. Posts nothing itself — the parent
 * (Import page) wires `onFile` to api.uploadFile so it can show the
 * "✓ N messages from [ex]" confirmation afterward.
 */
export default function Dropzone({
  onFile,
  busy = false,
  progress = 0,
  accept = ".zip,.txt,.json,.xml,.csv,.db,.pdf,.html",
  hint = "ZIP, TXT, JSON, XML, CSV, DB, PDF",
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (files && files.length > 0) onFile(files[0]);
    },
    [onFile],
  );

  return (
    <motion.div
      whileHover={{ scale: busy ? 1 : 1.01 }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!busy) handleFiles(e.dataTransfer.files);
      }}
      onClick={() => !busy && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !busy) inputRef.current?.click();
      }}
      aria-label="Upload your chat export"
      aria-busy={busy}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-10 text-center transition ${
        dragging
          ? "border-ink bg-surfacesoft"
          : "border-hairline bg-white hover:border-ink"
      } ${busy ? "cursor-wait opacity-80" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {busy ? (
        <div className="w-full">
          <p className="mb-3 font-display font-bold text-ink">Reading your chat…</p>
          <div className="h-2 w-full overflow-hidden rounded-pill bg-surfacestrong">
            <div
              className="h-full rounded-pill bg-rausch transition-all"
              style={{ width: `${Math.max(progress, 8)}%` }}
            />
          </div>
        </div>
      ) : (
        <>
          <span className="mb-2 text-4xl" aria-hidden>
            💌
          </span>
          <p className="font-display text-lg font-bold text-ink">
            Drop your chat export here
          </p>
          <p className="mt-1 text-sm text-muted">or tap to choose a file</p>
          <p className="mt-3 text-xs text-muted">{hint}</p>
        </>
      )}
    </motion.div>
  );
}
