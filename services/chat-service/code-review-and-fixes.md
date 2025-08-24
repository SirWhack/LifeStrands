
# Code Review & Improvement Plan

**Repository scope**: `main.py`, `requirements.txt`, `context_builder.py`, `conversation_manager.py`, `stream_handler.py`, `websocket_handler.py`

**Author**: M365 Copilot (for Sam Wynn)

**Date**: 2025-08-23

---

## TL;DR (Top fixes to apply first)

1. **Fix API mismatch between `conversation_manager` and `main`**: the client calls `/generate/stream` and expects raw JSON lines, while the server provides **SSE** on `/generate`. Update the client to POST `/generate` and parse `data: {json}` lines. (See Patch A.)
2. **Regex & logic bugs in `context_builder`**:
   - Broken sentence split regex in `optimize_for_token_limit`.
   - `union` set computation is missing the operator in `_calculate_relevance_score`.
   (See Patch B.)
3. **Import robustness**: `conversation_manager` uses relative import `.context_builder` which will fail outside a package. Add a safe dual import. (Patch C.)
4. **JWT & anonymous auth**: make WebSocket auth deterministic (return an `anonymous-<ts>` user when no token) and move JWT secret to env var. (Patch D.)
5. **Production hardening**: timeouts/retries for all `aiohttp` calls, better shutdown, structured logs, and consistent schemas. (Guidance & patches below.)

---

## Detailed Review

### 1) API Contract & Streaming

- **Server (`main.py`)** exposes `POST /generate` and, when `stream=True`, returns **Server-Sent Events** (SSE) formatted as `data: {"token": "..."}\n\n` and a final `data: {"done": true}`. ✔️
- **Client (`conversation_manager.py`)** calls `POST /generate/stream` and treats each network line as a standalone JSON document. ❌

**Impact**: No streaming will reach the client; you will likely see timeouts or JSON decode errors.

**Fix**: Align the client with SSE framing and the `/generate` path. Add robust parsing that ignores non-`data:` lines and honors the `{done:true}` sentinel, plus timeouts.

> **Patch A – `conversation_manager._stream_from_model` (SSE-compatible)**
```diff
@@
-    async def _stream_from_model(self, prompt: str, session_id: str) -> AsyncGenerator[str, None]:
-        """Stream response from model service"""
-        try:
-            import aiohttp
-            async with aiohttp.ClientSession() as session:
-                payload = {
-                    "prompt": prompt,
-                    "session_id": session_id,
-                    "stream": True
-                }
-                async with session.post(
-                    f"{self.model_service_url}/generate/stream",
-                    json=payload
-                ) as response:
-                    if response.status == 200:
-                        async for line in response.content:
-                            if line:
-                                try:
-                                    data = json.loads(line.decode().strip())
-                                    if "token" in data:
-                                        yield data["token"]
-                                except json.JSONDecodeError:
-                                    continue
-                    else:
-                        raise Exception(f"Model service error: {response.status}")
-        except Exception as e:
-            logger.error(f"Error streaming from model service: {e}")
-            raise
+    async def _stream_from_model(self, prompt: str, session_id: str) -> AsyncGenerator[str, None]:
+        """Stream response from model service (SSE framing)."""
+        import aiohttp
+        timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_read=300)
+        payload = {
+            "prompt": prompt,
+            "model_type": "chat",
+            "max_tokens": 512,
+            "temperature": 0.7,
+            "top_p": 0.9,
+            "stream": True,
+        }
+        try:
+            async with aiohttp.ClientSession(timeout=timeout) as session:
+                async with session.post(f"{self.model_service_url}/generate", json=payload) as resp:
+                    resp.raise_for_status()
+                    async for raw in resp.content:
+                        if not raw:
+                            continue
+                        line = raw.decode(errors="ignore").strip()
+                        if not line.startswith("data: "):
+                            continue
+                        chunk = line[len("data: "):]
+                        try:
+                            obj = json.loads(chunk)
+                        except json.JSONDecodeError:
+                            continue
+                        if obj.get("done"):
+                            break
+                        token = obj.get("token")
+                        if token is not None:
+                            yield token
+        except Exception as e:
+            logger.error(f"Error streaming from model service: {e}")
+            raise
```

> **Optional**: If you want the model parameters to be configurable per call, thread them through `process_message(...)` and `_stream_from_model(...)` instead of hard-coding.

---

### 2) `context_builder.py` correctness

**Findings**
- `optimize_for_token_limit`: sentence splitter regex is malformed. Use a simple and safe look-behind.
- `_calculate_relevance_score`: `union` is missing the set union operator, which yields a syntax/runtime error.
- Minor: `validate_context_size` & token estimates assume 4 chars/token—fine as a heuristic, but note model variance.

