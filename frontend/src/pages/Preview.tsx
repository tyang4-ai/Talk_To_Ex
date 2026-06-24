import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import ChatBubble from "../components/ChatBubble";
import GradientButton from "../components/GradientButton";
import Avatar from "../components/Avatar";
import { api, errorMessage, type PersonaDetail } from "../api/client";
import { getDraftPersonaId } from "../lib/draft";

interface ThreadItem {
  id: string;
  text: string;
  side: "in" | "out";
}

let counter = 0;
const nextId = () => `m${counter++}`;

export default function Preview() {
  const navigate = useNavigate();
  const personaId = getDraftPersonaId();
  const [persona, setPersona] = useState<PersonaDetail | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (personaId === null) {
      navigate("/intake", { replace: true });
      return;
    }
    api
      .getPersona(personaId)
      .then(setPersona)
      .catch(() => {
        /* non-fatal — preview still works, header just shows a generic name */
      });
  }, [personaId, navigate]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [thread, sending]);

  const exName = persona?.name ?? "Your ex";

  async function send(e: FormEvent) {
    e.preventDefault();
    const body = draft.trim();
    if (!body || personaId === null) return;
    setError(null);
    setDraft("");
    setThread((t) => [...t, { id: nextId(), text: body, side: "in" }]);
    setSending(true);
    try {
      const { bubbles } = await api.preview(personaId, body);
      setThread((t) => [
        ...t,
        ...bubbles.map((b) => ({ id: nextId(), text: b, side: "out" as const })),
      ]);
    } catch (err) {
      setError(errorMessage(err, "They didn't reply. (The model may be warming up.)"));
    } finally {
      setSending(false);
    }
  }

  return (
    <WizardShell onBack={() => navigate("/reveal")}>
      <div className="flex flex-1 flex-col">
        {/* Dating-app thread header */}
        <div className="flex items-center gap-3 border-b border-black/5 pb-4">
          <Avatar name={exName} size={48} />
          <div>
            <p className="font-display text-lg font-bold text-ink">{exName}</p>
            <p className="text-xs font-medium text-green-500">● online now</p>
          </div>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 space-y-2.5 overflow-y-auto py-4">
          {thread.length === 0 && !sending && (
            <div className="mt-10 text-center text-sm text-muted">
              Say something. See if they still text like they used to.
            </div>
          )}
          {thread.map((m) => (
            <ChatBubble key={m.id} text={m.text} side={m.side} />
          ))}
          {sending && <ChatBubble text="" side="out" typing />}
        </div>

        {error && (
          <p className="mb-2 rounded-2xl bg-red-50 px-4 py-2 text-sm font-medium text-red-600">
            {error}
          </p>
        )}

        {/* Composer */}
        <form onSubmit={send} className="flex items-end gap-2 border-t border-black/5 pt-3">
          <input
            className="field flex-1"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Text them…"
            aria-label="Your message"
          />
          <GradientButton
            type="submit"
            variant="ink"
            className="!px-5 !py-3"
            disabled={!draft.trim() || sending}
          >
            Send
          </GradientButton>
        </form>

        <button
          onClick={() => navigate("/dashboard")}
          className="mx-auto mt-4 text-sm font-semibold text-muted hover:text-ink"
        >
          Done — go to dashboard
        </button>
      </div>
    </WizardShell>
  );
}
