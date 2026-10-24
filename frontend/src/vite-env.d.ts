/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend origin for a deployed static build (e.g.
   *  https://help-router-backend.onrender.com). Empty in dev/phone mode, where the
   *  Vite proxy forwards same-origin requests to the local backend. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
