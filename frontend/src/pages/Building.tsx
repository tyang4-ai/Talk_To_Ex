import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import WizardShell from "../components/WizardShell";
import GradientButton from "../components/GradientButton";
import ModelPicker from "../components/ModelPicker";
import { api, errorMessage } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";

export default function Building() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const stages = t("building.stages", { returnObjects: true }) as unknown as string[];
  const personaId = getDraftPersonaId();
  const [stage, setStage] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [modelSource, setModelSource] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (personaId === null) {
      navigate("/intake", { replace: true });
      return;
    }
    if (started.current) return;
    started.current = true;

    // Animate the stage labels while the (slow) distillation runs.
    const ticker = setInterval(() => {
      setStage((s) => (s < stages.length - 1 ? s + 1 : s));
    }, 1600);

    api
      .distill(personaId)
      .then((res) => {
        setModel(res.llm_model ?? null);
        setModelSource(res.llm_model_source ?? null);
        setStage(stages.length - 1);
        setDone(true);
      })
      .catch((err) => {
        setError(errorMessage(err, t("building.retry")));
      })
      .finally(() => clearInterval(ticker));

    return () => clearInterval(ticker);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personaId, navigate]);

  async function retry() {
    if (personaId === null) return;
    setError(null);
    setDone(false);
    setStage(0);
    try {
      const res = await api.distill(personaId);
      setModel(res.llm_model ?? null);
      setModelSource(res.llm_model_source ?? null);
      setStage(stages.length - 1);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, t("building.retry")));
    }
  }

  return (
    <WizardShell step={4} totalSteps={5} title="Building them">
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <motion.div
          animate={{ rotate: done ? 0 : [0, -8, 8, 0], scale: done ? 1.05 : 1 }}
          transition={done ? { duration: 0.4 } : { duration: 1.8, repeat: Infinity }}
          className="text-7xl"
          aria-hidden
        >
          {done ? "💘" : "💔"}
        </motion.div>

        <p className="mt-6 font-display text-2xl font-bold text-ink">
          {done ? t("building.matchMade") : stages[stage]}
        </p>
        <p className="mt-2 max-w-xs text-sm text-muted">
          {done ? t("building.doneBlurb") : t("building.blurb")}
        </p>

        {!done && !error && (
          <div className="mt-8 flex w-full max-w-xs items-center gap-1.5" aria-hidden>
            {stages.map((_, i) => (
              <span
                key={i}
                className={`h-1 flex-1 rounded-pill transition-colors ${
                  i <= stage ? "bg-rausch" : "bg-hairline"
                }`}
              />
            ))}
          </div>
        )}

        {error && (
          <div className="mt-8 w-full max-w-xs space-y-3">
            <p className="rounded-md border border-hairline bg-surfacesoft px-4 py-2.5 text-sm font-medium text-error">
              {error}
            </p>
            <GradientButton variant="primary" fullWidth onClick={retry}>
              {t("common.tryAgain")}
            </GradientButton>
          </div>
        )}
      </div>

      {done && (
        <div className="space-y-4 pt-6">
          {personaId !== null && (
            <ModelPicker personaId={personaId} initialModel={model} initialSource={modelSource} />
          )}
          <GradientButton variant="primary" fullWidth onClick={() => navigate("/reveal")}>
            {t("building.meet")}
          </GradientButton>
        </div>
      )}
    </WizardShell>
  );
}
