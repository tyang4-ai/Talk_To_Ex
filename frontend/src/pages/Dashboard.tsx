import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import Avatar from "../components/Avatar";
import TipJar from "../components/TipJar";
import { TextAreaField } from "../components/Field";
import {
  api,
  clearToken,
  errorMessage,
  type PersonaDetail,
  type PersonaStatus,
  type PersonaSummary,
} from "../api/client";
import {
  getDraftPersonaId,
  setDraftPersonaId,
  clearDraftPersonaId,
} from "../lib/draft";

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
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(getDraftPersonaId());
  const [persona, setPersona] = useState<PersonaDetail | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [killed, setKilled] = useState(false);
  const [correction, setCorrection] = useState("");
  const [correctionMsg, setCorrectionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingCorrection, setSavingCorrection] = useState(false);

  // Load every persona this user owns; pick the selected ex (the persisted
  // draft id, falling back to the first one) so the detail cards have a target.
  useEffect(() => {
    api
      .listPersonas()
      .then((list) => {
        setPersonas(list);
        setSelectedId((current) => {
          if (current !== null && list.some((p) => p.id === current)) return current;
          return list.length ? list[0].id : null;
        });
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load your exes.")))
      .finally(() => setListLoading(false));
  }, []);

  // Load the selected persona's detail into the cards below.
  useEffect(() => {
    if (selectedId === null) {
      setPersona(null);
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    setCorrection("");
    setCorrectionMsg(null);
    api
      .getPersona(selectedId)
      .then((detail) => {
        setPersona(detail);
        setKilled(detail.status === "dormant");
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load your persona.")))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  function selectPersona(id: number) {
    if (id === selectedId) return;
    setDraftPersonaId(id);
    setSelectedId(id);
  }

  function addEx() {
    // Start the wizard fresh — no destructive change to existing personas.
    clearDraftPersonaId();
    navigate("/intake");
  }

  async function toggleKill() {
    if (selectedId === null) return;
    const next = !killed;
    setKilled(next);
    try {
      await api.setKillSwitch(selectedId, next);
    } catch (err) {
      setKilled(!next); // revert on failure
      setError(errorMessage(err, "Couldn't toggle the kill-switch."));
    }
  }

  async function submitCorrection(e: FormEvent) {
    e.preventDefault();
    if (selectedId === null || !correction.trim()) return;
    setCorrectionMsg(null);
    setSavingCorrection(true);
    try {
      await api.addCorrection(selectedId, correction.trim());
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

  // Empty state — no exes built yet.
  if (!listLoading && personas.length === 0) {
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
      {listLoading ? (
        <Card still>
          <p className="text-muted">Loading…</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Persona switcher */}
          <div className="flex flex-wrap gap-2">
            {personas.map((p) => {
              const active = p.id === selectedId;
              return (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => selectPersona(p.id)}
                  className={`flex items-center gap-2.5 rounded-card border px-3 py-2 text-left transition-colors ${
                    active
                      ? "border-ink bg-surfacesoft"
                      : "border-hairline hover:border-borderstrong"
                  }`}
                >
                  <Avatar name={p.name} size={40} />
                  <span className="min-w-0">
                    <span className="block max-w-[8rem] truncate text-sm font-semibold text-ink">
                      {p.name}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                      <span
                        className={`h-2 w-2 rounded-full ${STATUS_DOT[p.status]}`}
                      />
                      {p.status}
                    </span>
                  </span>
                </button>
              );
            })}
            <button
              type="button"
              onClick={addEx}
              className="flex items-center gap-2 rounded-card border border-dashed border-hairline px-4 py-2 text-sm font-semibold text-muted transition-colors hover:border-ink hover:text-ink"
            >
              <span className="text-lg leading-none">+</span>
              Add an ex
            </button>
          </div>

          {detailLoading ? (
            <Card still>
              <p className="text-muted">Loading…</p>
            </Card>
          ) : (
            <>
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
            </>
          )}

          {error && <p className="alert-error">{error}</p>}

          <TipJar />

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
