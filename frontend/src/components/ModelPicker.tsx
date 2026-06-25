import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, errorMessage } from "../api/client";

/** The two routed base models (must match backend OLLAMA_MODEL_ZH/EN). */
const QWEN = "qwen2.5:14b-instruct-q4_K_M";
const GEMMA = "gemma3:12b";

interface Props {
  personaId: number;
  initialModel?: string | null;
  initialSource?: string | null; // "auto" | "manual"
}

/**
 * Surface the auto-detected model with a Qwen / Gemma / Auto override (spec §26b),
 * calling POST /api/personas/{id}/model. The choice takes effect immediately and
 * survives re-distill. Worded as the persona's primary voice.
 */
export default function ModelPicker({ personaId, initialModel, initialSource }: Props) {
  const { t } = useTranslation();
  const [model, setModel] = useState<string | null>(initialModel ?? null);
  const [source, setSource] = useState<string>(initialSource ?? "auto");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function choose(choice: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.setPersonaModel(personaId, choice);
      setModel(res.llm_model);
      setSource(res.source);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  // What's currently selected: "auto" unless the user pinned a specific model.
  const selected = source === "manual" ? model : "auto";
  const options = [
    { key: "auto", label: t("model.auto"), hint: t("model.autoHint") },
    { key: QWEN, label: t("model.qwen") },
    { key: GEMMA, label: t("model.gemma") },
  ];

  return (
    <div className="rounded-2xl bg-white/15 px-4 py-3 text-left">
      <p className="text-xs font-semibold uppercase tracking-wide text-white/80">
        {t("model.title")}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((o) => {
          const active = selected === o.key;
          return (
            <button
              key={o.key}
              type="button"
              disabled={busy}
              onClick={() => choose(o.key)}
              aria-pressed={active}
              className={`rounded-pill px-3 py-1.5 text-xs font-bold transition disabled:opacity-60 ${
                active ? "bg-white text-tinder-start" : "bg-white/15 text-white hover:bg-white/25"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {err && <p className="mt-2 text-xs font-medium text-white">{err}</p>}
    </div>
  );
}
