Life Strands Summary Service — Code Review, Bug Fixes & Improvements
Reviewer: M365 Copilot
Date: 2025‑08‑23 (UTC)
Scope: main.py, summary_generator.py, change_extractor.py, memory_updater.py, queue_consumer.py

🔎 Executive Summary
Your service has strong foundations (LLM-driven summarization, change extraction, Redis queue, async workers). The main issues are API mismatches and contract drift:

main.py calls functions that don’t exist (generate_conversation_summary, extract_changes) and expects a different change schema than your extractor actually returns.
Change schema inconsistency: main.py expects a dict of lists with confidence, but ChangeExtractor emits a list of change objects with confidence_score.
Mixed service URLs: some modules hard-code http://localhost:8003 instead of using your environment variables (e.g., NPC_SERVICE_URL, MODEL_SERVICE_URL).
Retry flow not wired: you read from summary_queue:failed but never push to it after retries are exhausted.
Below are ready-to-apply diffs to fix all of the above, plus reliability/observability improvements and minimal metrics.

✅ Critical Bugs & Fixes
1) main.py — Broken Calls & Schema Alignment
Problems

Calls non-existent methods: SummaryGenerator.generate_conversation_summary(...), ChangeExtractor.extract_changes(...).
Expects changes shaped as a dict, but your extractor returns a list of change dicts with confidence_score.
Fix (diff) — keep your existing src. package imports; align method calls and auto‑apply logic; fetch NPC Life Strand to pass to the extractor.
--- a/main.py
+++ b/main.py
@@
-from src.queue_consumer import QueueConsumer
-from src.summary_generator import SummaryGenerator
-from src.change_extractor import ChangeExtractor
-from src.memory_updater import MemoryUpdater
+from src.queue_consumer import QueueConsumer
+from src.summary_generator import SummaryGenerator
+from src.change_extractor import ChangeExtractor
+from src.memory_updater import MemoryUpdater
+import aiohttp
@@
-summary_generator = SummaryGenerator(model_service_url)
-change_extractor = ChangeExtractor()
+summary_generator = SummaryGenerator(model_service_url)
+change_extractor = ChangeExtractor(model_service_url)
 memory_updater = MemoryUpdater(npc_service_url)
@@
 @app.post("/summary/generate")
 async def generate_summary(request: GenerateSummaryRequest):
     """Generate conversation summary and extract Life Strand changes"""
     try:
-        # Generate summary
-        summary = await summary_generator.generate_conversation_summary(
-            request.session_id,
-            request.npc_id,
-            request.user_id,
-            request.messages
-        )
-        # Extract potential changes
-        changes = await change_extractor.extract_changes(
-            request.npc_id,
-            request.messages,
-            summary
-        )
+        # Generate a concise summary from the messages
+        summary = await summary_generator.generate_summary(request.messages)
+
+        # Fetch NPC Life Strand context and extract changes
+        life_strand = await _fetch_life_strand(request.npc_id)
+        changes = await change_extractor.analyze_conversation(request.messages, life_strand)
@@
         return {
             "session_id": request.session_id,
             "summary": summary,
-            "extracted_changes": changes,
-            "auto_apply": await _should_auto_apply(changes)
+            "extracted_changes": changes,
+            "auto_apply": _should_auto_apply_list(changes)
         }
@@
 class ApplyUpdatesRequest(BaseModel):
     npc_id: str
-    updates: Dict[str, Any]
+    changes: List[Dict[str, Any]]
@@
 @app.post("/summary/apply-updates")
 async def apply_npc_updates(request: ApplyUpdatesRequest):
     """Apply approved changes to NPC Life Strand"""
     try:
-        success = await memory_updater.apply_updates(
-            request.npc_id,
-            request.updates
-        )
-        if success:
-            logger.info(f"Applied updates to NPC {request.npc_id}")
-            return {"message": "Updates applied successfully"}
-        else:
-            raise HTTPException(status_code=404, detail="NPC not found")
+        await memory_updater.apply_changes(request.npc_id, request.changes)
+        logger.info(f"Applied updates to NPC {request.npc_id}")
+        return {"message": "Updates applied successfully"}
     except HTTPException:
         raise
