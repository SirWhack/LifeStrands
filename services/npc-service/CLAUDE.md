# CLAUDE.md - NPC Service

This file provides guidance to Claude Code when working with the Life Strands NPC Service.

## Service Overview

The NPC Service manages Life Strand data structures, provides semantic search capabilities, and handles CRUD operations for Non-Player Characters. It integrates with pgvector for similarity search and the model service for embedding generation.

**Port:** 8003  
**Purpose:** Life Strand Management, Semantic Search, NPC Data Persistence  
**Dependencies:** PostgreSQL with pgvector, Model Service (for embeddings)

## Architecture

### Core Components

- **LifeStrandSchema** (`src/life_strand_schema.py`): Data validation and schema management
- **NPCRepository** (`src/npc_repository.py`): Database operations and persistence
- **EmbeddingManager** (`src/embedding_manager.py`): Vector search and similarity operations
- **Main Service** (`main.py`): FastAPI application with CRUD endpoints

### Life Strand Data Structure

Life Strands are comprehensive data structures containing:

```python
{
    "id": "unique-identifier",
    "schema_version": "1.0",
    "name": "Character Name",
    "background": {
        "age": 25,
        "occupation": "profession",
        "location": "current location",
        "history": "background story",
        "family": ["family members"],
        "education": "educational background"
    },
    "personality": {
        "traits": ["personality traits"],
        "motivations": ["core motivations"],
        "fears": ["character fears"],
        "values": ["important values"],
        "quirks": ["unique characteristics"]
    },
    "current_status": {
        "mood": "current emotional state",
        "health": "physical condition",
        "energy": "energy level",
        "location": "current location",
        "activity": "current activity"
    },
    "relationships": {
        "person_name": {
            "type": "friend|family|enemy|etc",
            "status": "positive|negative|neutral",
            "intensity": 5,  # 1-10 scale
            "notes": "relationship details"
        }
    },
    "knowledge": [{
        "topic": "subject matter",
        "content": "what they know",
        "source": "how they learned it",
        "confidence": 7  # 1-10 scale
    }],
    "memories": [{
        "content": "memory description",
        "timestamp": "2024-01-01T12:00:00Z",
        "importance": 8,  # 1-10 scale
        "emotional_impact": "positive|negative|neutral",
        "people_involved": ["other characters"],
        "tags": ["memory categories"]
    }]
}
```

## Key Features

### 1. Schema Validation

```python
class LifeStrandValidator:
    def validate_life_strand(self, data: Dict[str, Any]) -> bool:
        """Validate against JSON schema and custom rules"""
```

**Validation Features:**
- JSON Schema compliance
- Custom business rule validation
- Version-aware schema checking
- Field length and type constraints
- Relationship consistency validation

### 2. Data Migration

```python
def migrate_life_strand(self, data: Dict[str, Any], target_version: str) -> Dict[str, Any]:
    """Migrate between schema versions"""
```

**Migration Support:**
- Version-aware data migration
- Backward compatibility
- Schema evolution support
- Data integrity preservation

### 3. Change Merging

```python
def merge_changes(self, original: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Intelligently merge conversation updates"""
```

**Merge Strategies:**
- **Memories**: Append new, sort by timestamp, limit to 50 most recent
- **Knowledge**: Update existing topics, add new ones
- **Relationships**: Update existing, add new relationships
- **Personality**: Merge traits, avoid duplicates
- **Current Status**: Direct replacement

### 4. Semantic Search

```python
class EmbeddingManager:
    async def find_similar_npcs(self, query: str, limit: int = 10) -> List[Dict]:
        """Find NPCs with similar personalities or backgrounds"""
```

**Search Capabilities:**
- Personality similarity search
- Background matching
- Knowledge domain search
- Memory content search
- Relationship pattern matching

## Database Integration

### PostgreSQL with pgvector

```sql
-- NPC table with vector support
CREATE TABLE npcs (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    life_strand JSONB NOT NULL,
    embedding VECTOR(384),  -- Embedding dimension
    faction VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Vector similarity index
CREATE INDEX ON npcs USING ivfflat (embedding vector_cosine_ops);
```

### Embedding Generation

```python
async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
    """Generate embeddings via model service"""
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.model_service_url}/embeddings",
            json={"texts": texts}
        ) as response:
            result = await response.json()
            return result["embeddings"]
```

