import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import StepGuide from "../components/StepGuide";
import Dropzone from "../components/Dropzone";
import { TextAreaField } from "../components/Field";
import { importGuides, type PlatformGuide } from "../lib/importGuides";
import { api, errorMessage, type UploadResult } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";

export default function Import() {
  const navigate = useNavigate();
  const personaId = getDraftPersonaId();

  const [activeId, setActiveId] = useState<PlatformGuide["id"]>("whatsapp");
  const [uploads, setUploads] = useState<UploadResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [pasteExName, setPasteExName] = useState("");

  useEffect(() => {
    if (personaId === null) navigate("/intake", { replace: true });
  }, [personaId, navigate]);

  const active = importGuides.find((g) => g.id === activeId)!;
  const totalMessages = uploads.reduce((sum, u) => sum + u.message_count, 0);

  async function handleFile(file: File) {
    if (personaId === null) return;
    setError(null);
    setBusy(true);
    setProgress(0);
    try {
      const result = await api.uploadFile(personaId, file, setProgress);
      setUploads((prev) => [...prev, result]);
    } catch (err) {
      setError(errorMessage(err, "Couldn't read that file. Try the plaintext paste below."));
    } finally {
      setBusy(false);
      setProgress(0);
    }
  }

  async function handlePaste() {
    if (personaId === null || !pasteText.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const result = await api.uploadPlaintext(
        personaId,
        pasteText.trim(),
        pasteExName.trim() || active.platform,
      );
      setUploads((prev) => [...prev, result]);
      setPasteText("");
    } catch (err) {
      setError(errorMessage(err, "Couldn't read that text. Check the format and try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <WizardShell
      step={3}
      totalSteps={5}
      title="Bring the chats"
      subtitle="Pick where you talked. We auto-detect the format — you never choose one."
    >
      {/* Platform tabs */}
      <div className="-mx-1 mb-4 flex gap-2 overflow-x-auto px-1 pb-1">
        {importGuides.map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => setActiveId(g.id)}
            aria-pressed={activeId === g.id}
            className={`flex shrink-0 items-center gap-1.5 rounded-pill px-4 py-2 text-sm font-semibold transition ${
              activeId === g.id
                ? "bg-rausch text-white"
                : "bg-white text-ink ring-1 ring-hairline hover:ring-ink"
            }`}
          >
            <span aria-hidden>{g.emoji}</span>
            {g.platform.split(" ")[0]}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={active.id}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.22 }}
        >
          <Card still>
            <StepGuide
              platform={active.platform}
              emoji={active.emoji}
              steps={active.steps}
              note={active.note}
            />
          </Card>
        </motion.div>
      </AnimatePresence>

      {/* Dropzone */}
      <div className="mt-4">
        <Dropzone
          onFile={handleFile}
          busy={busy}
          progress={progress}
          accept={active.accept}
          hint={active.hint}
        />
      </div>

      {/* Plaintext fallback (universal — esp. WeChat) */}
      <details className="mt-4 rounded-card border border-hairline bg-white p-4 shadow-soft">
        <summary className="cursor-pointer font-display font-semibold text-ink">
          Or paste the messages instead
        </summary>
        <div className="mt-3 space-y-3">
          <input
            className="field"
            placeholder="Their name (for the labels)"
            value={pasteExName}
            onChange={(e) => setPasteExName(e.target.value)}
          />
          <TextAreaField
            label="Paste your chat"
            name="paste"
            rows={6}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={"2024-01-02 你: 在吗\n2024-01-02 me: yeah what's up"}
          />
          <GradientButton
            variant="ink"
            onClick={handlePaste}
            disabled={!pasteText.trim() || busy}
          >
            Add pasted chat
          </GradientButton>
        </div>
      </details>

      {error && (
        <p className="mt-4 alert-error">{error}</p>
      )}

      {/* Parse-preview confirmations: "✓ N messages from [ex]" */}
      {uploads.length > 0 && (
        <div className="mt-5 space-y-3">
          {uploads.map((u) => (
            <motion.div
              key={u.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-card border border-hairline bg-white p-4 shadow-soft"
            >
              <p className="font-display font-bold text-ink">
                ✓ {u.message_count.toLocaleString()} messages from {u.ex_name}
              </p>
              {(u.date_start || u.date_end) && (
                <p className="text-sm text-muted">
                  {u.date_start} – {u.date_end}
                </p>
              )}
              {u.sample_lines && u.sample_lines.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-muted">
                  {u.sample_lines.slice(0, 3).map((line, i) => (
                    <li key={i} className="truncate">
                      “{line}”
                    </li>
                  ))}
                </ul>
              )}
            </motion.div>
          ))}
        </div>
      )}

      <div className="mt-auto pt-8">
        <GradientButton
          fullWidth
          disabled={totalMessages === 0}
          onClick={() => navigate("/building")}
        >
          {totalMessages === 0
            ? "Add a chat to continue"
            : `Distill ${totalMessages.toLocaleString()} messages →`}
        </GradientButton>
      </div>
    </WizardShell>
  );
}