@@
-@app.get("/npc/{npc_id}/pending-updates")
-async def get_pending_updates(npc_id: str):
-    """Get pending Life Strand updates for review"""
-    try:
-        updates = await memory_updater.get_pending_updates(npc_id)
-        return {"pending_updates": updates}
-    except Exception as e:
-        logger.error(f"Error getting pending updates for NPC {npc_id}: {e}")
-        raise HTTPException(status_code=500, detail=str(e))
-
-@app.post("/npc/{npc_id}/approve-update/{update_id}")
-async def approve_pending_update(npc_id: str, update_id: str):
-    """Approve a pending Life Strand update"""
-    try:
-        success = await memory_updater.approve_update(npc_id, update_id)
-        if success:
-            return {"message": "Update approved and applied"}
-        else:
-            raise HTTPException(status_code=404, detail="Update not found")
-    except HTTPException:
-        raise
-    except Exception as e:
-        logger.error(f"Error approving update {update_id} for NPC {npc_id}: {e}")
-        raise HTTPException(status_code=500, detail=str(e))
-
-@app.delete("/npc/{npc_id}/reject-update/{update_id}")
-async def reject_pending_update(npc_id: str, update_id: str):
-    """Reject a pending Life Strand update"""
-    try:
-        success = await memory_updater.reject_update(npc_id, update_id)
-        if success:
-            return {"message": "Update rejected"}
-        else:
-            raise HTTPException(status_code=404, detail="Update not found")
-    except HTTPException:
-        raise
-    except Exception as e:
-        logger.error(f"Error rejecting update {update_id} for NPC {npc_id}: {e}")
-        raise HTTPException(status_code=500, detail=str(e))
+# NOTE: pending-updates/approve/reject endpoints were removed because
+# they are not implemented in MemoryUpdater. Re-add them when ready.
@@
-async def _should_auto_apply(changes: Dict[str, Any]) -> bool:
-    """Determine if changes should be auto-applied based on confidence scores"""
-    try:
-        # Get auto-approval threshold from environment
-        import os
-        threshold = float(os.getenv("SUMMARY_AUTO_APPROVAL_THRESHOLD", "0.8"))
-        # Check confidence scores for all changes
-        for change in changes.get("memory_updates", []):
-            if change.get("confidence", 0) < threshold:
-                return False
-        for change in changes.get("relationship_updates", []):
-            if change.get("confidence", 0) < threshold:
-                return False
-        for change in changes.get("knowledge_updates", []):
-            if change.get("confidence", 0) < threshold:
-                return False
-        return True
-    except Exception as e:
-        logger.error(f"Error determining auto-apply status: {e}")
-        return False
+def _should_auto_apply_list(changes: List[Dict[str, Any]]) -> bool:
+    """Auto-apply only if every change meets the confidence threshold."""
+    try:
+        threshold = float(os.getenv("SUMMARY_AUTO_APPROVAL_THRESHOLD", "0.8"))
+        if not changes:
+            return False
+        for change in changes:
+            if float(change.get("confidence_score", 0.0)) < threshold:
+                return False
+        return True
+    except Exception as e:
+        logger.error(f"Error determining auto-apply status: {e}")
+        return False
@@
-async def get_service_stats():
+async def get_service_stats():
     """Get service processing statistics"""
     try:
         stats = {
             "total_summaries_generated": summary_generator.get_total_summaries(),
-            "total_updates_applied": memory_updater.get_total_updates(),
             "queue_status": await queue_consumer.get_queue_status(),
-            "auto_approval_rate": await _get_auto_approval_rate()
+            "total_updates_applied": memory_updater.get_total_updates()
         }
         return stats
     except Exception as e:
         logger.error(f"Error getting service stats: {e}")
         raise HTTPException(status_code=500, detail=str(e))
+
+async def _fetch_life_strand(npc_id: str) -> Dict[str, Any]:
+    """Fetch NPC Life Strand from the NPC service for change extraction."""
+    try:
+        async with aiohttp.ClientSession() as session:
+            async with session.get(f"{npc_service_url}/npcs/{npc_id}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
+                if resp.status == 200:
+                    return await resp.json()
+                logger.warning(f"NPC service returned {resp.status} for npc_id={npc_id}")
+                return {}
+    except Exception as e:
+        logger.error(f"Error fetching life strand for NPC {npc_id}: {e}")
+        return {}
.

Why: Aligns main.py to the real class APIs and to the canonical change schema (list with confidence_score). Also removes unreachable endpoints and fixes stats.

2) Consistent Service URLs & DI (Dependency Injection)
Problems

summary_generator.py and change_extractor.py use hard-coded NPC URLs; main.py uses env vars.
Make both classes accept an optional npc_service_url and fall back to env.
Fix (diff)

