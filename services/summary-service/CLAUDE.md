# CLAUDE.md - Summary Service

This file provides guidance to Claude Code when working with the Life Strands Summary Service.

## Service Overview

The Summary Service processes completed conversations to extract insights, generate summaries, and update NPC Life Strands. It uses the model service for analysis and implements change approval workflows for Life Strand modifications.

**Port:** 8004  
**Purpose:** Conversation Analysis, Life Strand Updates, Post-Conversation Processing  
**Dependencies:** Model Service, NPC Service, Redis Queue System

## Architecture

### Core Components

- **SummaryGenerator** (`src/summary_generator.py`): LLM-powered conversation analysis
- **ChangeExtractor** (`src/change_extractor.py`): Identifies Life Strand modifications
- **MemoryUpdater** (`src/memory_updater.py`): Applies approved changes to NPCs
- **QueueConsumer** (`src/queue_consumer.py`): Redis queue processing
- **Main Service** (`main.py`): FastAPI application and queue management

### Processing Pipeline

1. **Queue Processing**: Consume conversation data from Redis
2. **Summary Generation**: Analyze conversation with LLM
3. **Change Extraction**: Identify potential Life Strand updates
4. **Change Approval**: Validate and approve modifications
5. **Memory Update**: Apply changes to NPC data
6. **Notification**: Inform other services of updates

## Key Features

### 1. Conversation Analysis

```python
class SummaryGenerator:
    async def generate_summary(self, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive conversation summary"""
```

**Analysis Components:**
- **Main Summary**: High-level conversation overview
- **Key Events**: Important moments and revelations
- **Relationship Changes**: Shifts in character relationships
- **Personality Insights**: New personality trait discoveries
- **Knowledge Updates**: New information learned
- **Emotional Impact**: Mood and status changes

### 2. Change Detection

```python
class ChangeExtractor:
    def extract_life_strand_changes(self, summary: Dict, npc_data: Dict) -> Dict[str, Any]:
        """Identify specific Life Strand modifications"""
```

**Change Types:**
- **New Memories**: Conversation events worth remembering
- **Relationship Updates**: Changed relationship dynamics
- **Status Changes**: Mood, location, activity updates
- **Knowledge Additions**: New facts or skills learned
- **Personality Evolution**: Trait modifications or additions

### 3. Approval Workflow

```python
class ChangeApprover:
    def validate_changes(self, changes: Dict, confidence_threshold: float = 0.8) -> Dict:
        """Validate and approve Life Strand changes"""
```

**Approval Criteria:**
- **Confidence Score**: LLM confidence in the change
- **Consistency Check**: Alignment with existing data
- **Impact Assessment**: Magnitude of proposed changes
- **Safety Validation**: No harmful or inappropriate content
- **Schema Compliance**: Valid Life Strand structure

### 4. Memory Integration

```python
class MemoryUpdater:
    async def apply_changes(self, npc_id: str, approved_changes: Dict) -> bool:
        """Apply approved changes to NPC Life Strand"""
```

**Update Strategies:**
- **Memory Addition**: Add significant conversation events
- **Relationship Merge**: Update relationship statuses
- **Knowledge Expansion**: Add new knowledge entries
- **Status Refresh**: Update current status fields
- **Personality Integration**: Merge new personality insights

## Redis Queue System

### Queue Structure

```python
# Summary queue entry
{
    "session_id": "conversation-uuid",
    "npc_id": "npc-uuid",
    "user_id": "user-uuid", 
    "messages": [conversation_messages],
    "created_at": "2024-01-01T12:00:00Z",
    "ended_at": "2024-01-01T12:30:00Z",
    "metadata": {
        "duration_minutes": 30,
        "message_count": 45
    }
}
```

### Queue Processing

```python
async def process_summary_queue(self):
    """Continuously process queued conversations"""
    
    while True:
        # Get next conversation from queue
        conversation_data = await redis.brpop("summary_queue", timeout=30)
        
        if conversation_data:
            await self.process_conversation(conversation_data)
```

**Processing Features:**
- **Blocking Queue Pop**: Wait for new conversations
- **Error Handling**: Retry failed processing
- **Dead Letter Queue**: Handle persistent failures
- **Concurrent Processing**: Multiple worker threads
- **Rate Limiting**: Prevent model service overload

## Model Service Integration

### Summary Generation

```python
async def generate_conversation_summary(self, messages: List[Dict]) -> str:
    """Use summary model for conversation analysis"""
    
    prompt = self.build_summary_prompt(messages)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.model_service_url}/generate",
            json={
                "prompt": prompt,
                "model_type": "summary",
                "max_tokens": 1024,
                "stream": False
            }
        ) as response:
            result = await response.json()
            return result["text"]
```

**Native Service Integration:**
- Uses `http://host.docker.internal:8001` for Windows model service
- Automatically switches to summary model
- Non-streaming for complete analysis
- Structured prompt templates for consistent output