> **Patch B – `context_builder.py` fixes**
```diff
@@
-        sentences = re.split(r'\(?\<=\[.\!?\])\\s\+', context)
+        # Split on sentence boundaries after . ! ?
+        sentences = re.split(r'(?<=[.!?])\s+', context)
@@
-        query_words = set(re.findall(r'\b\w+\b', query_text.lower()))
-        knowledge_words = set(re.findall(r'\b\w+\b', knowledge_text.lower()))
+        query_words = set(re.findall(r'\b\w+\b', query_text.lower()))
+        knowledge_words = set(re.findall(r'\b\w+\b', knowledge_text.lower()))
         if not query_words or not knowledge_words:
             return 0.0
-        intersection = query_words & knowledge_words
-        union = query_words \
-            knowledge_words
+        intersection = query_words & knowledge_words
+        union = query_words | knowledge_words
         # Jaccard similarity
         return len(intersection) / len(union) if union else 0.0
```

> **Nice-to-have**: Consider swapping the overlap heuristic for cosine similarity on hashed TF–IDF or using a compact embedding model if you already depend on one.

---

### 3) Import resilience in `conversation_manager`

When running these modules directly (not as a package), `from .context_builder import ContextBuilder` fails. Provide a dual import.

> **Patch C – dual import**
```diff
@@
-        from .context_builder import ContextBuilder
+        try:
+            from .context_builder import ContextBuilder  # package context
+        except Exception:
+            from context_builder import ContextBuilder   # module context
```

---

### 4) WebSocket auth & hygiene

- Secret is hardcoded. Move to `WS_JWT_SECRET` env var with fallback.
- If no token is provided, return a consistent anonymous id rather than `None`.
- Add read timeouts to avoid stuck awaits.

> **Patch D – `websocket_handler.py` auth & anon**
```diff
@@
-    def __init__(self):
+    def __init__(self):
         self.connection_manager = ConnectionManager()
         self.heartbeat_interval = 30
         self.connection_timeout = 300  # 5 minutes
-        self.jwt_secret = "your-jwt-secret"  # Should be from config
+        import os
+        self.jwt_secret = os.getenv("WS_JWT_SECRET", "dev-only-secret")
         self.cleanup_task = None
@@
-    async def _authenticate_connection(self, websocket, path: str) -> Optional[str]:
+    async def _authenticate_connection(self, websocket, path: str) -> Optional[str]:
@@
-        if "token=" in path:
+        if "token=" in path:
             token = path.split("token=")[1].split("&")[0]
             try:
                 # Decode JWT (in production, use proper validation)
                 payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
                 return payload.get("user_id")
             except jwt.InvalidTokenError:
                 logger.warning("Invalid JWT token in WebSocket connection")
-        # Return anonymous user for demo
-        return f"anonymous_{int(time.time())}"
+        # No/invalid token -> anonymous user for demo
+        return f"anonymous-{int(time.time())}"
```

> **Security note**: In production validate issuer/audience, check expiry (`exp`), and consider rotating secrets.

---

### 5) `main.py` service concerns

- **Readiness**: Some endpoints assume a ready `model_manager`. Add a 503 guard.
- **Shutdown**: `asyncio.get_event_loop()` is deprecated in modern asyncio contexts; prefer `get_running_loop()`. Also, `SIGTERM` doesn’t exist on Windows. Use `signal.CTRL_BREAK_EVENT` where applicable.
- **Schema**: Replace ad-hoc dict for `/embeddings` with a Pydantic model.

> **Patch E – readiness guard & shutdown**
```diff
@@
 @app.post("/generate")
 async def generate_text(request: GenerateRequest):
     """Generate text with streaming or completion mode"""
     try:
+        if not model_manager:
+            raise HTTPException(status_code=503, detail="ModelManager not ready")
@@
 @app.post("/shutdown")
 async def graceful_shutdown():
@@
-    def shutdown_server():
-        os.kill(os.getpid(), signal.SIGTERM)
+    def shutdown_server():
+        if os.name == "nt":
+            os.kill(os.getpid(), signal.CTRL_BREAK_EVENT)
+        else:
+            os.kill(os.getpid(), signal.SIGTERM)
-    asyncio.get_event_loop().call_later(1.0, shutdown_server)
+    asyncio.get_running_loop().call_later(1.0, shutdown_server)
     return {"message": "Shutdown initiated successfully"}
```

> **Patch F – Pydantic model for embeddings**
```diff
@@
-from fastapi import FastAPI, HTTPException
+from fastapi import FastAPI, HTTPException
+from typing import List
@@
-class LoadModelRequest(BaseModel):
+class LoadModelRequest(BaseModel):
     model_type: str
+
+class EmbeddingsRequest(BaseModel):
+    texts: List[str]
@@
-@app.post("/embeddings")
-async def generate_embeddings(request: dict):
+@app.post("/embeddings")
+async def generate_embeddings(request: EmbeddingsRequest):
@@
-        texts = request.get("texts", [])
-        if not texts:
+        texts = request.texts
+        if not texts:
             raise HTTPException(status_code=400, detail="No texts provided")
```

