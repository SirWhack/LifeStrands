# Chat Service Bug Report

## Summary
This document enumerates functional and integration issues in the chat service (FastAPI app and `src/` helpers), with concrete code references and suggested fixes. The most critical items are API contract mismatches with repository docs/tests, duplicated user messages sent to the model, and incomplete/wrong streaming logic that is currently unused.

## Affected Areas
- API handlers: `services/chat-service/main.py`
- Conversation orchestration: `src/conversation_manager.py`
- Context building: `src/context_builder.py`
- WebSockets + streaming helpers: `src/stream_handler.py`, `src/websocket_handler.py`

## High‑Impact Issues

1) API shape diverges from tests/README
- Symptoms:
  - Endpoints implemented with singular nouns and non‑streaming payloads vs. tests expecting plural and streaming.
- Examples:
  - Implemented: `POST /conversation/start`, `POST /conversation/send`, `POST /conversation/{id}/end`.
  - Tests expect: `POST /conversations/start` (201), `POST /conversations/{id}/message` (chunked/streaming), `POST /conversations/{id}/end` (200), `GET /conversations/{id}/history`.
- Impact: Integration tests and gateway paths fail against chat service.
- Fix (short‑term): Add compatibility routes/aliases calling through to existing handlers.
  ```python
  # main.py (add below existing routes)
  @app.post("/conversations/start", status_code=201)
  async def start_conversation_v2(req: StartConversationRequest):
      return await start_conversation(req)

  @app.post("/conversations/{session_id}/end")
  async def end_conversation_v2(session_id: str):
      return await end_conversation(session_id)

  @app.get("/conversations/{session_id}/history")
  async def history_v2(session_id: str):
      return await get_conversation_history(session_id)
  ```
- Fix (streaming): Expose `POST /conversations/{id}/message` that streams server‑sent tokens. See Issue 3.

2) Duplicate user message in model prompt
- Location: `src/conversation_manager.py` → `process_message()`.
- Bug:
  ```python
  # Adds user msg to session...
  session.add_message("user", message)
  # Later iterates last 10 messages (already includes current user msg)
  for msg in session.messages[-10:]:
      ... messages.append({"role": role, "content": msg["content"]})
  # Then adds current user msg again (duplicate)
  messages.append({"role": "user", "content": message})
  ```
- Impact: LLM sees the user’s message twice, degrading quality and wasting tokens.
- Fix: Remove the explicit re‑append, or exclude the last item when iterating.
  ```python
  # Option A: do not re‑append
  # messages.append({"role": "user", "content": message})  # remove

  # Option B: exclude most recent when iterating
  for msg in session.messages[-11:-1]:
      ...
  ```

3) Streaming implementation incomplete and incorrect (not wired)
- Current state: `process_message()` returns a single complete string; `_stream_from_model_chatml()` exists but unused.
- Parsing bug: Iterating `async for line in resp.content` does not guarantee line boundaries (SSE frames can split across chunks). Also filtering with `startswith("data: ")` will drop partial frames.
- Fix:
  - Use `async for raw in resp.content.iter_any():` and buffer/split by `\n\n`.
  - Wire a new handler to expose streaming per tests: `POST /conversations/{id}/message` that yields `data: {...}\n\n` tokens.
  ```python
  # main.py (new route)
  @app.post("/conversations/{session_id}/message")
  async def send_streaming(session_id: str, body: dict):
      user_msg = body.get("content", "")
      async def gen():
          async for tok in conversation_manager.stream_message(session_id, user_msg):
              yield f"data: {json.dumps({"token": tok})}\n\n"
      return StreamingResponse(gen(), media_type="text/event-stream")
  ```
  - In manager, implement `stream_message()` using a fixed `_stream_from_model_chatml()` that properly buffers SSE.

4) NPC service endpoint assumptions may be wrong
- Code assumes raw service URLs: `GET {NPC_SERVICE_URL}/npc/{id}` and `/npc/{id}/prompt`.
- Repo shows gateway routes (`/api/npcs/*`, `/api/npc/*`) and `npc-service` code lacks a visible FastAPI entry file.
- Impact: 404s when fetching NPCs for context; conversations will fail to start.
- Fix: Confirm actual NPC service API; prefer gateway: `http://gateway:8000/api/npc/{id}`; make base URL configurable and add health check/fallback.

## Medium‑Impact Issues

5) Background tasks not cancelled on shutdown
- `ConversationManager.initialize()` creates `_periodic_cleanup()` via `asyncio.create_task` but no handle is stored/cancelled on lifespan shutdown.
- Impact: Potential orphan tasks during reload/shutdown.
- Fix: Store task reference and cancel in FastAPI lifespan shutdown.

6) WebSocket helper API mismatch
- `src/stream_handler.py` and `src/websocket_handler.py` use `websocket.send(...)`; FastAPI’s `WebSocket` requires `send_text(...)`/`send_json(...)`.
- Impact: If these helpers are later wired with FastAPI websockets, sends will fail.
- Fix: Normalize on FastAPI `WebSocket` and use `send_text` or feature‑detect method.

## Low‑Impact / Quality

7) Relationship name extraction is naive
- `_build_relationship_context()` matches single capitalized words; relationship keys like `"Bob Wilson"` won’t match unless both full name encountered. It compensates by always adding up to 2 relationships.
- Fix: Tokenize names and match any token, or use a simple proper‑noun bigram heuristic.

8) Token estimation is coarse
- 4 chars/token heuristic can overshoot limits on multilingual inputs. Not a functional bug, but can trim useful context.
- Fix: Optional tiktoken‑based estimator if available.

## Suggested Next Steps
- Add compatibility REST routes + streaming endpoint to satisfy tests.
- Fix duplicate user message bug.
- Harden/validate NPC service calls via gateway.
- Store and cancel background cleanup tasks on shutdown.
- Align websocket helpers with FastAPI `WebSocket` or remove unused code.

## References
- `services/chat-service/main.py`
- `services/chat-service/src/conversation_manager.py`
- `services/chat-service/src/stream_handler.py`
- `tests/integration/test_conversation_flow.py`
