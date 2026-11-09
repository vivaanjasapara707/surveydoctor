/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Address of the SurveyDoctor API, e.g. https://surveydoctor-api.onrender.com */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
