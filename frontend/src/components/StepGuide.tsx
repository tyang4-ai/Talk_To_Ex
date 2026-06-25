import type { ReactNode } from "react";

export interface GuideStep {
  title: string;
  detail?: ReactNode;
  /** Optional path to your OWN annotated screenshot (spec §27 — not forum-lifted). */
  image?: string;
}

interface StepGuideProps {
  platform: string;
  emoji: string;
  steps: GuideStep[];
  /** A short note rendered under the steps (e.g. the plaintext fallback hint). */
  note?: ReactNode;
  /** Optional link to an external how-to, rendered under the steps/note. */
  tutorial?: { label: string; url: string };
}

/**
 * Numbered per-platform export walkthrough (spec §10.1). The numbering encodes a
 * real ordered sequence — the friend must do step N before N+1.
 */
export default function StepGuide({ platform, emoji, steps, note, tutorial }: StepGuideProps) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-2xl" aria-hidden>
          {emoji}
        </span>
        <h3 className="text-display-md font-bold text-ink">{platform}</h3>
      </div>
      <ol className="space-y-3">
        {steps.map((step, i) => (
          <li key={i} className="flex gap-3">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-pill bg-tinder-gradient-135 text-sm font-bold text-white">
              {i + 1}
            </span>
            <div className="pt-0.5">
              <p className="font-semibold text-ink">{step.title}</p>
              {step.detail && <p className="mt-0.5 text-sm text-muted">{step.detail}</p>}
              {step.image && (
                <img
                  src={step.image}
                  alt={step.title}
                  loading="lazy"
                  className="mt-2 max-h-56 w-full rounded-md border border-hairlinesoft object-contain"
                />
              )}
            </div>
          </li>
        ))}
      </ol>
      {note && (
        <p className="mt-4 rounded-md bg-surfacesoft px-4 py-3 text-sm text-muted">
          {note}
        </p>
      )}
      {tutorial && (
        <a
          href={tutorial.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-block text-sm font-semibold text-rausch"
        >
          ▶ {tutorial.label}
        </a>
      )}
    </div>
  );
}
