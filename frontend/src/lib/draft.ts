/**
 * The wizard threads a single draft persona id across steps (Intake → Import →
 * Building → Reveal → Preview). Persist it so a refresh mid-flow doesn't lose
 * the user's place.
 */
const KEY = "ttx_persona_id";

export function setDraftPersonaId(id: number): void {
  localStorage.setItem(KEY, String(id));
}

export function getDraftPersonaId(): number | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function clearDraftPersonaId(): void {
  localStorage.removeItem(KEY);
}
