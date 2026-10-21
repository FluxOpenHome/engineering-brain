# Engineering Brain – web frontend

Next.js 15 (App Router, TypeScript, Tailwind CSS v4) UI for the Engineering Brain
FastAPI backend. Pages: Documents, Search, Chat (SSE streaming), Wiki (Tiptap editor),
Review (proposal diffs), Compliance (sets, runs, matrix, reviewer overrides) and Specs
(rule check + template-based drafting).

## Requirements

- Node 22+, npm
- Backend reachable from the **browser** (default `http://localhost:8000`). The backend's
  `cors_origins` setting must include this app's origin (`http://localhost:3000` by default).

## Run (development)

```bash
cd web
cp .env.example .env.local        # edit NEXT_PUBLIC_API_URL if the API is elsewhere
npm install
npm run dev                       # http://localhost:3000
```

## Build and run (production)

```bash
npm run build                     # type-checks, lints, produces .next/standalone
npm run start                     # or: node .next/standalone/server.js
```

`npm run lint` runs ESLint (next/core-web-vitals + next/typescript).

## Docker

`NEXT_PUBLIC_*` variables are inlined at build time, so pass the API URL as a build arg:

```bash
docker build -t eb-web --build-arg NEXT_PUBLIC_API_URL=http://api.example.local:8000 .
docker run --rm -p 3000:3000 eb-web
```

## Layout

```
src/
  lib/types.ts        # TypeScript mirror of the backend contract
  lib/api.ts          # typed fetch helpers for every endpoint, SSE parser for /chat/stream
  lib/format.ts       # date / citation / quantity formatting
  lib/usePolling.ts   # poll-while-condition hook (documents 5 s, compliance runs 3 s)
  components/         # small hand-written Tailwind components (ui.tsx, DiffView, WikiEditor, ...)
  app/
    documents/        # upload + list (polls while parsing), detail with propose / compliance actions
    search/           # hybrid search with filters and highlighted hits
    chat/             # conversations, streaming answers, sources panel, citation chips
    wiki/             # tree, list/search, page view, Tiptap markdown editor, archive
    review/           # open proposals, side-by-side / unified diff, accept (with edits) / reject
    compliance/       # sets, requirements (manual / import / extract), runs, matrix, export
    specs/            # Check (GtWR/EARS issues) and Draft (templates, parameters, citations)
```

## Notes

- Dev mode only: no auth UI, no token is sent. Add an `Authorization` header in
  `src/lib/api.ts#apiFetch` when auth is enabled.
- Chat streaming uses `fetch` + `ReadableStream` (EventSource cannot POST). If the stream
  fails before the first `delta`, the UI falls back to `POST /chat`.
- Wiki pages are edited as markdown via `@tiptap/markdown`; the editor round-trips
  `GET /wiki/pages/{slug}.content` → `PUT /wiki/pages/{slug}.content`.
