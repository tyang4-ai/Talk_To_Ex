/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_STRIPE_PUBLISHABLE_KEY: string;
  /** Zelle handle for the tip jar — set in the gitignored .env.local, kept out of the repo. */
  readonly VITE_ZELLE_HANDLE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