---

### 6) Timeouts, retries, and backpressure

- Add `ClientTimeout` to all `aiohttp` calls (`_validate_npc`, `_get_npc_data`, `_notify_model_service` if switched to HTTP, and in `_stream_from_model`) to avoid hanging awaits.
- Optionally add exponential backoff (e.g., `asyncio.sleep(backoff)` ) on transient network failures.

> **Patch G – sample timeouts**
```diff
@@
-    async def _validate_npc(self, npc_id: str) -> bool:
+    async def _validate_npc(self, npc_id: str) -> bool:
         """Validate NPC exists"""
         try:
-            import aiohttp
-            async with aiohttp.ClientSession() as session:
+            import aiohttp
+            timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
+            async with aiohttp.ClientSession(timeout=timeout) as session:
                 async with session.get(f"{self.npc_service_url}/npc/{npc_id}") as response:
                     return response.status == 200
         except Exception as e:
             logger.error(f"Error validating NPC {npc_id}: {e}")
             return False
@@
-    async def _get_npc_data(self, npc_id: str) -> dict:
+    async def _get_npc_data(self, npc_id: str) -> dict:
         """Get NPC data for context building"""
         try:
-            import aiohttp
-            async with aiohttp.ClientSession() as session:
+            import aiohttp
+            timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
+            async with aiohttp.ClientSession(timeout=timeout) as session:
                 async with session.get(f"{self.npc_service_url}/npc/{npc_id}/prompt") as response:
                     if response.status == 200:
                         return await response.json()
                     else:
                         logger.error(f"Failed to get NPC data: {response.status}")
                         return {}
```

---

### 7) Streaming UX (`stream_handler.py`)

- Good design with `TokenBuffer` and `StreamMetrics`.
- Consider making `buffer_size` configurable per stream and exposing a **minimum flush interval** to avoid starvation on long words.
- Add `try/except` around `websocket.send` to surface payload sizes or slow clients.

**Suggestion (optional):**
```python
# When buffering, also flush on time threshold
last_flush = time.time()
flush_interval = 0.25  # seconds
...
if buffered_text or (time.time() - last_flush) >= flush_interval:
    await self._send_token(websocket, buffered_text or "", session_id)
    last_flush = time.time()
```

---

### 8) Observability & audit (aligned with your preferences)

- **Structured logs**: include `session_id`, `user_id`, `npc_id` in every log line (use a LoggerAdapter or context variables).
- **Metrics**: you already have `/metrics` on the model service. Mirror counters on the conversation/websocket services: active sessions, TTFT, tokens/sec, disconnects, etc. Consider Prometheus format or push to Azure Monitor.
- **Audit trail**: emit one event per message (user->npc and npc->user) with latency, token counts, and any safety filter outcomes. Persist to Cosmos DB serverless (your chosen store) and fan out summaries using **Azure Event Grid** subscriptions for scheduled updates.

---

### 9) API schemas & consistency

Unify message/event envelope across HTTP SSE and WebSockets, e.g.:
```json
{
  "type": "token|stream_start|stream_complete|error",
  "session_id": "...",
  "content": "...",  
  "stats": {"tps": 17.2, "ttft_ms": 180},
  "timestamp": 1699999999
}
```
This lets clients handle either transport with the same parser.

---

### 10) `requirements.txt`

- Versions are pinned—good for reproducibility. Ensure they are compatible with your runtime (Python ≥3.10 recommended).
- Consider adding optional dependencies used in the review (Prometheus client, opentelemetry, pydantic-settings) only if you adopt the suggestions:
```
prometheus-client~=0.20
opentelemetry-sdk~=1.26
opentelemetry-instrumentation-aiohttp-client~=0.47b0
pydantic-settings~=2.5
```

> Tip: add `pip-tools` (or `uv`) for lockfile management if you plan to frequently upgrade.

---

## Smaller polish items

- **Typing**: add explicit return types for public APIs; use `from __future__ import annotations` if needed.
- **Graceful shutdown**: add `shutdown()` coroutines for `ConversationManager` and `WebSocketHandler` (cancel background tasks, close Redis connections, etc.).
- **Rate limiting**: guard `/generate` and WebSocket message rates to avoid abuse.
- **CORS**: if this faces browsers, configure CORS appropriately.

---

## Appendix: Full File Diffs (consolidated)

The patches above are minimal; if you want, I can generate updated files with these changes applied.

---

## Next steps

1. Apply Patches A–G.
2. Run an end-to-end streaming test:
   - Start model service.
   - Start conversation service and open a session.
   - Verify that tokens stream and `stream_complete` is received.
3. Add Prometheus counters/histograms for TTFT and TPS.
4. Wire audit events to Cosmos DB and Event Grid for the scheduled analytics you requested.

---

If you want, I can produce fully updated files and a quick test harness script (`pytest` or a small client) to validate SSE parsing and WebSocket flows.
