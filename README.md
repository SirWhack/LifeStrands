# LifeStrands – Dev Notes

This repo contains multiple Python microservices and two frontends. See AGENTS.md for full repo guidelines. The notes below pin the critical environment variables for local/dev vs Docker so background processing (summaries/memories) works reliably.

## Key Environment Variables

- REDIS_URL: Must be identical for chat-service and summary-service.
  - Local/dev (native): `REDIS_URL=redis://localhost:6379`
  - Docker: provided by compose as `redis://:REDIS_PASSWORD@redis:6379`

- NPC_SERVICE_URL: Must point to the running NPC service for all services that call it.
  - Local/dev (native): `NPC_SERVICE_URL=http://localhost:8003`
  - Docker: provided by compose as `http://npc-service:8003` (or fixed IP in native-model compose)

- LM_STUDIO_BASE_URL / MODEL_SERVICE_URL: Where the model endpoint (LM Studio) is reachable.
  - Local/dev: `LM_STUDIO_BASE_URL=http://localhost:1234/v1` (default works if LM Studio is listening on 1234)
  - Docker: compose uses `http://host.docker.internal:1234/v1` so containers can reach the host.

Defaults in code now prefer localhost for native runs and are overridden by docker-compose in containers.

## Running Integration Tests

- Ensure services are running and share the same Redis:
  - If running natively, start Redis on localhost:6379, then export `REDIS_URL=redis://localhost:6379` for both chat and summary.
  - If using Docker, `make dev-up` brings up Redis and sets `REDIS_URL` inside containers.

- Start the minimum services for tests: chat-service (8002), npc-service (8003), summary-service (8004). Model/gateway tests skip if unavailable.

- Run: `make test-integration`

If conversation memories don’t appear, verify:
- Chat and summary see the same Redis (`REDIS_URL` identical).
- Summary service can reach NPC service (`NPC_SERVICE_URL`).
- LM Studio (or model endpoint) is reachable if you want summaries generated.

## Docker Compose

- `docker-compose.yml` and `docker-compose.native-model.yml` already set consistent `REDIS_URL` and `NPC_SERVICE_URL` for all services. Override via `.env` if needed.

## Frontend: Ending Conversations + Dev Mode

- The chat UI now includes an “End Conversation” button in the header.
  - It disconnects and reconnects the WebSocket, which ends server-side sessions and triggers summaries.
- A “Dev Mode” checkbox toggles display of per-assistant message metrics (approximate tokens and response time) under each chat bubble.

## Database Cleanup

Tests may create “Test Character” NPCs. Remove them with:

- Dry run: `python scripts/cleanup_test_npcs.py`
- Execute: `python scripts/cleanup_test_npcs.py --execute`

Set `DATABASE_URL` if your DB differs from the default.
