/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AURA_RELAY_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
