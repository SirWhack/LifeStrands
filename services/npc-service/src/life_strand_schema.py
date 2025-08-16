import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import jsonschema
from copy import deepcopy
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Life Strand JSON Schema
LIFE_STRAND_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "schema_version": {"type": "string", "default": "1.0"},
        "name": {"type": "string", "minLength": 1},
        "background": {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 0, "maximum": 200},
                "occupation": {"type": "string"},
                "location": {"type": "string"},
                "history": {"type": "string"},
                "family": {"type": "array", "items": {"type": "string"}},
                "education": {"type": "string"}
            },
            "required": ["age", "location"]
        },
        "personality": {
            "type": "object",
            "properties": {
                "traits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 10
                },
                "motivations": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "maxItems": 5
                },
                "fears": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5
                },
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5
                },
                "quirks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3
                }
            },
            "required": ["traits"]
        },
        "current_status": {
            "type": "object",
            "properties": {
                "mood": {"type": "string"},
                "health": {"type": "string"},
                "energy": {"type": "string"},
                "location": {"type": "string"},
                "activity": {"type": "string"},
                "relationships_affected": {"type": "array", "items": {"type": "string"}}
            }
        },
        "relationships": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["family", "friend", "enemy", "acquaintance", "romantic", "colleague", "mentor", "student"]},
                    "status": {"type": "string", "enum": ["positive", "negative", "neutral", "complicated"]},
                    "intensity": {"type": "integer", "minimum": 1, "maximum": 10},
                    "notes": {"type": "string"},
                    "history": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["type", "status"]
            }
        },
        "knowledge": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                    "source": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 1, "maximum": 10},
                    "acquired_date": {"type": "string", "format": "date-time"}
                },
                "required": ["topic", "content"]
            }
        },
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 10},
                    "emotional_impact": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "people_involved": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["content", "timestamp"]
            }
        },
        "faction": {"type": "string"},
        "status": {"type": "string", "enum": ["active", "inactive", "archived"], "default": "active"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"}
    },
    "required": ["name", "background", "personality"]
}