### Analysis Prompts

```python
def build_summary_prompt(self, messages: List[Dict], npc_data: Dict) -> str:
    """Build structured analysis prompt"""
    
    return f"""
    Analyze this conversation and identify changes to the character's Life Strand.
    
    CHARACTER: {npc_data['name']}
    CURRENT STATE: {npc_data['current_status']}
    PERSONALITY: {npc_data['personality']['traits']}
    
    CONVERSATION:
    {format_messages(messages)}
    
    Please identify:
    1. New memories worth storing
    2. Relationship changes
    3. Mood/status updates  
    4. New knowledge or skills
    5. Personality insights
    
    Format as JSON with confidence scores.
    """
```

## Change Processing

### Memory Creation

```python
def create_memory_from_event(self, event: Dict, conversation_meta: Dict) -> Dict:
    """Convert conversation event to Life Strand memory"""
    
    return {
        "content": event["description"],
        "timestamp": conversation_meta["ended_at"],
        "importance": min(10, max(1, event["importance"])),
        "emotional_impact": event["emotional_tone"],
        "people_involved": [conversation_meta["user_id"]],
        "tags": ["conversation", event["category"]]
    }
```

### Relationship Updates

```python
def update_relationship(self, current_relationship: Dict, changes: Dict) -> Dict:
    """Merge relationship changes"""
    
    updated = current_relationship.copy()
    
    # Update relationship status
    if "status_change" in changes:
        updated["status"] = changes["status_change"]
        
    # Adjust intensity
    if "intensity_delta" in changes:
        old_intensity = updated.get("intensity", 5)
        new_intensity = max(1, min(10, old_intensity + changes["intensity_delta"]))
        updated["intensity"] = new_intensity
        
    # Add history entry
    if "history" not in updated:
        updated["history"] = []
    updated["history"].append({
        "event": changes["summary"],
        "date": datetime.utcnow().isoformat()
    })
    
    return updated
```

### Knowledge Integration

```python
def add_knowledge_entry(self, topic: str, content: str, confidence: int) -> Dict:
    """Create knowledge entry from conversation"""
    
    return {
        "topic": topic,
        "content": content,
        "source": "conversation",
        "confidence": confidence,
        "acquired_date": datetime.utcnow().isoformat()
    }
```

## Quality Control

### Confidence Scoring

```python
def calculate_change_confidence(self, change: Dict, context: Dict) -> float:
    """Calculate confidence score for proposed change"""
    
    factors = {
        "llm_confidence": change.get("confidence", 0.5),
        "consistency_score": self.check_consistency(change, context),
        "conversation_length": min(1.0, len(context["messages"]) / 10),
        "clarity_score": self.assess_clarity(change)
    }
    
    # Weighted average
    weights = {"llm_confidence": 0.4, "consistency_score": 0.3, 
               "conversation_length": 0.2, "clarity_score": 0.1}
    
    return sum(factors[k] * weights[k] for k in factors)
```

### Change Validation

```python
def validate_proposed_changes(self, changes: Dict, npc_data: Dict) -> Dict:
    """Validate changes before approval"""
    
    validated = {"approved": [], "rejected": [], "requires_review": []}
    
    for change in changes.get("proposed_changes", []):
        confidence = self.calculate_change_confidence(change, npc_data)
        
        if confidence >= self.auto_approval_threshold:
            validated["approved"].append(change)
        elif confidence >= self.manual_review_threshold:
            validated["requires_review"].append(change)
        else:
            validated["rejected"].append(change)
            
    return validated
```

### Safety Checks

```python
def safety_check_changes(self, changes: Dict) -> bool:
    """Ensure changes are safe and appropriate"""
    
    # Content filtering
    dangerous_patterns = ["violence", "explicit", "harmful"]
    
    for change in changes.get("approved", []):
        content = str(change).lower()
        if any(pattern in content for pattern in dangerous_patterns):
            return False
            
    # Magnitude check
    if self.assess_change_magnitude(changes) > self.max_change_threshold:
        return False
        
    return True
```

## API Endpoints

### Manual Summary Operations

```python
# Generate summary for specific conversation
POST /summaries/generate
{
    "session_id": "conversation-uuid",
    "force_reprocess": false
}

# Get summary status
GET /summaries/{session_id}

# Approve pending changes
POST /summaries/{session_id}/approve
{
    "change_ids": ["change1", "change2"]
}

# Reject changes
POST /summaries/{session_id}/reject
{
    "change_ids": ["change3"],
    "reason": "Inconsistent with character"
}
```

### Analysis Operations

```python
# Analyze conversation without processing
POST /analysis/preview
{
    "messages": [conversation_messages],
    "npc_id": "npc-uuid"
}

# Get processing statistics
GET /analysis/stats

# Review pending changes
GET /analysis/pending-changes?limit=10
```

### Queue Management

```python
# Check queue status
GET /queue/status

# Requeue failed processing
POST /queue/retry/{session_id}

# Clear queue
DELETE /queue/clear
```

