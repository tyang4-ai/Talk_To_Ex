import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import WizardShell from "../components/WizardShell";
import GradientButton from "../components/GradientButton";
import Avatar from "../components/Avatar";
import { api, errorMessage, type AssignedNumber } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";
import { microcopy } from "../lib/theme";

function prettyNumber(e164: string): string {
  // +13105551234 -> +1 (310) 555-1234 ; leave non-US numbers as-is.
  const m = e164.match(/^\+1(\d{3})(\d{3})(\d{4})$/);
  return m ? `+1 (${m[1]}) ${m[2]}-${m[3]}` : e164;
}

export default function Reveal() {
  const navigate = useNavigate();
  const personaId = getDraftPersonaId();
  const [number, setNumber] = useState<AssignedNumber | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (personaId === null) {
      navigate("/intake", { replace: true });
      return;
    }
    if (started.current) return;
    started.current = true;
    api
      .activate(personaId)
      .then((res) => setNumber(res.number))
      .catch((err) =>
        setError(
          errorMessage(err, "Couldn't assign a number. Make sure your subscription is active."),
        ),
      )
      .finally(() => setLoading(false));
  }, [personaId, navigate]);

  return (
    <WizardShell step={5} totalSteps={5} title="It's a match">
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
        >
          <Avatar name="Your ex" size={140} />
        </motion.div>

        <p className="mt-5 font-display text-2xl font-extrabold text-ink">
          {microcopy.matchMade}
        </p>

        {loading && (
          <p className="mt-6 text-muted" aria-live="polite">
            Assigning your number…
          </p>
        )}

        {error && (
          <p className="mt-6 max-w-xs rounded-md border border-hairline bg-surfacesoft px-4 py-2.5 text-sm font-medium text-error">
            {error}
          </p>
        )}

        {number && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-7 w-full max-w-xs rounded-card border border-hairline bg-white p-6 shadow-card"
          >
            <p className="text-sm font-semibold uppercase tracking-wide text-muted">
              Text them at
            </p>
            <p className="mt-1 font-display text-display-md font-extrabold text-ink">
              {prettyNumber(number.e164)}
            </p>
            <a
              href={`sms:${number.e164}`}
              className="pill-ink mt-4 inline-flex w-full"
            >
              Open Messages 💬
            </a>
            {number.mode === "trial" && (
              <p className="mt-3 text-xs text-muted">
                Trial number — replies carry a Twilio watermark until you upgrade.
              </p>
            )}
          </motion.div>
        )}
      </div>

      <div className="space-y-3 pt-6">
        <GradientButton
          variant="primary"
          fullWidth
          disabled={!number}
          onClick={() => navigate("/preview")}
        >
          Try a message first →
        </GradientButton>
        <button
          onClick={() => navigate("/dashboard")}
          className="mx-auto block text-sm font-semibold text-ink underline-offset-4 hover:underline"
        >
          Go to dashboard
        </button>
      </div>
    </WizardShell>
  );
}
