# NPC Service Code Review

This review covers `services/npc-service/src`: `auth.py`, `embedding_manager.py`, `error_handler.py`, `life_strand_schema.py`, and `npc_repository.py`.

Methodology: analyzed architecture, data flow, security posture, async usage, SQL patterns, error handling, and maintainability; validated against the repository’s tests and service interactions.

## Issues

1) Location: `src/auth.py` L14
- Severity: CRITICAL
- Issue: Insecure default JWT secret (`default-secret-change-in-production`).
- Risk: Token forgery; complete bypass of auth in non‑prod setups.
- Solution:
  ```python
  self.jwt_secret = os.getenv("JWT_SECRET")
  if not self.jwt_secret:
      raise RuntimeError("JWT_SECRET must be set")
  ```
- Rationale: Fails safe and prevents deployments with weak secrets.

2) Location: `src/npc_repository.py` L16
- Severity: CRITICAL
- Issue: Hardcoded default `database_url` with `user:pass` fallback.
- Risk: Credentials leakage, connecting to unintended local DB.
- Solution:
  ```python
  url = database_url or os.getenv("DATABASE_URL")
  if not url:
      raise RuntimeError("DATABASE_URL must be set")
  self.database_url = url
  ```
- Rationale: Enforces explicit configuration; avoids insecure defaults.

3) Location: `src/npc_repository.py` L134–142
- Severity: HIGH
- Issue: `json.loads(row["life_strand_data"])` assumes text; asyncpg often returns dict for JSONB.
- Risk: TypeError at runtime; data retrieval fails.
- Solution:
  ```python
  raw = row["life_strand_data"]
  life = raw if isinstance(raw, dict) else json.loads(raw)
  return life
  ```
- Rationale: Robust across driver codecs; prevents crashes.

4) Location: `src/npc_repository.py` L33–76
- Severity: HIGH
- Issue: Runtime DDL (`CREATE EXTENSION`, tables, indexes) in service init.
- Risk: Startup latency, migrations racing across instances, permissions failure in managed DBs.
- Solution: Move all DDL to migrations (e.g., Alembic) and keep service init to connectivity checks.
- Rationale: Predictable deploys, least privilege, faster boot.

5) Location: `src/npc_repository.py` L417–436; L365–394
- Severity: HIGH
- Issue: Query patterns won’t use GIN index; `personality_traits::text ILIKE` defeats JSONB index.
- Risk: Slow scans under load.
- Solution: Use JSONB operators or GIN‑friendly queries:
  ```sql
  -- Example containment by trait
  WHERE personality_traits ?| array[$1]
  -- or
  WHERE personality_traits @> to_jsonb(ARRAY[$1])
  ```
  And add appropriate GIN index (jsonb_ops) if needed.
- Rationale: Enables index usage; improves latency and throughput.

6) Location: `src/npc_repository.py` L120–121, 194, 315, 334, 523, 535
- Severity: MEDIUM
- Issue: Using `datetime.utcnow()` (naive) with `TIMESTAMPTZ` columns.
- Risk: Ambiguous timestamps, implicit timezone assumptions.
- Solution: Use UTC‑aware timestamps or server‑side `now()`:
  ```python
  from datetime import datetime, timezone
  datetime.now(timezone.utc)
  # Or in SQL: updated_at = now()
  ```
- Rationale: Correct time semantics; avoids tz bugs.

7) Location: `src/embedding_manager.py` L12–20
- Severity: MEDIUM
- Issue: Embeddings disabled returns zero vectors silently.
- Risk: Downstream vector search polluted with identical vectors.
- Solution: Return `None` or raise when embeddings are required; or gate vector features by `is_enabled()` at call sites.
- Rationale: Fails loudly; preserves data integrity.

8) Location: `src/embedding_manager.py` L58–75
- Severity: MEDIUM
- Issue: `_post_with_retries` has no jitter and retries on 4xx.
- Risk: Thundering herd, unnecessary retries on client errors.
- Solution:
  ```python
  if 400 <= response.status < 500:
      return await response.json()
  delay = base_delay * (2 ** attempt) * (0.8 + random.random()*0.4)
  ```