**Model Service Integration:**
- Uses native Windows model service for embeddings
- Connects via `http://host.docker.internal:8001/embeddings`
- Handles embedding model loading automatically
- Processes batches of text for efficiency

## API Endpoints

### CRUD Operations

```python
# Create NPC
POST /npcs
{
    "name": "Character Name",
    "background": {...},
    "personality": {...}
}

# Get NPC
GET /npcs/{npc_id}

# Update NPC
PUT /npcs/{npc_id}
{
    "current_status": {"mood": "happy"}
}

# Delete NPC
DELETE /npcs/{npc_id}

# List NPCs
GET /npcs?faction=rebels&limit=10
```

### Search Operations

```python
# Semantic search
POST /search/similar
{
    "query": "brave warrior with sword skills",
    "limit": 5
}

# Search by traits
GET /search/traits?traits=brave,loyal&limit=10

# Search by location
GET /search/location/{location_name}

# Search by faction
GET /search/faction/{faction_name}
```

### Context Building

```python
# Get prompt-ready NPC data
GET /npcs/{npc_id}/prompt

# Get relationship context
GET /npcs/{npc_id}/relationships/{other_id}

# Get memory context
GET /npcs/{npc_id}/memories?relevance={topic}
```

### Bulk Operations

```python
# Bulk update
POST /npcs/bulk-update
{
    "npcs": [
        {"id": "npc1", "changes": {...}},
        {"id": "npc2", "changes": {...}}
    ]
}

# Import NPCs
POST /npcs/import
{
    "npcs": [life_strand_data...]
}
```

## Life Strand Schema Management

### Schema Versions

```python
LIFE_STRAND_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "background": {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 0, "maximum": 200},
                "occupation": {"type": "string"},
                "location": {"type": "string"}
            }
        }
        # ... full schema definition
    }
}
```

### Custom Validation Rules

```python
def _validate_custom_rules(self, data: Dict[str, Any]) -> bool:
    """Business logic validation"""
    
    # Age consistency
    # Relationship intensity ranges (1-10)
    # Memory timestamp format
    # Knowledge confidence scores (1-10)
    # Array size limits
```

### Data Sanitization

```python
def sanitize_life_strand(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize data for safe storage"""
    
    # Truncate long text fields
    # Limit array sizes
    # Remove dangerous content
    # Normalize data formats
```

## Integration Points

### With Model Service

```python
# Generate embeddings for similarity search
POST http://host.docker.internal:8001/embeddings
{
    "texts": ["NPC description for embedding"]
}
```

**Native Service Integration:**
- Direct connection to Windows Vulkan model service
- Automatic embedding model loading
- Batch processing for efficiency
- Error handling and fallbacks

### With Chat Service

```python
# Provide NPC data for conversations
GET /npcs/{npc_id}/prompt
# Returns optimized prompt data for LLM

# Validate NPC existence
GET /npcs/{npc_id}
# Quick validation for conversation start
```

### With Summary Service

```python
# Receive Life Strand updates from conversations
PUT /npcs/{npc_id}
{
    "memories": [new_memory],
    "relationships": {updated_relationships},
    "current_status": {mood_change}
}
```

## Memory and Knowledge Management

### Memory Storage

```python
{
    "content": "Detailed memory description",
    "timestamp": "2024-01-01T12:00:00Z",
    "importance": 8,  # 1-10 relevance scale
    "emotional_impact": "positive",
    "people_involved": ["other_character_names"],
    "tags": ["conversation", "revelation", "conflict"]
}
```

**Memory Features:**
- Chronological ordering
- Importance-based filtering
- Emotional impact tracking
- People association
- Tag-based categorization
- Automatic pruning (limit 50 most recent)

### Knowledge Base

```python
{
    "topic": "Sword Fighting",
    "content": "Expert level swordsmanship, trained by master",
    "source": "Formal training at academy",
    "confidence": 9,
    "acquired_date": "2024-01-01T12:00:00Z"
}
```

**Knowledge Features:**
- Topic-based organization
- Confidence scoring
- Source tracking
- Acquisition dating
- Duplicate prevention
- Relevance filtering

## Search and Discovery

### Vector Similarity Search

