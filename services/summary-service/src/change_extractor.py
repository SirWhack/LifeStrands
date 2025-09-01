import asyncio, json, logging, os, re
from typing import List, Dict, Any, Optional
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

class ChangeExtractor:
    """Extract potential Life Strand changes from conversations"""
    
    def __init__(self, model_service_url: str = "http://host.docker.internal:1234/v1", npc_service_url: Optional[str] = None):
        self.model_service_url = model_service_url
        self.npc_service_url = npc_service_url or os.getenv("NPC_SERVICE_URL", "http://npc-service:8003")
        self.confidence_threshold = 0.4  # More permissive for fictional NPCs
        # Optional explicit model override
        self.model_id = os.getenv("ANALYSIS_MODEL_ID") or os.getenv("SUMMARY_MODEL_ID") or os.getenv("MODEL_ID")
    
    async def initialize(self):
        """Initialize the ChangeExtractor"""
        try:
            logger.info("Initializing ChangeExtractor...")
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
                        logger.info(f"ChangeExtractor connected to LM Studio with {len(models)} models available")
            logger.info("ChangeExtractor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ChangeExtractor: {e}")
            raise
        
        self.analysis_prompts = {
            "personality_changes": """Analyze this conversation to identify changes to the NPC's personality traits, motivations, or fears. Look for ANY new aspects revealed, even subtle ones, as NPCs should be dynamic and evolving.

Current NPC Profile:
Name: {npc_name}
Traits: {traits}
Motivations: {motivations}  
Fears: {fears}

Conversation:
{transcript}

What new personality aspects were revealed or changed? Be generous in identifying personality development - characters should evolve through interactions.
Respond with JSON format:
{{"changes": [{{"type": "trait_added|motivation_added|fear_added|trait_modified", "item": "specific trait/motivation/fear", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}]}}""",

            "relationship_changes": """Analyze this conversation for relationship changes or new relationships formed. NPCs should form dynamic relationships easily and relationships should evolve naturally.

Current Relationships: {relationships}
NPC Name: {npc_name}

Conversation:
{transcript}

What relationship changes occurred? Include new people mentioned, changes in existing relationships, and emotional shifts. Be generous in identifying relationship development.
Respond with JSON format:
{{"changes": [{{"person": "person name", "relationship_type": "friend|family|colleague|enemy|acquaintance|romantic|rival|mentor|student|ally", "status": "positive|negative|neutral|complicated|obsessed|devoted|hostile", "intensity": -10-10, "reasoning": "explanation"}}]}}""",

            "knowledge_learned": """Extract any new information, facts, or knowledge the NPC learned during this conversation.

NPC Name: {npc_name}
Current Knowledge Topics: {knowledge_topics}

Conversation:
{transcript}

What new information did the NPC learn? Focus on facts, skills, or insights gained.
Respond with JSON format:
{{"knowledge": [{{"topic": "topic name", "content": "what was learned", "confidence": 1-10, "source": "user|conversation"}}]}}""",

            "status_updates": """Analyze if the NPC's current status (mood, health, energy, location, activity) should be updated based on this conversation.

Current Status:
Mood: {mood}
Health: {health}
Energy: {energy}
Location: {location}
Activity: {activity}

Conversation:
{transcript}

Should any status be updated? Only suggest changes if clearly indicated.
Respond with JSON format:
{{"status_changes": [{{"field": "mood|health|energy|location|activity", "new_value": "new value", "confidence": 0.0-1.0, "reasoning": "explanation"}}]}}""",

            "emotional_impact": """Analyze the overall emotional impact this conversation had on the NPC character.

NPC Name: {npc_name}
Conversation:
{transcript}

How did this conversation affect the character emotionally?
Respond with JSON format:
{{"emotional_impact": {{"primary_emotion": "emotion", "intensity": 1-10, "lasting_effect": "brief description", "confidence": 0.0-1.0}}}}"""
        }
        
    async def analyze_conversation(self, transcript: List[Dict[str, Any]], life_strand: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify potential personality/relationship changes"""
        try:
            all_changes = []
            
            if not transcript or not life_strand:
                return all_changes
                
            npc_name = life_strand.get("name", "Character")
            formatted_transcript = self._format_transcript(transcript)
            
            # Analyze different types of changes in parallel
            change_tasks = [
                self._analyze_personality_changes(formatted_transcript, life_strand),
                self._analyze_relationship_changes(formatted_transcript, life_strand),
                self._analyze_status_changes(formatted_transcript, life_strand),
                self._analyze_emotional_impact(formatted_transcript, npc_name)
            ]
            
            change_results = await asyncio.gather(*change_tasks, return_exceptions=True)
            
            # Combine all changes
            for result in change_results:
                if isinstance(result, list):
                    all_changes.extend(result)
                elif isinstance(result, dict):
                    all_changes.append(result)
                    
            # Filter by confidence threshold (lowered for more dynamic NPCs)
            filtered_changes = [
                change for change in all_changes 
                if change.get("confidence_score", 0) >= 0.4  # Very permissive threshold
            ]
            
            logger.info(f"Extracted {len(filtered_changes)} high-confidence changes from conversation")
            return filtered_changes
            
        except Exception as e:
            logger.error(f"Error analyzing conversation: {e}")
            return []
            
    async def extract_learned_information(self, transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract new knowledge/facts learned"""
        try:
            if not transcript:
                return []
                
            formatted_transcript = self._format_transcript(transcript)
            
            # Use simpler prompt for knowledge extraction
            prompt = f"""Extract factual information and knowledge shared in this conversation:

{formatted_transcript}

List new facts, information, or knowledge as JSON:
{{"knowledge": [{{"topic": "topic", "content": "fact/information", "confidence": 1-10}}]}}"""
            
            response = await self._generate_with_model(prompt, max_tokens=400)
            
            try:
                data = json.loads(response)
                knowledge_items = data.get("knowledge", [])
                
                # Validate and clean knowledge items
                cleaned_items = []
                for item in knowledge_items[:10]:  # Limit to 10 items
                    if (isinstance(item, dict) and 
                        "topic" in item and 
                        "content" in item and
                        len(item["content"]) > 10):
                        
                        cleaned_item = {
                            "topic": str(item["topic"])[:100],
                            "content": str(item["content"])[:500],
                            "confidence": min(10, max(1, int(item.get("confidence", 5)))),
                            "source": "conversation",
                            "acquired_date": datetime.utcnow().isoformat()
                        }
                        cleaned_items.append(cleaned_item)
                        
                return cleaned_items
                
            except json.JSONDecodeError:
                logger.warning("Could not parse knowledge extraction response as JSON")
                return []
                
        except Exception as e:
            logger.error(f"Error extracting learned information: {e}")
            return []
            
    async def detect_relationship_changes(self, transcript: List[Dict[str, Any]], npc_id: str) -> List[Dict[str, Any]]:
        """Identify relationship status changes"""
        try:
            if not transcript:
                return []
                
            # Get current NPC data
            life_strand = await self._get_npc_data(npc_id)
            if not life_strand:
                return []
                
            formatted_transcript = self._format_transcript(transcript)
            current_relationships = life_strand.get("relationships", {})
            
            prompt = self.analysis_prompts["relationship_changes"].format(
                relationships=json.dumps(current_relationships, indent=2),
                npc_name=life_strand.get("name", "Character"),
                transcript=formatted_transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=300)
            
            try:
                data = json.loads(response)
                changes = data.get("changes", [])
                
                relationship_changes = []
                for change in changes:  # No limits - allow all relationship changes
                    if isinstance(change, dict) and "person" in change:
                        relationship_change = {
                            "change_type": "relationship_updated",
                            "change_summary": f"Relationship with {change['person']} updated",
                            "change_data": {
                                "person": change["person"],
                                "type": change.get("relationship_type", "acquaintance"),
                                "status": change.get("status", "neutral"),
                                "intensity": int(change.get("intensity", 5)),  # Allow any intensity value
                                "notes": change.get("reasoning", "")
                            },
                            "confidence_score": 0.8  # Default confidence
                        }
                        relationship_changes.append(relationship_change)
                        
                return relationship_changes
                
            except json.JSONDecodeError:
                logger.warning("Could not parse relationship changes response as JSON")
                return []
                
        except Exception as e:
            logger.error(f"Error detecting relationship changes: {e}")
            return []
            
    async def calculate_emotional_impact(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess emotional impact of conversation"""
        try:
            if not transcript:
                return {"emotional_impact": "neutral", "intensity": 5, "confidence": 0.5}
                
            formatted_transcript = self._format_transcript(transcript)
            
            prompt = f"""Analyze the emotional impact of this conversation:

{formatted_transcript}

Rate the overall emotional impact:
{{"emotional_impact": "very_positive|positive|neutral|negative|very_negative", "intensity": 1-10, "primary_emotions": ["emotion1", "emotion2"], "confidence": 0.0-1.0}}"""
            
            response = await self._generate_with_model(prompt, max_tokens=200)
            
            try:
                data = json.loads(response)
                return {
                    "emotional_impact": data.get("emotional_impact", "neutral"),
                    "intensity": min(10, max(1, int(data.get("intensity", 5)))),
                    "primary_emotions": data.get("primary_emotions", []),
                    "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5))))
                }
            except (json.JSONDecodeError, ValueError):
                # Fallback analysis
                return self._simple_emotional_analysis(formatted_transcript)
                
        except Exception as e:
            logger.error(f"Error calculating emotional impact: {e}")
            return {"emotional_impact": "neutral", "intensity": 5, "confidence": 0.3}
            
    async def _analyze_personality_changes(self, transcript: str, life_strand: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze potential personality changes"""
        try:
            personality = life_strand.get("personality", {})
            
            prompt = self.analysis_prompts["personality_changes"].format(
                npc_name=life_strand.get("name", "Character"),
                traits=json.dumps(personality.get("traits", [])),
                motivations=json.dumps(personality.get("motivations", [])),
                fears=json.dumps(personality.get("fears", [])),
                transcript=transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=400)
            
            try:
                data = json.loads(response)
                changes = data.get("changes", [])
                
                personality_changes = []
                for change in changes:  # No limits - allow all personality changes
                    if (isinstance(change, dict) and 
                        "type" in change and 
                        "item" in change):
                        
                        personality_change = {
                            "change_type": "personality_changed",
                            "change_summary": f"Personality change: {change['item']}",
                            "change_data": {
                                "change_type": change["type"],
                                "item": change["item"],
                                "reasoning": change.get("reasoning", "")
                            },
                            "confidence_score": float(change.get("confidence", 0.5))
                        }
                        personality_changes.append(personality_change)
                        
                return personality_changes
                
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            logger.error(f"Error analyzing personality changes: {e}")
            return []
            
    async def _analyze_relationship_changes(self, transcript: str, life_strand: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze relationship changes"""
        try:
            relationships = life_strand.get("relationships", {})
            
            prompt = self.analysis_prompts["relationship_changes"].format(
                relationships=json.dumps(relationships, indent=2),
                npc_name=life_strand.get("name", "Character"),
                transcript=transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=300)
            
            try:
                data = json.loads(response)
                return await self._process_relationship_changes(data.get("changes", []))
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            logger.error(f"Error analyzing relationship changes: {e}")
            return []
            
    async def _analyze_status_changes(self, transcript: str, life_strand: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze current status changes"""
        try:
            current_status = life_strand.get("current_status", {})
            
            prompt = self.analysis_prompts["status_updates"].format(
                mood=current_status.get("mood", "neutral"),
                health=current_status.get("health", "good"),
                energy=current_status.get("energy", "normal"),
                location=current_status.get("location", "unknown"),
                activity=current_status.get("activity", "none"),
                transcript=transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=250)
            
            try:
                data = json.loads(response)
                changes = data.get("status_changes", [])
                
                status_changes = []
                for change in changes:  # No limits - allow all status changes
                    if (isinstance(change, dict) and 
                        "field" in change and 
                        "new_value" in change):
                        
                        status_change = {
                            "change_type": "status_updated",
                            "change_summary": f"Status update: {change['field']} -> {change['new_value']}",
                            "change_data": {
                                "field": change["field"],
                                "old_value": current_status.get(change["field"], "unknown"),
                                "new_value": change["new_value"],
                                "reasoning": change.get("reasoning", "")
                            },
                            "confidence_score": float(change.get("confidence", 0.6))
                        }
                        status_changes.append(status_change)
                        
                return status_changes
                
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            logger.error(f"Error analyzing status changes: {e}")
            return []
            
    async def _analyze_emotional_impact(self, transcript: str, npc_name: str) -> Dict[str, Any]:
        """Analyze emotional impact"""
        try:
            prompt = self.analysis_prompts["emotional_impact"].format(
                npc_name=npc_name,
                transcript=transcript
            )
            
            response = await self._generate_with_model(prompt, max_tokens=200)
            
            try:
                data = json.loads(response)
                emotional_data = data.get("emotional_impact", {})
                
                return {
                    "change_type": "emotional_impact",
                    "change_summary": f"Emotional impact: {emotional_data.get('primary_emotion', 'neutral')}",
                    "change_data": emotional_data,
                    "confidence_score": float(emotional_data.get("confidence", 0.5))
                }
                
            except json.JSONDecodeError:
                return {}
                
        except Exception as e:
            logger.error(f"Error analyzing emotional impact: {e}")
            return {}
            
    async def _process_relationship_changes(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process and validate relationship changes"""
        relationship_changes = []
        
        for change in changes:  # No limits - allow all relationship changes
            if not isinstance(change, dict) or "person" not in change:
                continue
                
            relationship_change = {
                "change_type": "relationship_updated",
                "change_summary": f"Relationship with {change['person']} updated",
                "change_data": {
                    "person": str(change["person"]),
                    "type": change.get("relationship_type", "acquaintance"),
                    "status": change.get("status", "neutral"),
                    "intensity": min(10, max(1, int(change.get("intensity", 5)))),
                    "notes": change.get("reasoning", "")
                },
                "confidence_score": 0.7  # Default confidence for relationship changes
            }
            relationship_changes.append(relationship_change)
            
        return relationship_changes
        
    def _format_transcript(self, transcript: List[Dict[str, Any]]) -> str:
        """Format transcript for analysis"""
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
            
    def _simple_emotional_analysis(self, transcript: str) -> Dict[str, Any]:
        """Fallback emotional analysis using simple keyword matching"""
        try:
            transcript_lower = transcript.lower()
            
            positive_words = ["happy", "excited", "pleased", "grateful", "wonderful", "great"]
            negative_words = ["sad", "angry", "frustrated", "disappointed", "worried", "upset"]
            
            positive_count = sum(1 for word in positive_words if word in transcript_lower)
            negative_count = sum(1 for word in negative_words if word in transcript_lower)
            
            if positive_count > negative_count:
                return {
                    "emotional_impact": "positive",
                    "intensity": min(8, positive_count + 5),
                    "primary_emotions": ["positive"],
                    "confidence": 0.6
                }
            elif negative_count > positive_count:
                return {
                    "emotional_impact": "negative", 
                    "intensity": min(8, negative_count + 5),
                    "primary_emotions": ["negative"],
                    "confidence": 0.6
                }
            else:
                return {
                    "emotional_impact": "neutral",
                    "intensity": 5,
                    "primary_emotions": ["neutral"],
                    "confidence": 0.4
                }
                
        except Exception as e:
            logger.error(f"Error in simple emotional analysis: {e}")
            return {"emotional_impact": "neutral", "intensity": 5, "confidence": 0.3}
            
    async def _generate_with_model(self, prompt: str, max_tokens: int = 200) -> str:
        """Generate response using LM Studio's OpenAI-compatible API"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_id or "local-model",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful AI assistant that analyzes conversations and extracts changes in a structured format."
                        },
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,  # Low temperature for consistent analysis
                    "top_p": 0.9,
                    "stop": ["User:", "NPC:", "\n\n"],
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
            
    async def _get_npc_data(self, npc_id: str) -> Dict[str, Any]:
        """Get NPC data from NPC service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.npc_service_url}/npcs/{npc_id}",
                                       timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        return await response.json()
                        
        except Exception as e:
            logger.debug(f"Could not get NPC data: {e}")
            
        return {}