class LifeStrandValidator:
    """Validate and migrate Life Strand data structures"""
    
    def __init__(self):
        self.schemas = {
            "1.0": LIFE_STRAND_SCHEMA_V1
        }
        self.current_version = "1.0"
        
    def validate_life_strand(self, data: Dict[str, Any]) -> bool:
        """Validate against current schema version"""
        try:
            # Determine schema version
            schema_version = data.get("schema_version", self.current_version)
            
            if schema_version not in self.schemas:
                logger.error(f"Unknown schema version: {schema_version}")
                return False
                
            schema = self.schemas[schema_version]
            
            # Validate against schema
            jsonschema.validate(data, schema)
            
            # Additional custom validations
            if not self._validate_custom_rules(data):
                return False
                
            logger.debug(f"Life strand validation passed for version {schema_version}")
            return True
            
        except jsonschema.ValidationError as e:
            logger.error(f"Life strand schema validation failed: {e.message}")
            return False
        except Exception as e:
            logger.error(f"Life strand validation error: {e}")
            return False
            
    def migrate_life_strand(self, data: Dict[str, Any], target_version: str) -> Dict[str, Any]:
        """Migrate old Life Strand to new schema"""
        try:
            current_version = data.get("schema_version", "1.0")
            
            if current_version == target_version:
                return data
                
            # For now, we only have version 1.0
            # Future versions would have migration logic here
            
            migrated_data = deepcopy(data)
            migrated_data["schema_version"] = target_version
            
            logger.info(f"Migrated life strand from {current_version} to {target_version}")
            return migrated_data
            
        except Exception as e:
            logger.error(f"Error migrating life strand: {e}")
            return data
            
    def extract_queryable_fields(self, life_strand: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields for database columns"""
        try:
            fields = {}
            
            # Basic fields
            fields["name"] = life_strand.get("name")
            fields["faction"] = life_strand.get("faction")
            fields["status"] = life_strand.get("status", "active")
            
            # Background fields
            background = life_strand.get("background", {})
            fields["background_occupation"] = background.get("occupation")
            fields["background_age"] = background.get("age")
            fields["location"] = background.get("location")
            
            # Current status location (overrides background location if present)
            current_status = life_strand.get("current_status", {})
            if current_status.get("location"):
                fields["location"] = current_status["location"]
                
            # Personality traits for searching
            personality = life_strand.get("personality", {})
            fields["personality_traits"] = personality.get("traits", [])
            
            return fields
            
        except Exception as e:
            logger.error(f"Error extracting queryable fields: {e}")
            return {}
            
    def merge_changes(self, original: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
        """Intelligently merge conversation changes"""
        try:
            merged = deepcopy(original)
            
            # Update timestamp
            merged["updated_at"] = datetime.utcnow().isoformat()
            
            # Merge top-level fields
            for key, value in changes.items():
                if key in ["id", "schema_version", "created_at"]:
                    continue  # Skip immutable fields
                    
                if key == "memories":
                    # Append new memories
                    if "memories" not in merged:
                        merged["memories"] = []
                    if isinstance(value, list):
                        merged["memories"].extend(value)
                    else:
                        merged["memories"].append(value)
                        
                    # Sort by timestamp and limit to most recent 50
                    merged["memories"] = sorted(
                        merged["memories"],
                        key=lambda m: m.get("timestamp", ""),
                        reverse=True
                    )[:50]
                    
                elif key == "knowledge":
                    # Merge knowledge, avoiding duplicates by topic
                    if "knowledge" not in merged:
                        merged["knowledge"] = []
                        
                    existing_topics = {k.get("topic") for k in merged["knowledge"]}
                    
                    new_knowledge = value if isinstance(value, list) else [value]
                    for knowledge_item in new_knowledge:
                        topic = knowledge_item.get("topic")
                        if topic not in existing_topics:
                            merged["knowledge"].append(knowledge_item)
                            existing_topics.add(topic)
                        else:
                            # Update existing knowledge
                            for i, existing in enumerate(merged["knowledge"]):
                                if existing.get("topic") == topic:
                                    merged["knowledge"][i] = knowledge_item
                                    break
                                    
                elif key == "relationships":
                    # Merge relationship updates
                    if "relationships" not in merged:
                        merged["relationships"] = {}
                        
                    for person, relationship_data in value.items():
                        if person in merged["relationships"]:
                            # Update existing relationship
                            merged["relationships"][person].update(relationship_data)
                        else:
                            # Add new relationship
                            merged["relationships"][person] = relationship_data
                            
                elif key == "personality":
                    # Merge personality updates
                    if "personality" not in merged:
                        merged["personality"] = {}
                        
                    for trait_type, trait_values in value.items():
                        if trait_type in merged["personality"]:
                            if isinstance(trait_values, list):
                                # Merge lists, removing duplicates
                                existing = set(merged["personality"][trait_type])
                                existing.update(trait_values)
                                merged["personality"][trait_type] = list(existing)
                            else:
                                merged["personality"][trait_type] = trait_values
                        else:
                            merged["personality"][trait_type] = trait_values
                            
                elif key == "current_status":
                    # Update current status
                    if "current_status" not in merged:
                        merged["current_status"] = {}
                    merged["current_status"].update(value)
                    
                else:
                    # Direct replacement for other fields
                    merged[key] = value
                    
            return merged
            
        except Exception as e:
            logger.error(f"Error merging changes: {e}")
            return original
            
    def _validate_custom_rules(self, data: Dict[str, Any]) -> bool:
        """Apply custom validation rules beyond schema"""
        try:
            # Validate age consistency
            background = data.get("background", {})
            age = background.get("age")
            if age and age < 0:
                logger.error("Age cannot be negative")
                return False
                
            # Validate relationship consistency
            relationships = data.get("relationships", {})
            for person, relationship in relationships.items():
                intensity = relationship.get("intensity", 5)
                if not (1 <= intensity <= 10):
                    logger.error(f"Relationship intensity for {person} must be 1-10")
                    return False
                    
            # Validate memory timestamps
            memories = data.get("memories", [])
            for memory in memories:
                timestamp = memory.get("timestamp")
                if timestamp:
                    try:
                        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except ValueError:
                        logger.error(f"Invalid memory timestamp: {timestamp}")
                        return False
                        
            # Validate knowledge confidence scores
            knowledge = data.get("knowledge", [])
            for item in knowledge:
                confidence = item.get("confidence", 5)
                if confidence and not (1 <= confidence <= 10):
                    logger.error("Knowledge confidence must be 1-10")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Custom validation error: {e}")
            return False
            
    def get_schema_version(self, data: Dict[str, Any]) -> str:
        """Get schema version from life strand data"""
        return data.get("schema_version", "1.0")
        
    def get_available_versions(self) -> List[str]:
        """Get list of available schema versions"""
        return list(self.schemas.keys())
        
    def create_empty_life_strand(self, name: str, **kwargs) -> Dict[str, Any]:
        """Create a minimal valid life strand"""
        life_strand = {
            "schema_version": self.current_version,
            "name": name,
            "background": {
                "age": kwargs.get("age", 25),
                "location": kwargs.get("location", "Unknown"),
                "occupation": kwargs.get("occupation", "Unknown")
            },
            "personality": {
                "traits": kwargs.get("traits", ["friendly", "curious"])
            },
            "current_status": {},
            "relationships": {},
            "knowledge": [],
            "memories": [],
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Add any additional fields from kwargs
        for key, value in kwargs.items():
            if key not in ["age", "location", "occupation", "traits"]:
                life_strand[key] = value
                
        return life_strand
        
    def sanitize_life_strand(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize life strand data for safe storage"""
        try:
            sanitized = deepcopy(data)
            
            # Truncate long text fields
            max_lengths = {
                "name": 100,
                "background.history": 2000,
                "background.education": 500,
                "current_status.activity": 200
            }
            
            for field_path, max_length in max_lengths.items():
                keys = field_path.split(".")
                obj = sanitized
                
                for key in keys[:-1]:
                    if key in obj and isinstance(obj[key], dict):
                        obj = obj[key]
                    else:
                        break
                else:
                    final_key = keys[-1]
                    if final_key in obj and isinstance(obj[final_key], str):
                        if len(obj[final_key]) > max_length:
                            obj[final_key] = obj[final_key][:max_length].rsplit(" ", 1)[0] + "..."
                            
            # Limit array sizes
            max_array_sizes = {
                "personality.traits": 10,
                "personality.motivations": 5,
                "personality.fears": 5,
                "knowledge": 100,
                "memories": 50
            }
            
            for field_path, max_size in max_array_sizes.items():
                keys = field_path.split(".")
                obj = sanitized
                
                for key in keys[:-1]:
                    if key in obj and isinstance(obj[key], dict):
                        obj = obj[key]
                    else:
                        break
                else:
                    final_key = keys[-1]
                    if final_key in obj and isinstance(obj[final_key], list):
                        obj[final_key] = obj[final_key][:max_size]
                        
            return sanitized
            
        except Exception as e:
            logger.error(f"Error sanitizing life strand: {e}")
            return data
            
    def get_validation_errors(self, data: Dict[str, Any]) -> List[str]:
        """Get detailed validation errors"""
        errors = []
        
        try:
            schema_version = data.get("schema_version", self.current_version)
            schema = self.schemas.get(schema_version)
            
            if not schema:
                errors.append(f"Unknown schema version: {schema_version}")
                return errors
                
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as e:
                errors.append(f"Schema validation: {e.message}")
                
            # Custom validation errors
            if not self._validate_custom_rules(data):
                errors.append("Custom validation rules failed")
                
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            
        return errors

# Pydantic models for API use
class LifeStrand(BaseModel):
    """Pydantic model for Life Strand data"""
    id: Optional[str] = None
    schema_version: str = "1.0"
    name: str = Field(..., min_length=1, max_length=100)
    background: Dict[str, Any] = Field(default_factory=dict)
    personality: Dict[str, Any] = Field(default_factory=dict) 
    current_status: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    knowledge: List[Dict[str, Any]] = Field(default_factory=list)
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        extra = "allow"
        
class NPCUpdate(BaseModel):
    """Pydantic model for NPC updates"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    background: Optional[Dict[str, Any]] = None
    personality: Optional[Dict[str, Any]] = None
    current_status: Optional[Dict[str, Any]] = None
    relationships: Optional[Dict[str, Any]] = None
    knowledge: Optional[List[Dict[str, Any]]] = None
    memories: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None
    
    class Config:
        extra = "allow"