summary_generator.py
--- a/summary_generator.py
+++ b/summary_generator.py
@@
-import asyncio
-import json
-import logging
-from typing import List, Dict, Any, Optional
-import aiohttp
-from datetime import datetime
-import re
+import asyncio, json, logging, os, re
+from typing import List, Dict, Any, Optional
+import aiohttp
+from datetime import datetime
@@
-class SummaryGenerator:
-    """Generate conversation summaries using LLM"""
-    def __init__(self, model_service_url: str = "http://host.docker.internal:8001"):
-        self.model_service_url = model_service_url
+class SummaryGenerator:
+    """Generate conversation summaries using LLM"""
+    def __init__(self, model_service_url: str = "http://host.docker.internal:8001", npc_service_url: Optional[str] = None):
+        self.model_service_url = model_service_url
+        self.npc_service_url = npc_service_url or os.getenv("NPC_SERVICE_URL", "http://localhost:8003")
@@
     async def _get_npc_name(self, npc_id: str) -> str:
         """Get NPC name from NPC service"""
         try:
             async with aiohttp.ClientSession() as session:
-                async with session.get(
-                    f"http://localhost:8003/npcs/{npc_id}/summary"
-                ) as response:
+                async with session.get(
+                    f"{self.npc_service_url}/npcs/{npc_id}/summary",
+                    timeout=aiohttp.ClientTimeout(total=5)
+                ) as response:
                     if response.status == 200:
                         data = await response.json()
                         return data.get("name", "Character")


change_extractor.py
--- a/change_extractor.py
+++ b/change_extractor.py
@@
-import asyncio
-import json
-import logging
-from typing import List, Dict, Any, Optional
-import aiohttp
-import re
-from datetime import datetime
+import asyncio, json, logging, os, re
+from typing import List, Dict, Any, Optional
+import aiohttp
+from datetime import datetime
@@
-class ChangeExtractor:
-    """Extract potential Life Strand changes from conversations"""
-    def __init__(self, model_service_url: str = "http://host.docker.internal:8001"):
-        self.model_service_url = model_service_url
-        self.confidence_threshold = 0.6
+class ChangeExtractor:
+    """Extract potential Life Strand changes from conversations"""
+    def __init__(self, model_service_url: str = "http://host.docker.internal:8001", npc_service_url: Optional[str] = None):
+        self.model_service_url = model_service_url
+        self.npc_service_url = npc_service_url or os.getenv("NPC_SERVICE_URL", "http://localhost:8003")
+        self.confidence_threshold = 0.6
@@
     async def _get_npc_data(self, npc_id: str) -> Dict[str, Any]:
         """Get NPC data from NPC service"""
         try:
             async with aiohttp.ClientSession() as session:
-                async with session.get(f"http://localhost:8003/npcs/{npc_id}") as response:
+                async with session.get(f"{self.npc_service_url}/npcs/{npc_id}",
+                                       timeout=aiohttp.ClientTimeout(total=5)) as response:
                     if response.status == 200:
                         return await response.json()


Why: Prevents environment drift and container/host mismatches with a single source of truth.

3) Queue failure flow — actually push to summary_queue:failed
Problem

After retry limit, messages are never pushed to the :failed list, so /queue/retry-failed doesn’t do anything.
Fix (diff)
--- a/queue_consumer.py
+++ b/queue_consumer.py
@@
     async def handle_processing_error(self, error: Exception, message: Dict[str, Any]):
         """Handle failed summary generation"""
         try:
             session_id = message.get("session_id", "unknown")
             retry_count = message.get("retry_count", 0)
             max_retries = 3
             logger.error(f"Processing error for session {session_id}: {error}")
             if retry_count < max_retries:
                 # Retry the message
                 retry_message = message.copy()
                 retry_message["retry_count"] = retry_count + 1
                 retry_message["last_error"] = str(error)
                 retry_message["retry_at"] = datetime.utcnow().isoformat()
                 # Add back to queue with delay
                 await asyncio.sleep(min(60 * (retry_count + 1), 300))  # Exponential backoff, max 5 min
                 await self.redis_client.lpush(
                     "summary_queue",
                     json.dumps(retry_message, default=str)
                 )
                 logger.info(f"Queued retry #{retry_count + 1} for session {session_id}")
             else:
-                # Max retries reached, store error
-                await self._store_processing_error(session_id, error, message)
-                logger.error(f"Max retries reached for session {session_id}, storing error")
+                # Max retries reached: move to failed queue and store error
+                await self.redis_client.lpush(
+                    "summary_queue:failed",
+                    json.dumps(message, default=str)
+                )
+                await self._store_processing_error(session_id, error, message)
+                logger.error(f"Max retries reached for session {session_id}, moved to failed queue")
         except Exception as e:
             logger.error(f"Error handling processing error: {e}")


Why: Makes the /queue/retry-failed path effective.

4) Initialize downstream dependencies in QueueConsumer
Problem

QueueConsumer.initialize() pings Redis but skips initializing SummaryGenerator, ChangeExtractor, MemoryUpdater (so their health checks never run).
Fix (diff)
--- a/queue_consumer.py
+++ b/queue_consumer.py
@@
     async def initialize(self):
         """Initialize Redis connection and prepare consumer"""
         try:
             self.redis_client = redis.from_url(self.redis_url)
             await self.redis_client.ping()
