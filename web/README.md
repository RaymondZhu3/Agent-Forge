# Agent Forge — web

React + TypeScript + Vite. No UI framework: hand-written CSS design tokens (`src/styles/app.css`), Lucide icons, SVG charts.

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build -> dist/
```

The dev server proxies `/api` to the backend, so there is no CORS or mixed-content issue. Default target is the Vultr API; override locally:

```bash
VITE_API_TARGET=http://localhost:8000 npm run dev
```

For a production build served from another origin, set `VITE_API_BASE` (e.g. `https://api.example.com/api`) at build time and add that site to `CORS_ORIGINS` on the server.

Pages: `/` agents + templates, `/builder[/:id]`, `/chat/:id`, `/dashboard`, `/runs/:id`.
All data comes from the real API (`src/lib/api.ts`); there are no mock fixtures. Shared contracts live in `src/types.ts` (frozen).
