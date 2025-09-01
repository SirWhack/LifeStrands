Admin Dashboard (Frontend) — Build & Stability Report

Status Summary
- Containerization: Dockerfile (node:18-alpine) builds Vite app and serves via `serve` on port 3000.
- Compose: Service defined with port 3002:3000 and env placeholders; build runs successfully.

Stability Notes
- Code previously targeted monitoring websocket at ws://localhost:8006; monitor-service runs on 8005.

Improvements (Applied)
- Updated monitoring websocket to route via Gateway at `ws://localhost:8000/monitor/ws` for consistency.

Improvements (Backlog)
- Introduce Vite env variables (VITE_API_BASE_URL, VITE_MONITOR_WS_URL) and read via `import.meta.env`.

Validation
- Integration smoke test exercises backend /health endpoints; UI build validated by Dockerfile.


