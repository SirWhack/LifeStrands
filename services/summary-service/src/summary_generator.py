import asyncio, json, logging, os, re
from typing import List, Dict, Any, Optional
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

class SummaryGenerator:
    """Generate conversation summaries using LLM"""
    
    def __init__(self, model_service_url: str = "http://host.docker.internal:1234/v1", npc_service_url: Optional[str] = None):
        self.model_service_url = model_service_url
        self.npc_service_url = npc_service_url or os.getenv("NPC_SERVICE_URL", "http://npc-service:8003")
        # Optional explicit model override (e.g., gryphe_codex-24b-small-3.2@q5_k_l)
        self.model_id = os.getenv("SUMMARY_MODEL_ID") or os.getenv("MODEL_ID")
        self.total_summaries = 0
        self.summary_prompts = {
            "conversation": """You are an expert conversation analyst. Create a concise summary of the following conversation between a user and an NPC character.

Focus on:
- Key topics discussed
- Important information exchanged
- Emotional tone and mood changes
- Any significant moments or revelations

Conversation:
{transcript}

Provide a clear, objective summary in 2-3 sentences:""",
            
            "key_points": """Analyze the following conversation and extract the most important key points and moments.

Conversation:
{transcript}

List the top 3-5 key points as a JSON array of strings:""",
            
            "memory_entry": """Convert this conversation summary into a memory entry for the NPC character.

Summary: {summary}
NPC Name: {npc_name}
Context: This was a conversation with a user.

Create a natural memory entry that the character would have about this interaction. Write it from the NPC's perspective in first person:"""
        }
        
    async def initialize(self):
        """Initialize the SummaryGenerator"""
        try:
            logger.info("Initializing SummaryGenerator...")
            # Test connection to LM Studio
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.model_service_url}/models",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"LM Studio health check failed: {response.status}")
                    else:
                        data = await response.json()
                        models = data.get('data', [])
                        logger.info(f"Connected to LM Studio with {len(models)} models available")
            logger.info("SummaryGenerator initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SummaryGenerator: {e}")
            raise
        
    async def generate_summary(self, transcript: List[Dict[str, Any]]) -> str:
        """Create concise conversation summary"""
        try:
            if not transcript:
                return ""
                
            # Format transcript for LLM
            formatted_transcript = self._format_transcript(transcript)
            
            if not formatted_transcript.strip():
                return "Brief conversation with no substantial content."
            
            # Generate summary using model service
            prompt = self.summary_prompts["conversation"].format(
                transcript=formatted_transcript
            )
            
            summary = await self._generate_with_model(prompt, max_tokens=200)
            
            # Clean and validate summary
            summary = self._clean_summary(summary)
            
            # Increment counter
            self.total_summaries += 1
            
            logger.info(f"Generated summary for conversation with {len(transcript)} messages")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Conversation summary unavailable due to processing error."
            
    async def extract_key_points(self, transcript: List[Dict[str, Any]]) -> List[str]:
        """Identify important moments in conversation"""
        try:
            if not transcript or len(transcript) < 2:
                return []
                
            formatted_transcript = self._format_transcript(transcript)
            
            prompt = self.summary_prompts["key_points"].format(
                transcript=formatted_transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=300)
            
            # Try to parse as JSON array
            try:
                key_points = json.loads(response.strip())
                if isinstance(key_points, list):
                    # Ensure all items are strings and not too long
                    cleaned_points = []
                    for point in key_points[:5]:  # Max 5 points
                        if isinstance(point, str) and len(point) <= 200:
                            cleaned_points.append(point.strip())
                    return cleaned_points
            except json.JSONDecodeError:
                # Fallback: parse line by line
                lines = response.strip().split('\n')
                key_points = []
                for line in lines[:5]:
                    line = line.strip()
                    if line and not line.startswith('[') and not line.startswith(']'):
                        # Remove numbering, bullets, etc.
                        cleaned_line = re.sub(r'^[\d\-\*\.\)]+\s*', '', line)
                        if len(cleaned_line) <= 200:
                            key_points.append(cleaned_line)
                return key_points
                
            return []
            
        except Exception as e:
            logger.error(f"Error extracting key points: {e}")
            return []
            
    async def generate_memory_entry(self, summary: str, npc_id: str) -> Dict[str, Any]:
        """Format summary as memory for Life Strand"""
        try:
            if not summary or not npc_id:
                return {}
                
            # Get NPC name for context
            npc_name = await self._get_npc_name(npc_id)
            
            # Generate personalized memory entry
            prompt = self.summary_prompts["memory_entry"].format(
                summary=summary,
                npc_name=npc_name
            )
            
            memory_content = await self._generate_with_model(prompt, max_tokens=150)
            memory_content = memory_content.strip()
            
            # Create memory entry structure
            memory_entry = {
                "content": memory_content,
                "timestamp": datetime.utcnow().isoformat(),
                "importance": self._calculate_memory_importance(summary),
                "emotional_impact": self._analyze_emotional_impact(summary),
                "people_involved": ["user"],  # Generic user reference
                "tags": self._extract_tags(summary)
            }
            
            return memory_entry
            
        except Exception as e:
            logger.error(f"Error generating memory entry: {e}")
            return {}
            
    async def prioritize_memories(self, memories: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Keep most important memories within limit"""
        try:
            if len(memories) <= limit:
                return memories
                
            # Sort by importance and recency
            def memory_score(memory):
                importance = memory.get("importance", 5)
                
                # Recency boost (newer memories get slight preference)
                try:
                    timestamp = datetime.fromisoformat(memory.get("timestamp", ""))
                    days_old = (datetime.utcnow() - timestamp).days
                    recency_boost = max(0, 1 - (days_old / 30))  # Decay over 30 days
                except:
                    recency_boost = 0
                    
                return importance + recency_boost
                
            sorted_memories = sorted(memories, key=memory_score, reverse=True)
            
            # Keep top memories
            prioritized = sorted_memories[:limit]
            
            logger.info(f"Prioritized {len(prioritized)} memories from {len(memories)} total")
            return prioritized
            
        except Exception as e:
            logger.error(f"Error prioritizing memories: {e}")
            return memories[:limit]  # Fallback to simple truncation
            
    def _format_transcript(self, transcript: List[Dict[str, Any]]) -> str:
        """Format conversation transcript for LLM processing"""
        try:
            formatted_lines = []
            
            for msg in transcript:
                role = msg.get("role", "unknown")
                content = msg.get("content", "").strip()
                
                if not content:
                    continue
                    
                if role == "user":
                    formatted_lines.append(f"User: {content}")
                elif role == "assistant":
                    formatted_lines.append(f"NPC: {content}")
                    
            return "\n".join(formatted_lines)
            
        except Exception as e:
            logger.error(f"Error formatting transcript: {e}")
            return ""
            
    def _clean_summary(self, summary: str) -> str:
        """Clean and validate generated summary"""
        try:
            # Remove common LLM artifacts
            summary = summary.strip()
            
            # Remove "Summary:" prefix if present
            if summary.lower().startswith("summary:"):
                summary = summary[8:].strip()
                
            # Remove quotes if the entire summary is quoted
            if summary.startswith('"') and summary.endswith('"'):
                summary = summary[1:-1]
                
            # Ensure reasonable length
            if len(summary) > 500:
                # Truncate at sentence boundary
                sentences = summary.split('. ')
                truncated = []
                total_length = 0
                
                for sentence in sentences:
                    if total_length + len(sentence) > 450:
                        break
                    truncated.append(sentence)
                    total_length += len(sentence) + 2
                    
                summary = '. '.join(truncated)
                if not summary.endswith('.'):
                    summary += '.'
                    
            return summary if summary else "Conversation occurred but content was not substantial."
            
        except Exception as e:
            logger.error(f"Error cleaning summary: {e}")
            return summary
            
    def _calculate_memory_importance(self, summary: str) -> int:
        """Calculate importance score (1-10) based on summary content"""
        try:
            importance = 5  # Default
            summary_lower = summary.lower()
            
            # Boost for emotional content
            emotional_indicators = [
                "excited", "worried", "happy", "sad", "angry", "surprised",
                "grateful", "frustrated", "proud", "disappointed", "nervous"
            ]
            
            if any(word in summary_lower for word in emotional_indicators):
                importance += 1
                
            # Boost for personal information
            personal_indicators = [
                "personal", "private", "family", "childhood", "dream", "goal",
                "fear", "hope", "secret", "relationship", "love", "hate"
            ]
            
            if any(word in summary_lower for word in personal_indicators):
                importance += 1
                
            # Boost for conflict or important decisions
            conflict_indicators = [
                "conflict", "argument", "decision", "choice", "problem", 
                "challenge", "crisis", "important", "urgent", "critical"
            ]
            
            if any(word in summary_lower for word in conflict_indicators):
                importance += 1
                
            # Boost for learning or new information
            learning_indicators = [
                "learned", "discovered", "realized", "understood", "explained",
                "taught", "new information", "revelation", "insight"
            ]
            
            if any(word in summary_lower for word in learning_indicators):
                importance += 1
                
            # Length penalty for very short summaries
            if len(summary) < 50:
                importance -= 1
                
            return max(1, min(10, importance))
            
        except Exception as e:
            logger.error(f"Error calculating memory importance: {e}")
            return 5
            
    def _analyze_emotional_impact(self, summary: str) -> str:
        """Analyze emotional impact of conversation"""
        try:
            summary_lower = summary.lower()
            
            positive_indicators = [
                "happy", "excited", "pleased", "satisfied", "grateful", "proud",
                "successful", "achieved", "wonderful", "great", "excellent"
            ]
            
            negative_indicators = [
                "sad", "angry", "frustrated", "worried", "disappointed", "upset",
                "failed", "problem", "difficult", "challenging", "concerning"
            ]
            
            positive_count = sum(1 for word in positive_indicators if word in summary_lower)
            negative_count = sum(1 for word in negative_indicators if word in summary_lower)
            
            if positive_count > negative_count:
                return "positive"
            elif negative_count > positive_count:
                return "negative"
            else:
                return "neutral"
                
        except Exception as e:
            logger.error(f"Error analyzing emotional impact: {e}")
            return "neutral"
            
    def _extract_tags(self, summary: str) -> List[str]:
        """Extract relevant tags from summary"""
        try:
            summary_lower = summary.lower()
            tags = []
            
            # Topic-based tags
            topic_keywords = {
                "work": ["work", "job", "career", "professional", "business"],
                "family": ["family", "parent", "child", "sibling", "relative"],
                "relationship": ["friend", "relationship", "partner", "dating"],
                "health": ["health", "medical", "doctor", "sick", "wellness"],
                "education": ["school", "study", "learn", "education", "knowledge"],
                "hobby": ["hobby", "interest", "passion", "recreation"],
                "travel": ["travel", "trip", "vacation", "journey", "visit"],
                "technology": ["technology", "computer", "software", "digital"],
                "personal_growth": ["growth", "improvement", "development", "change"]
            }
            
            for tag, keywords in topic_keywords.items():
                if any(keyword in summary_lower for keyword in keywords):
                    tags.append(tag)
                    
            return tags[:5]  # Limit to 5 tags
            
        except Exception as e:
            logger.error(f"Error extracting tags: {e}")
            return []
            
    async def _generate_with_model(self, prompt: str, max_tokens: int = 200) -> str:
        """Generate text using LM Studio's OpenAI-compatible API"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    # Use configured model if provided; otherwise rely on LM Studio default
                    "model": self.model_id or "local-model",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful AI assistant that analyzes conversations and generates concise summaries."
                        },
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,  # Lower temperature for more consistent summaries
                    "top_p": 0.9,
                    "stop": ["User:", "NPC:", "\n\n---"],
                    "stream": False
                }
                
                async with session.post(
                    f"{self.model_service_url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        choices = data.get("choices", [])
                        if choices:
                            message = choices[0].get("message", {})
                            return message.get("content", "").strip()
                        return ""
                    else:
                        logger.error(f"LM Studio API error: {response.status}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text}")
                        return ""
                        
        except Exception as e:
            logger.error(f"Error calling LM Studio API: {e}")
            return ""
            
    async def _get_npc_name(self, npc_id: str) -> str:
        """Get NPC name from NPC service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.npc_service_url}/npc/{npc_id}/prompt",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("name", "Character")
                        
        except Exception as e:
            logger.debug(f"Could not get NPC name: {e}")
            
        return "Character"  # Fallback
        
    def get_summary_stats(self, summary: str, key_points: List[str]) -> Dict[str, Any]:
        """Get statistics about generated summary"""
        try:
            return {
                "summary_length": len(summary),
                "summary_words": len(summary.split()),
                "summary_sentences": len([s for s in summary.split('.') if s.strip()]),
                "key_points_count": len(key_points),
                "emotional_impact": self._analyze_emotional_impact(summary),
                "importance_score": self._calculate_memory_importance(summary),
                "tags": self._extract_tags(summary)
            }
        except Exception as e:
            logger.error(f"Error getting summary stats: {e}")
            return {}
            
    def get_total_summaries(self) -> int:
        """Get total number of summaries generated"""
        return self.total_summaries