+            await self.summary_generator.initialize()
+            await self.change_extractor.initialize()
+            await self.memory_updater.initialize()
             logger.info("QueueConsumer initialized successfully")
         except Exception as e:
             logger.error(f"Failed to initialize QueueConsumer: {e}")
             raise


Why: Fail fast and surface outages early.

5) Minimal metrics for /stats
Problem

main.py expects memory_updater.get_total_updates() but the method doesn’t exist.
Fix (diff)
--- a/memory_updater.py
+++ b/memory_updater.py
@@
 class MemoryUpdater:
     """Apply approved changes to NPC Life Strands"""
     def __init__(self, npc_service_url: str = "http://localhost:8003"):
         self.npc_service_url = npc_service_url
         self.max_memories_per_npc = 50
         self.memory_importance_threshold = 3
+        self._total_updates_applied = 0
@@
     async def apply_changes(self, npc_id: str, changes: List[Dict[str, Any]]):
         """Apply auto-approved changes to Life Strand"""
         try:
             if not changes:
                 logger.debug(f"No changes to apply for NPC {npc_id}")
                 return
@@
-        await self._update_npc(npc_id, updated_life_strand)
+        await self._update_npc(npc_id, updated_life_strand)
+        self._total_updates_applied += len(changes)
         logger.info(f"Applied {len(changes)} changes to NPC {npc_id}")
     except Exception as e:
         logger.error(f"Error applying changes to NPC {npc_id}: {e}")
+    def get_total_updates(self) -> int:
+        return self._total_updates_applied


Why: Restores /stats parity.

🧭 API & Contract Alignment
Canonical change object (what ChangeExtractor already emits):
{
  "change_type": "personality_changed | relationship_updated | status_updated | knowledge_learned | memory_added | emotional_impact",
  "change_summary": "string",
  "change_data": { "...type-specific keys..." },
  "confidence_score": 0.0
}

Auto‑approval should be based on each change’s confidence_score across a list of changes (patched above as _should_auto_apply_list).

/summary/generate now returns:

summary: str
extracted_changes: List[Change]
auto_apply: bool
(Optional enhancement: also return key_points and a quick emotional_impact to help clients render highlights.)

🛡️ Reliability, Observability, Resilience
Correlation IDs: Thread session_id through logs (consider a LoggerAdapter or struct‑logging so it’s present on every line).
Structured logging: Output JSON logs to make Kusto/ELK/Azure Monitor queries easier.
Circuit breakers & backoff: You have exponential retry delays; consider short‑circuiting downstream calls after repeated failures.
Backpressure: Pause or slow consumers if queue length breaches a threshold (e.g., temporarily reduce concurrency).
🔐 Security & Data Hygiene
Validate FastAPI inputs (e.g., roles limited to user|assistant, content length caps, non-empty arrays).
Ensure timeouts on all outbound calls (LLM/NPC/Redis interactions are largely covered, keep them consistent).
Avoid logging raw conversation text; if needed, redact or sample.
🧪 Quick Tests / How to Validate
Unit (with pytest-asyncio & mocks):

SummaryGenerator.generate_summary returns a non-empty string for a normal transcript.
ChangeExtractor.analyze_conversation returns List[change] and filters by confidence_score >= threshold.
QueueConsumer.handle_processing_error moves an item to summary_queue:failed after 3 retries.
Integration (manual):

Start the API. POST /summary/generate with a short transcript including both user and assistant messages; verify JSON shape and that auto_apply is True/False as expected given the SUMMARY_AUTO_APPROVAL_THRESHOLD.
Enqueue a message to Redis, kill the model service to force retries, then check that /queue/retry-failed actually requeues items from summary_queue:failed.
🗂️ Project Hygiene
Imports/package layout: You are using src. in main.py and relative imports inside modules, which implies a package. Keep that structure (as patched). Ensure your runtime includes -m execution or correct PYTHONPATH so src is resolvable.
Configuration: Standardize on env vars: MODEL_SERVICE_URL, NPC_SERVICE_URL, REDIS_URL, SUMMARY_AUTO_APPROVAL_THRESHOLD. Constructors now pick these up consistently.
📦 Bonus UX Improvements (optional)
Include key_points (from SummaryGenerator.extract_key_points) in /summary/generate.
Include a compact emotional_impact object to aid client rendering/moderation.
📜 Appendix — JSON Robustness Pattern
A small helper to defensively parse model JSON responses:


Use it in ChangeExtractor where strict JSON is expected, and in SummaryGenerator.extract_key_points as a fallback.