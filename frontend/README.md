# Frontend (React + Tailwind)

## Run in development

1. Install deps:
   npm install
2. Start dev server:
   npm run dev

The Vite dev server proxies `/api/*` calls to `http://127.0.0.1:8000`.

## Build

npm run build

Build output is written to `frontend/dist`. When present, FastAPI serves this build at `/`.
