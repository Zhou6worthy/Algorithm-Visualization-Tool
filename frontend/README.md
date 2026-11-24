# AlgoViz Workbench Frontend

Vue 3 + TypeScript + Vite frontend for the M4 Two Sum teaching workbench.

## Development

Prerequisite: Node.js 20+.

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/static/workbench/`. Vite proxies `/api` and `/health`
to `http://127.0.0.1:8000`, so start the backend first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn algoviz.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Production build

```powershell
cd frontend
npm run typecheck
npm run build
```

The build output is written to `../algoviz/api/static/workbench/`. FastAPI then
serves the workbench at `/`; the legacy video-factory GUI remains at `/legacy`.

## Test

```powershell
npm run typecheck
```

The end-to-end test lives at the repository root:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts\m4_browser_check.py
```