## Configuration

### Environment Variables

- `MODEL_SERVICE_URL`: Native Windows model service URL
- `NPC_SERVICE_URL`: NPC service for Life Strand updates
- `REDIS_URL`: Redis connection for queue processing
- `SUMMARY_AUTO_APPROVAL_THRESHOLD`: Auto-approval confidence (0.8)
- `SUMMARY_WORKER_CONCURRENCY`: Number of worker threads (3)

### Processing Thresholds

```python
# Confidence thresholds
AUTO_APPROVAL_THRESHOLD = 0.8    # Auto-approve high confidence
MANUAL_REVIEW_THRESHOLD = 0.6    # Flag for manual review
REJECTION_THRESHOLD = 0.4        # Auto-reject low confidence

# Change magnitude limits
MAX_PERSONALITY_CHANGES = 3      # Max trait changes per conversation
MAX_MEMORIES_PER_SESSION = 5     # Max memories to store
MAX_RELATIONSHIP_DELTA = 2       # Max relationship intensity change
```

## Error Handling

### Processing Failures

```python
async def handle_processing_error(self, conversation_data: Dict, error: Exception):
    """Handle failed conversation processing"""
    
    # Log error details
    logger.error(f"Summary processing failed: {error}")
    
    # Increment retry count
    retry_count = conversation_data.get("retry_count", 0) + 1
    
    if retry_count < self.max_retries:
        # Requeue for retry
        conversation_data["retry_count"] = retry_count
        await self.requeue_conversation(conversation_data)
    else:
        # Move to dead letter queue
        await self.dead_letter_queue(conversation_data, str(error))
```

### Model Service Errors

```python
async def handle_model_service_error(self, error: Exception) -> str:
    """Handle model service failures"""
    
    if "timeout" in str(error).lower():
        # Retry with shorter prompt
        return await self.retry_with_truncation()
    elif "service unavailable" in str(error).lower():
        # Queue for later processing
        await self.delay_processing(300)  # 5 minute delay
    else:
        # Fallback to basic analysis
        return self.generate_basic_summary()
```

## Performance Optimization

### Batch Processing

```python
async def process_batch(self, conversations: List[Dict]) -> List[Dict]:
    """Process multiple conversations in batch"""
    
    # Group by NPC for context sharing
    npc_groups = self.group_by_npc(conversations)
    
    results = []
    for npc_id, conv_group in npc_groups.items():
        # Load NPC data once
        npc_data = await self.get_npc_data(npc_id)
        
        # Process group with shared context
        for conversation in conv_group:
            result = await self.process_with_context(conversation, npc_data)
            results.append(result)
            
    return results
```

### Caching Strategy

- **NPC Data**: Cache frequently updated NPCs
- **Model Responses**: Cache similar conversation patterns
- **Validation Results**: Cache change validation outcomes
- **Template Prompts**: Cache formatted prompt templates

### Queue Optimization

- **Priority Queues**: Process important NPCs first
- **Batch Consumption**: Group similar conversations
- **Load Balancing**: Distribute work across workers
- **Back-pressure**: Throttle when model service busy

## Monitoring and Debugging

### Key Metrics

- Queue processing rate
- Summary generation latency
- Change approval ratio
- Model service response times
- Memory update success rate

### Health Monitoring

```python
GET /health
{
    "status": "healthy",
    "queue_size": 15,
    "processing_rate": "2.3/min",
    "model_service": "available",
    "pending_approvals": 8
}
```

### Debug Information

```python
# Processing statistics
GET /debug/stats

# Recent errors
GET /debug/errors

# Queue metrics
GET /debug/queue-metrics

# Model service integration
GET /debug/model-service-health
```

## Integration Testing

### Queue Processing Test

```python
# Add test conversation to queue
POST /debug/queue-test
{
    "session_id": "test-session",
    "npc_id": "test-npc",
    "messages": [test_messages]
}
```

### Summary Generation Test

```python
# Test summary without queueing
POST /debug/summary-test
{
    "messages": [conversation_messages],
    "npc_id": "test-npc"
}
```

### Change Extraction Test

```python
# Test change detection
POST /debug/change-extraction-test
{
    "summary": "conversation summary",
    "npc_data": {current_life_strand}
}
```

## Security and Safety

### Content Safety

- **Content filtering**: Remove inappropriate content
- **Change validation**: Verify reasonable modifications
- **Approval workflows**: Human oversight for major changes
- **Audit logging**: Track all Life Strand modifications

### Data Privacy

- **Conversation encryption**: Secure message storage
- **User anonymization**: Remove identifying information
- **Retention policies**: Automatic data cleanup
- **Access controls**: Role-based permissions

### System Safety

- **Resource limits**: Prevent processing overload
- **Error isolation**: Contain processing failures
- **Rollback capability**: Undo problematic changes
- **Monitoring alerts**: Notify of system issues