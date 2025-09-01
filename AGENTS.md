# Repository Guidelines

## Project Structure & Modules
- `services/`: Python microservices (`chat-service`, `npc-service`, `model-service`, `gateway-service`, `summary-service`, `monitor-service`), each with `src/`.
- `frontends/`: React + TypeScript apps (`chat-interface`, `admin-dashboard`).
- `tests/`: Pytest suites under `unit/` and `integration/`.
- `database/`, `monitoring/`, `nginx/`, `scripts/`: infra, seeds, tooling.
- Top-level orchestration: `Makefile`, `docker-compose*.yml`, `.env`.

## Build, Test, and Development
- `make dev-up`: Start full dev stack (Docker; expects LM Studio at `:1234`).
- `make dev-down`: Stop all services. `make logs s=chat-service` for one service.
- `make test` | `make test-unit` | `make test-integration`: Run pytest suites.
- `make migrate` | `make seed`: Apply DB migrations and seed data.
- `make health-check`: Verify service and DB/Redis health.
- Frontends: `cd frontends/chat-interface && npm run dev` (or `build`).

## Coding Style & Naming
- Python: PEP 8, 4‑space indent, docstrings, type hints where practical. Module names `snake_case`; classes `PascalCase`; functions/vars `snake_case`.
- APIs: FastAPI route modules under each service’s `src/`; prefer explicit pydantic schemas.
- Frontend: TypeScript strictness, React hooks; components in `PascalCase.tsx`, files `kebab-case.ts` for utilities.
- Lint/format: Use editor formatters; align with existing patterns (no repo-wide formatter config yet).

## Testing Guidelines
- Framework: `pytest` with fixtures. Place unit tests in `tests/unit/`, integration in `tests/integration/`.
- Naming: `test_*.py` files, `Test*` classes, descriptive test names.
- Coverage: `make test-coverage` prints summary and writes `htmlcov/`.
- Examples: run a single file `python -m pytest tests/unit/test_context_builder.py -v`.

## Commit & Pull Request Guidelines
- Commits: Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`). Current history is mixed—please standardize going forward.
- PRs: Clear title, summary of changes, test evidence (`make test` output), linked issues, and screenshots for UI changes. Touch only one concern per PR.

## Security & Configuration
- Configure via `.env` (see `README.md`). Set strong JWT secrets and database credentials.
- Models: Place GGUF files under `models/` when running locally.
- Data: Use `make backup`/`make restore file=...` before risky changes.

## Architecture Notes
- Event flow: Clients → `gateway-service` → internal services; persistence in PostgreSQL (+pgvector) and Redis for queues/cache.
- Health: Every service exposes `/health`; monitor with Grafana/Prometheus (see `make monitor`).
