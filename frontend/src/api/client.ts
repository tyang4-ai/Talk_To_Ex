/**
 * Axios client + the full REST contract for the backend (plan E5/E6).
 * JWT lives in localStorage under `ttx_token`; a request interceptor attaches it
 * as `Authorization: Bearer <token>`. Every endpoint the wizard calls and every
 * response type the backend must return is centralized here so E6 has one
 * contract to match.
 */
import axios, { type AxiosError, type AxiosInstance } from "axios";

export const TOKEN_KEY = "ttx_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthed(): boolean {
  return !!getToken();
}

const baseURL = import.meta.env.VITE_API_URL || "/api";

export const http: AxiosInstance = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    // 401 → token is stale; drop it so the router bounces to /auth.
    if (error.response?.status === 401) {
      clearToken();
    }
    return Promise.reject(error);
  },
);

/** Normalize an axios error into a human string for inline error UI. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: unknown } | undefined;
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === "string") {
      return detail[0].msg as string;
    }
    if (err.response?.status === 402) return "Payment required to continue.";
    if (err.message) return err.message;
  }
  return fallback;
}

// ───────────────────────── Types (the E6 contract) ─────────────────────────

export type SubscriptionStatus = "inactive" | "active" | "past_due" | "canceled";
export type PersonaStatus = "draft" | "active" | "dormant";

export interface AuthResponse {
  token: string;
}

export interface MeResponse {
  id: number;
  email: string;
  subscription_status: SubscriptionStatus;
}

export interface IntakeAnswers {
  nickname: string;
  how_you_met: string;
  time_since_breakup: string;
  personality_tags: string[];
  attachment_style: string;
}

export interface PersonaSummary {
  id: number;
  name: string;
  slug: string;
  status: PersonaStatus;
}

/** GET /api/personas/{id} — status + parse-preview counts for the wizard. */
export interface PersonaDetail {
  id: number;
  name: string;
  slug: string;
  status: PersonaStatus;
  message_count: number; // total parsed across all uploads
  uploads: UploadResult[];
  distilled: boolean;
  number?: AssignedNumber | null;
}

/** POST /api/personas/{id}/uploads — instant parse preview (spec §10.1). */
export interface UploadResult {
  id: number;
  filename: string;
  format: string;
  message_count: number;
  ex_name: string; // "[ex]" for the "✓ N messages from [ex]" confirmation
  date_start?: string | null;
  date_end?: string | null;
  sample_lines?: string[];
}

/** POST /api/personas/{id}/activate — returns the assigned number for Reveal. */
export interface AssignedNumber {
  e164: string;
  mode: "trial" | "tollfree";
}

export interface ActivateResponse {
  status: PersonaStatus;
  number: AssignedNumber;
}

/** POST /api/personas/{id}/preview — send a turn, get reply bubbles back. */
export interface PreviewResponse {
  bubbles: string[];
}

/** POST /api/billing/checkout — Stripe Checkout session. */
export interface CheckoutResponse {
  url: string; // hosted Checkout URL (primary redirect path)
  session_id?: string; // optional, for stripe-js redirectToCheckout fallback
}

// ───────────────────────────── API functions ─────────────────────────────

export const api = {
  // Auth
  async register(email: string, password: string): Promise<AuthResponse> {
    const { data } = await http.post<AuthResponse>("/auth/register", { email, password });
    return data;
  },
  async login(email: string, password: string): Promise<AuthResponse> {
    const { data } = await http.post<AuthResponse>("/auth/login", { email, password });
    return data;
  },
  async me(): Promise<MeResponse> {
    const { data } = await http.get<MeResponse>("/auth/me");
    return data;
  },

  // Billing
  async checkout(): Promise<CheckoutResponse> {
    const { data } = await http.post<CheckoutResponse>("/billing/checkout", {});
    return data;
  },

  // Persona lifecycle
  async createPersona(name: string, intake: IntakeAnswers): Promise<PersonaSummary> {
    const { data } = await http.post<PersonaSummary>("/personas", { name, intake });
    return data;
  },
  async getPersona(id: number): Promise<PersonaDetail> {
    const { data } = await http.get<PersonaDetail>(`/personas/${id}`);
    return data;
  },
  async uploadFile(
    id: number,
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<UploadResult> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await http.post<UploadResult>(`/personas/${id}/uploads`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return data;
  },
  async uploadPlaintext(id: number, text: string, exName: string): Promise<UploadResult> {
    const { data } = await http.post<UploadResult>(`/personas/${id}/uploads`, {
      text,
      ex_name: exName,
    });
    return data;
  },
  async distill(id: number): Promise<PersonaDetail> {
    const { data } = await http.post<PersonaDetail>(`/personas/${id}/distill`, {});
    return data;
  },
  async activate(id: number): Promise<ActivateResponse> {
    const { data } = await http.post<ActivateResponse>(`/personas/${id}/activate`, {});
    return data;
  },
  async addCorrection(id: number, instruction: string): Promise<{ applied: boolean }> {
    const { data } = await http.post<{ applied: boolean }>(`/personas/${id}/corrections`, {
      instruction,
    });
    return data;
  },
  async preview(id: number, body: string): Promise<PreviewResponse> {
    const { data } = await http.post<PreviewResponse>(`/personas/${id}/preview`, { body });
    return data;
  },
  async setKillSwitch(id: number, enabled: boolean): Promise<{ killed: boolean }> {
    const { data } = await http.post<{ killed: boolean }>(`/personas/${id}/kill`, {
      enabled,
    });
    return data;
  },
};
