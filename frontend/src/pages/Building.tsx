import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import WizardShell from "../components/WizardShell";
import GradientButton from "../components/GradientButton";
import { api, errorMessage, type BuildStatus } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";

function prettyNumber(e164: string): string {
  // +13105551234 -> +1 (310) 555-1234 ; leave non-US numbers as-is.
  const m = e164.match(/^\+1(\d{3})(\d{3})(\d{4})$/);
  return m ? `+1 (${m[1]}) ${m[2]}-${m[3]}` : e164;
}

const POLL_MS = 3000;
const DONE = new Set(["ready", "revealed"]); // build finished (opener sent or pending)

/**
 * The async "reveal": kick off the build (set up & forget), then poll status.
 * While the persona is "contemplating their wrongdoings" the user can close the
 * tab — when the build finishes the persona texts them FIRST, and this screen
 * flips to "they texted you".
 */
export default function Building() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const stages = t("building.stages", { returnObjects: true }) as unknown as string[];
  const personaId = getDraftPersonaId();
  const [status, setStatus] = useState<BuildStatus | null>(null);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const ranFor = useRef(-1);

  const state = status?.state ?? "draft";
  const name = status?.name || "Your ex";
  const done = DONE.has(state);

  useEffect(() => {
    if (personaId === null) {
      navigate("/intake", { replace: true });
      return;
    }
    if (ranFor.current === attempt) return; // guard StrictMode double-invoke
    ranFor.current = attempt;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let ticker: ReturnType<typeof setInterval>;

    const stop = () => {
      clearTimeout(timer);
      clearInterval(ticker);
    };

    const apply = (s: BuildStatus): boolean => {
      if (cancelled) return true;
      setStatus(s);
      if (s.state === "failed") {
        setError(s.error || t("building.failed", { name: s.name }));
        return true;
      }
      return DONE.has(s.state); // true => finished, stop polling
    };

    const poll = async () => {
      try {
        if (apply(await api.status(personaId))) stop();
        else timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, t("building.retry")));
      }
    };

    // Start the build (idempotent server-side), animate, then poll until done.
    api
      .build(personaId)
      .then((s) => {
        if (apply(s)) return;
        ticker = setInterval(
          () => setStage((x) => (x < stages.length - 1 ? x + 1 : x)),
          1800,
        );
        timer = setTimeout(poll, POLL_MS);
      })
      .catch((err) => !cancelled && setError(errorMessage(err, t("building.retry"))));

    return () => {
      cancelled = true;
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personaId, navigate, attempt]);

  function retry() {
    setError(null);
    setStatus(null);
    setStage(0);
    setAttempt((a) => a + 1);
  }

  return (
    <WizardShell step={4} totalSteps={5} title={done ? "They reached out" : "Building them"}>
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <motion.div
          animate={{ rotate: done ? 0 : [0, -8, 8, 0], scale: done ? 1.05 : 1 }}
          transition={done ? { duration: 0.4 } : { duration: 1.8, repeat: Infinity }}
          className="text-7xl"
          aria-hidden
        >
          {done ? "💌" : "💔"}
        </motion.div>

        <p className="mt-6 font-display text-2xl font-bold text-ink">
          {done
            ? t("building.texted", { name })
            : t("building.contemplatingTitle", { name })}
        </p>
        <p className="mt-2 max-w-xs text-sm text-muted" aria-live="polite">
          {done ? t("building.textedBlurb") : stages[stage]}
        </p>

        {!done && !error && (
          <>
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
            <p className="mt-6 max-w-xs text-xs text-muted">
              {t("building.closeHint", { name })}
            </p>
            {status && !status.has_phone && (
              <p className="mt-3 max-w-xs rounded-md border border-hairline bg-surfacesoft px-4 py-2.5 text-sm font-medium text-error">
                {t("building.noPhone")}
              </p>
            )}
          </>
        )}

        {done && status?.number_e164 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-7 w-full max-w-xs rounded-card border border-hairline bg-white p-6 shadow-card"
          >
            <p className="text-sm font-semibold uppercase tracking-wide text-muted">
              {t("building.fromNumber")}
            </p>
            <p className="mt-1 font-display text-display-md font-extrabold text-ink">
              {prettyNumber(status.number_e164)}
            </p>
          </motion.div>
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

      <div className="space-y-3 pt-6">
        <GradientButton
          variant={done ? "primary" : "ghost"}
          fullWidth
          onClick={() => navigate("/dashboard")}
        >
          {t("building.toDashboard")}
        </GradientButton>
      </div>
    </WizardShell>
  );
}
