import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import WizardShell from "../components/WizardShell";
import GradientButton from "../components/GradientButton";
import { api, errorMessage } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";
import { microcopy } from "../lib/theme";

const STAGES = [
  "Reading your chats",
  "Learning their voice",
  "Mapping the in-jokes",
  "Bottling the chaos",
  "Almost them",
];

export default function Building() {
  const navigate = useNavigate();
  const personaId = getDraftPersonaId();
  const [stage, setStage] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (personaId === null) {
      navigate("/intake", { replace: true });
      return;
    }
    if (started.current) return;
    started.current = true;

    // Animate the stage labels while the (slow) Claude distillation runs.
    const ticker = setInterval(() => {
      setStage((s) => (s < STAGES.length - 1 ? s + 1 : s));
    }, 1600);

    api
      .distill(personaId)
      .then(() => {
        setStage(STAGES.length - 1);
        setDone(true);
      })
      .catch((err) => {
        setError(errorMessage(err, "Distillation hit a snag. You can retry."));
      })
      .finally(() => clearInterval(ticker));

    return () => clearInterval(ticker);
  }, [personaId, navigate]);

  async function retry() {
    if (personaId === null) return;
    setError(null);
    setDone(false);
    setStage(0);
    try {
      await api.distill(personaId);
      setStage(STAGES.length - 1);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, "Still failing. Try again in a bit."));
    }
  }

  return (
    <WizardShell step={4} totalSteps={5} gradient title="Building them">
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <motion.div
          animate={{ rotate: done ? 0 : [0, -8, 8, 0], scale: done ? 1.05 : 1 }}
          transition={done ? { duration: 0.4 } : { duration: 1.8, repeat: Infinity }}
          className="text-7xl"
          aria-hidden
        >
          {done ? "💘" : "💔"}
        </motion.div>

        <p className="mt-6 font-display text-2xl font-bold text-white">
          {done ? microcopy.matchMade : STAGES[stage]}
        </p>
        <p className="mt-2 max-w-xs text-sm text-white/85">
          {done
            ? "Their voice is bottled and encrypted. Ready to meet them?"
            : microcopy.buildingBlurb}
        </p>

        {!done && !error && (
          <div className="mt-8 flex w-full max-w-xs items-center gap-1.5" aria-hidden>
            {STAGES.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 flex-1 rounded-pill transition-colors ${
                  i <= stage ? "bg-white" : "bg-white/30"
                }`}
              />
            ))}
          </div>
        )}

        {error && (
          <div className="mt-8 w-full max-w-xs space-y-3">
            <p className="rounded-2xl bg-white/15 px-4 py-2.5 text-sm font-medium text-white">
              {error}
            </p>
            <GradientButton variant="primary" fullWidth onClick={retry}>
              Try again
            </GradientButton>
          </div>
        )}
      </div>

      {done && (
        <div className="pt-6">
          <GradientButton variant="primary" fullWidth onClick={() => navigate("/reveal")}>
            Meet them →
          </GradientButton>
        </div>
      )}
    </WizardShell>
  );
}