- Rationale: Backoff hygiene; reduces contention and noise.

9) Location: `src/npc_repository.py` L243–252
- Severity: MEDIUM
- Issue: Building dynamic `WHERE` OK, but `LIMIT` only; no `OFFSET` for pagination in `query_npcs`.
- Risk: Cursoring/paging not supported; poor UX for large sets.
- Solution: Accept `offset` and add `OFFSET ${param_count+1}`.
- Rationale: Proper pagination support.

10) Location: `src/life_strand_schema.py` L226–241
- Severity: MEDIUM
- Issue: Sorting memories by string timestamp.
- Risk: Misorder if non‑ISO or missing timezone info.
- Solution: Parse to datetime safely:
  ```python
  def _ts(m):
      t = m.get("timestamp", "")
      try:
          return datetime.fromisoformat(t.replace("Z","+00:00"))
      except Exception:
          return datetime.min
  merged["memories"] = sorted(merged["memories"], key=_ts, reverse=True)[:50]
  ```
- Rationale: Deterministic ordering.

11) Location: `src/auth.py` L39–87
- Severity: MEDIUM
- Issue: No audience (`aud`) validation; permissive role/permission checks.
- Risk: Token replay across services; privilege confusion.
- Solution: Validate `aud` against service; normalize RBAC (admin as role, not permission), enforce scopes.
- Rationale: Principle of least privilege; multi‑service safety.

12) Location: `src/npc_repository.py` L275–304
- Severity: LOW
- Issue: `get_npc_for_prompt` slices lists but doesn’t de‑duplicate or prioritize by importance for knowledge/memories.
- Risk: Suboptimal prompt quality.
- Solution: Sort by explicit `importance`/recency; de‑dupe topics.
- Rationale: Better context fidelity.

13) Location: `src/life_strand_schema.py` L388–443
- Severity: LOW
- Issue: `sanitize_life_strand` may cut mid‑word and drops trailing ellipsis spacing.
- Risk: Minor readability loss.
- Solution: Prefer word boundary and add unicode‑aware truncate helper.
- Rationale: Cleaner UX.

14) Location: `src/error_handler.py` (entire file)
- Severity: LOW
- Issue: Not integrated with a FastAPI app.
- Risk: Inconsistent error surfacing if/when API endpoints are added.
- Solution: Add FastAPI exception handlers and use `handle_service_error` in routes.
- Rationale: Uniform errors and logs.

15) Location: General (service root)
- Severity: MEDIUM
- Issue: No FastAPI entry (`main.py`) for NPC API; tests reference routes like `/npcs`.
- Risk: Integration via HTTP will fail; chat service calls may 404.
- Solution: Provide `main.py` exposing REST endpoints that wrap `NPCRepository` and `AuthManager`.
- Rationale: Completes the service contract.

## Summary
Strong foundational layering: validation (`jsonschema` + custom rules), repository abstraction, and embedding manager. Main risks are configuration/security defaults, DB initialization in process, and JSON handling assumptions. Query patterns can be improved to leverage indexes. Async patterns and error handling are mostly solid.

## Priority Actions
- 1) Remove insecure defaults for `JWT_SECRET` and `DATABASE_URL` (CRITICAL).
- 2) Fix JSONB handling in `get_npc` to accept dict or str (HIGH).
- 3) Move DDL to migrations and keep service init minimal (HIGH).

## Recommendations
- Architecture: add `main.py` with authenticated endpoints, integrate `error_handler`, and centralize config via `pydantic-settings`.
- Security: validate `aud`, use UTC‑aware timestamps, and adopt secrets management (.env + vault for prod).
- Performance: switch trait/text filters to JSONB operators; add pagination/offset; consider read replicas.
- Testing: add unit tests for validator merge/sanitize, repository JSONB handling, and integration tests for endpoints.
- Ops: provide Alembic migrations; add health checks and readiness.
