# FitAI frontend

React 19 + TypeScript + Vite single-page app. It talks to the FastAPI backend through `/api/v1` and signs users
in with Supabase Auth. See the [root README](../README.md) for the full project overview.

## Commands

```bash
npm install
npm run dev           # Vite dev server on http://127.0.0.1:5173 (proxies /api/v1 to the backend)
npm run lint          # oxlint
npm run type-check    # tsc -b
npm test              # vitest (jsdom)
npm run build         # type-check + production build into dist/
npm run check:bundle  # fail if dist/ contains secrets or source maps
```

## Configuration

Copy `.env.example` to `.env.local`. `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are required; both are
public. Leave `VITE_API_BASE_URL` unset in development. Everything prefixed `VITE_` ends up in the browser
bundle, so never put a secret there.

## Layout

```text
src/
├── pages/        Landing, Login, Chat, Library, Memory, Plan, Progress, Profile
├── components/   chat, layout, plan, progress and shared UI
├── services/     API client, Supabase client, speech helpers
├── context/      auth context
├── hooks/        shared hooks
├── types/        shared TypeScript types
└── utils/        date, markdown and URL helpers
```

Voice dictation uses the browser's Web Speech API; see [`SPEECH_TO_TEXT.md`](SPEECH_TO_TEXT.md).
Deployment headers and SPA rewrites for Vercel live in [`vercel.json`](vercel.json).
