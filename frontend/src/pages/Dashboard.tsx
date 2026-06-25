import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import Avatar from "../components/Avatar";
import { TextAreaField } from "../components/Field";
import {
  api,
  clearToken,
  errorMessage,
  type PersonaDetail,
  type PersonaStatus,
} from "../api/client";
import { getDraftPersonaId, clearDraftPersonaId } from "../lib/draft";

const STATUS_LABEL: Record<PersonaStatus, string> = {
  draft: "Draft — not live yet",
  active: "Active — they're answering",
  dormant: "Dormant — replies paused",
};

const STATUS_DOT: Record<PersonaStatus, string> = {
  draft: "bg-warning",
  active: "bg-success",
  dormant: "bg-muted",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const personaId = getDraftPersonaId();
  const [persona, setPersona] = useState<PersonaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [killed, setKilled] = useState(false);
  const [correction, setCorrection] = useState("");
  const [correctionMsg, setCorrectionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingCorrection, setSavingCorrection] = useState(false);

  useEffect(() => {
    if (personaId === null) {
      setLoading(false);
      return;
    }
    api
      .getPersona(personaId)
      .then(setPersona)
      .catch((err) => setError(errorMessage(err, "Couldn't load your persona.")))
      .finally(() => setLoading(false));
  }, [personaId]);

  async function toggleKill() {
    if (personaId === null) return;
    const next = !killed;
    setKilled(next);
    try {
      await api.setKillSwitch(personaId, next);
    } catch (err) {
      setKilled(!next); // revert on failure
      setError(errorMessage(err, "Couldn't toggle the kill-switch."));
    }
  }

  async function submitCorrection(e: FormEvent) {
    e.preventDefault();
    if (personaId === null || !correction.trim()) return;
    setCorrectionMsg(null);
    setSavingCorrection(true);
    try {
      await api.addCorrection(personaId, correction.trim());
      setCorrection("");
      setCorrectionMsg("Got it — they'll adjust.");
    } catch (err) {
      setError(errorMessage(err, "Couldn't save that correction."));
    } finally {
      setSavingCorrection(false);
    }
  }

  function logout() {
    clearToken();
    clearDraftPersonaId();
    navigate("/", { replace: true });
  }

  if (personaId === null && !loading) {
    return (
      <WizardShell onBack={() => navigate("/")} title="No persona yet">
        <Card>
          <p className="text-muted">You haven't built anyone yet. Start the flow to begin.</p>
          <GradientButton className="mt-4" fullWidth onClick={() => navigate("/intake")}>
            Build a profile →
          </GradientButton>
        </Card>
      </WizardShell>
    );
  }

  return (
    <WizardShell onBack={() => navigate("/")} title="Dashboard">
      {loading ? (
        <Card still>
          <p className="text-muted">Loading…</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Status */}
          <Card>
            <div className="flex items-center gap-4">
              <Avatar name={persona?.name ?? "?"} size={64} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-xl font-bold text-ink">
                  {persona?.name ?? "Your ex"}
                </p>
                <p className="mt-1 flex items-center gap-2 text-sm text-muted">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      persona ? STATUS_DOT[persona.status] : "bg-hairline"
                    }`}
                  />
                  {persona ? STATUS_LABEL[persona.status] : "Unknown"}
                </p>
              </div>
            </div>
            {persona?.number && (
              <p className="mt-4 rounded-md bg-surfacesoft px-4 py-2.5 text-sm font-semibold text-ink">
                Texting number: {persona.number.e164}
              </p>
            )}
            <p className="mt-3 text-sm text-muted">
              {persona ? persona.message_count.toLocaleString() : 0} messages learned
            </p>
          </Card>

          {/* Add data */}
          <Card>
            <h3 className="text-display-md font-bold text-ink">Add more chats</h3>
            <p className="mt-1 text-sm text-muted">
              More history sharpens their voice. We re-distill when you add data.
            </p>
            <GradientButton
              variant="ink"
              className="mt-4"
              fullWidth
              onClick={() => navigate("/import")}
            >
              Import more →
            </GradientButton>
          </Card>

          {/* Corrections */}
          <Card>
            <h3 className="text-display-md font-bold text-ink">Set them straight</h3>
            <p className="mt-1 text-sm text-muted">
              “She'd never say that.” Tell us what's off and they'll adjust.
            </p>
            <form onSubmit={submitCorrection} className="mt-4 space-y-3">
              <TextAreaField
                label="What should change?"
                name="correction"
                rows={3}
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                placeholder="They never used emojis. And they'd never call me 'babe'."
              />
              {correctionMsg && (
                <p className="text-sm font-semibold text-success">{correctionMsg}</p>
              )}
              <GradientButton
                type="submit"
                variant="ink"
                loading={savingCorrection}
                disabled={!correction.trim()}
              >
                Apply correction
              </GradientButton>
            </form>
          </Card>

          {/* Kill switch */}
          <Card>
            <div className="flex items-center justify-between gap-4">
              <div>
                <h3 className="text-display-md font-bold text-ink">Kill-switch</h3>
                <p className="mt-1 text-sm text-muted">
                  Silence every reply instantly. The data stays put.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={killed}
                onClick={toggleKill}
                className={`relative h-8 w-14 shrink-0 rounded-pill transition-colors ${
                  killed ? "bg-error" : "bg-surfacestrong"
                }`}
              >
                <span
                  className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow transition-all ${
                    killed ? "left-7" : "left-1"
                  }`}
                />
              </button>
            </div>
            {killed && (
              <p className="mt-3 alert-error">
                Replies are off. Flip the switch back to bring them online.
              </p>
            )}
          </Card>

          {error && <p className="alert-error">{error}</p>}

          <button
            onClick={logout}
            className="mx-auto block py-2 text-sm font-semibold text-muted hover:text-ink"
          >
            Log out
          </button>
        </div>
      )}
    </WizardShell>
  );
}
