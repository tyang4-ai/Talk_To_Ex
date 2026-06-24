import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import WizardShell from "../components/WizardShell";
import Card from "../components/Card";
import GradientButton from "../components/GradientButton";
import TagPicker from "../components/TagPicker";
import { Field, TextAreaField } from "../components/Field";
import { api, errorMessage, type IntakeAnswers } from "../api/client";
import { setDraftPersonaId } from "../lib/draft";

const PERSONALITY_TAGS = [
  "warm",
  "sarcastic",
  "anxious",
  "avoidant",
  "funny",
  "intense",
  "blunt",
  "flirty",
  "moody",
  "caring",
  "competitive",
  "chaotic",
];

const ATTACHMENT_STYLES = ["Secure", "Anxious", "Avoidant", "Disorganized", "Not sure"];

const TIME_OPTIONS = [
  "Days ago",
  "A few weeks",
  "A few months",
  "About a year",
  "Years ago",
];

export default function Intake() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState("");
  const [howYouMet, setHowYouMet] = useState("");
  const [timeSince, setTimeSince] = useState(TIME_OPTIONS[1]);
  const [tags, setTags] = useState<string[]>([]);
  const [attachment, setAttachment] = useState(ATTACHMENT_STYLES[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const intake: IntakeAnswers = {
      nickname: nickname.trim(),
      how_you_met: howYouMet.trim(),
      time_since_breakup: timeSince,
      personality_tags: tags,
      attachment_style: attachment,
    };
    try {
      const persona = await api.createPersona(intake.nickname, intake);
      setDraftPersonaId(persona.id);
      navigate("/import");
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the profile. Try again."));
      setLoading(false);
    }
  }

  return (
    <WizardShell
      step={2}
      totalSteps={5}
      title="Build their profile"
      subtitle="The little things help us nail their voice. Be honest — it's just you."
    >
      <Card>
        <form onSubmit={submit} className="space-y-5">
          <Field
            label="What did you call them?"
            name="nickname"
            required
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="Their name or nickname"
          />

          <TextAreaField
            label="How did you two meet?"
            name="how_you_met"
            rows={3}
            value={howYouMet}
            onChange={(e) => setHowYouMet(e.target.value)}
            placeholder="A class, a party, a dating app, a long story…"
          />

          <div>
            <span className="field-label">How long since the breakup?</span>
            <div className="flex flex-wrap gap-2">
              {TIME_OPTIONS.map((opt) => (
                <button
                  type="button"
                  key={opt}
                  onClick={() => setTimeSince(opt)}
                  aria-pressed={timeSince === opt}
                  className={`rounded-pill border px-4 py-2 text-sm font-semibold transition ${
                    timeSince === opt
                      ? "border-transparent bg-tinder-gradient-135 text-white shadow-pill"
                      : "border-black/15 bg-white text-ink hover:border-tinder-mid/60"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="field-label">Their personality (pick a few)</span>
            <TagPicker options={PERSONALITY_TAGS} selected={tags} onChange={setTags} max={6} />
          </div>

          <div>
            <span className="field-label">Attachment style</span>
            <div className="flex flex-wrap gap-2">
              {ATTACHMENT_STYLES.map((opt) => (
                <button
                  type="button"
                  key={opt}
                  onClick={() => setAttachment(opt)}
                  aria-pressed={attachment === opt}
                  className={`rounded-pill border px-4 py-2 text-sm font-semibold transition ${
                    attachment === opt
                      ? "border-transparent bg-tinder-gradient-135 text-white shadow-pill"
                      : "border-black/15 bg-white text-ink hover:border-tinder-mid/60"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-2xl bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600">
              {error}
            </p>
          )}

          <GradientButton type="submit" fullWidth loading={loading} disabled={!nickname.trim()}>
            Next: bring the chats →
          </GradientButton>
        </form>
      </Card>
    </WizardShell>
  );
}