```python
async def find_similar_npcs(self, query: str, limit: int = 10):
    """Use pgvector for semantic similarity"""
    
    # Generate query embedding
    query_embedding = await self.generate_embeddings([query])
    
    # Vector similarity search
    similar_npcs = await db.fetch("""
        SELECT id, name, life_strand,
               embedding <=> $1 as similarity
        FROM npcs
        WHERE status = 'active'
        ORDER BY embedding <=> $1
        LIMIT $2
    """, query_embedding[0], limit)
```

### Faceted Search

```python
# Multiple search criteria
GET /search?traits=brave&location=castle&faction=knights&age_min=20&age_max=40
```

### Relationship Queries

```python
# Find NPCs with relationships to specific character
GET /npcs/{npc_id}/connections

# Find mutual relationships
GET /relationships/mutual/{npc1_id}/{npc2_id}
```

## Performance Optimization

### Database Indexing

```sql
-- Primary indices
CREATE INDEX idx_npcs_name ON npcs(name);
CREATE INDEX idx_npcs_faction ON npcs(faction);
CREATE INDEX idx_npcs_status ON npcs(status);

-- JSONB indices for Life Strand queries
CREATE INDEX idx_npcs_location ON npcs USING GIN ((life_strand->'background'->>'location'));
CREATE INDEX idx_npcs_traits ON npcs USING GIN ((life_strand->'personality'->'traits'));

-- Vector similarity index
CREATE INDEX idx_npcs_embedding ON npcs USING ivfflat (embedding vector_cosine_ops);
```

### Caching Strategy

- **NPC Data**: Cache frequently accessed NPCs
- **Embeddings**: Cache generated embeddings
- **Search Results**: Cache common search queries
- **Schema Validation**: Cache validation results

### Batch Operations

- **Bulk Updates**: Process multiple NPCs in single transaction
- **Embedding Generation**: Batch text processing
- **Search Operations**: Parallel similarity queries

## Error Handling

### Validation Errors

```python
{
    "error": "validation_failed",
    "details": [
        "Age must be between 0 and 200",
        "Relationship intensity must be 1-10",
        "Required field 'name' missing"
    ]
}
```

### Database Errors

- **Constraint violations**: Handle unique key conflicts
- **Transaction failures**: Rollback and retry logic
- **Connection issues**: Connection pooling and recovery
- **Data integrity**: Validation before persistence

### Service Integration Errors

- **Model service unavailable**: Graceful degradation
- **Embedding generation failures**: Fallback strategies
- **Network timeouts**: Retry mechanisms

## Development Guidelines

### Adding New Schema Fields

1. Update `LIFE_STRAND_SCHEMA_V1`
2. Add validation rules in `_validate_custom_rules`
3. Update migration logic
4. Add database indices if needed
5. Update API documentation

### Extending Search Capabilities

1. Identify search requirements
2. Add database indices for performance
3. Implement search endpoint
4. Add embedding support if needed
5. Test performance with large datasets

### Life Strand Updates

1. Implement merge logic in `merge_changes`
2. Handle data conflicts gracefully
3. Preserve important historical data
4. Validate merged results
5. Update embeddings if structure changes

## Testing

### Unit Tests

```python
# Schema validation
pytest tests/unit/test_life_strand_schema.py

# Data merging
pytest tests/unit/test_data_merging.py

# Repository operations
pytest tests/unit/test_npc_repository.py
```

### Integration Tests

```python
# Database operations
pytest tests/integration/test_database_crud.py

# Search functionality
pytest tests/integration/test_semantic_search.py

# Model service integration
pytest tests/integration/test_embedding_generation.py
```

## Monitoring and Debugging

### Key Metrics

- NPC count by status/faction
- Search query performance
- Embedding generation latency
- Database query times
- Memory usage patterns

### Health Checks

```python
GET /health
{
    "status": "healthy",
    "database": "connected",
    "model_service": "available",
    "embedding_model": "loaded"
}
```

### Debug Endpoints

```python
# Schema validation test
POST /debug/validate
{life_strand_data}

# Search performance
GET /debug/search-stats

# Database metrics
GET /debug/db-stats
```

## Security Considerations

- **Input validation**: Strict schema validation
- **SQL injection**: Parameterized queries only
- **Data sanitization**: Clean all user inputs
- **Access control**: Role-based permissions
- **Data encryption**: Sensitive data protection