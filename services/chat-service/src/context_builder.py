import logging
from typing import List, Dict, Any, Optional
import json
import re

logger = logging.getLogger(__name__)

class ContextBuilder:
    """Converts Life Strand data to optimized prompts"""
    
    def __init__(self):
        self.max_context_length = 8192  # Default context window
        self.system_prompt_max = 2048
        self.conversation_history_max = 4096
        self.knowledge_max = 2048
        
    def build_system_prompt(self, life_strand: dict) -> str:
        """Create system prompt from NPC personality"""
        try:
            if not life_strand:
                return "You are a helpful AI assistant."
                
            # Extract core personality components
            name = life_strand.get("name", "Unknown")
            background = life_strand.get("background", {})
            personality = life_strand.get("personality", {})
            current_status = life_strand.get("current_status", {})
            
            # Build system prompt sections
            prompt_parts = []
            
            # Character introduction
            prompt_parts.append(f"You are {name}, a character in a dynamic world.")
            
            # Background information
            if background:
                age = background.get("age")
                occupation = background.get("occupation")
                location = background.get("location")
                
                bg_parts = []
                if age:
                    bg_parts.append(f"You are {age} years old")
                if occupation:
                    bg_parts.append(f"working as {occupation}")
                if location:
                    bg_parts.append(f"currently in {location}")
                    
                if bg_parts:
                    prompt_parts.append(". ".join(bg_parts) + ".")
                    
            # Personality traits
            if personality:
                traits = personality.get("traits", [])
                motivations = personality.get("motivations", [])
                fears = personality.get("fears", [])
                
                if traits:
                    trait_text = ", ".join(traits[:5])  # Limit to top 5 traits
                    prompt_parts.append(f"Your personality is characterized by being {trait_text}.")
                    
                if motivations:
                    motivation_text = "; ".join(motivations[:3])
                    prompt_parts.append(f"You are motivated by: {motivation_text}.")
                    
                if fears:
                    fear_text = "; ".join(fears[:2])
                    prompt_parts.append(f"You have concerns about: {fear_text}.")
                    
            # Current emotional/physical state
            if current_status:
                mood = current_status.get("mood")
                health = current_status.get("health")
                energy = current_status.get("energy")
                
                status_parts = []
                if mood:
                    status_parts.append(f"feeling {mood}")
                if health and health != "normal":
                    status_parts.append(f"health is {health}")
                if energy and energy != "normal":
                    status_parts.append(f"energy level is {energy}")
                    
                if status_parts:
                    prompt_parts.append(f"Currently, you are {', '.join(status_parts)}.")
                    
            # Behavioral guidelines
            prompt_parts.append(
                "Respond naturally as this character would, staying true to your personality, "
                "background, and current state. Keep responses conversational and in-character."
            )
            
            system_prompt = " ".join(prompt_parts)
            
            # Ensure it fits within token limit
            system_prompt = self.optimize_for_token_limit(system_prompt, self.system_prompt_max)
            
            logger.debug(f"Built system prompt for {name}: {len(system_prompt)} characters")
            return system_prompt
            
        except Exception as e:
            logger.error(f"Error building system prompt: {e}")
            return "You are a helpful AI assistant."
            
    def build_conversation_context(self, life_strand: dict, history: List[Dict[str, Any]]) -> str:
        """Include relevant memories and relationships"""
        try:
            context_parts = []
            
            # Add relevant knowledge/memories
            knowledge_context = self.extract_relevant_knowledge(life_strand, history)
            if knowledge_context:
                context_parts.extend(knowledge_context)
                
            # Add relationship context
            relationships = life_strand.get("relationships", {})
            if relationships:
                rel_context = self._build_relationship_context(relationships, history)
                if rel_context:
                    context_parts.append(rel_context)
                    
            # Add recent memories
            memories = life_strand.get("memories", [])
            if memories:
                memory_context = self._build_memory_context(memories, limit=3)
                if memory_context:
                    context_parts.append(memory_context)
                    
            # Add conversation history
            if history:
                history_context = self._format_conversation_history(history)
                context_parts.append(history_context)
                
            full_context = "\n\n".join(context_parts)
            
            # Optimize for token limit
            full_context = self.optimize_for_token_limit(
                full_context, 
                self.max_context_length - self.system_prompt_max
            )
            
            return full_context
            
        except Exception as e:
            logger.error(f"Error building conversation context: {e}")
            return ""
            
    def optimize_for_token_limit(self, context: str, limit: int) -> str:
        """Intelligently truncate context to fit token limits"""
        try:
            # Rough token estimation: 4 characters per token
            estimated_tokens = len(context) // 4
            
            if estimated_tokens <= limit:
                return context
                
            # Calculate target character length
            target_chars = limit * 4
            
            # Try to truncate intelligently at sentence boundaries
            sentences = re.split(r'(?<=[.!?])\s+', context)
            
            truncated = []
            char_count = 0
            
            for sentence in sentences:
                if char_count + len(sentence) > target_chars:
                    break
                truncated.append(sentence)
                char_count += len(sentence) + 1  # +1 for space
                
            result = " ".join(truncated)
            
            # If still too long, do hard truncation
            if len(result) > target_chars:
                result = result[:target_chars].rsplit(' ', 1)[0]  # Truncate at word boundary
                
            logger.debug(f"Optimized context: {len(context)} -> {len(result)} chars")
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing context: {e}")
            return context[:limit * 4] if limit * 4 < len(context) else context
            
    def extract_relevant_knowledge(self, life_strand: dict, query_history: List[Dict[str, Any]]) -> List[str]:
        """RAG-style retrieval of relevant NPC knowledge"""
        try:
            knowledge = life_strand.get("knowledge", [])
            if not knowledge or not query_history:
                return []
                
            # Get recent user messages for relevance scoring
            recent_messages = [
                msg["content"] for msg in query_history[-5:] 
                if msg.get("role") == "user"
            ]
            
            if not recent_messages:
                return []
                
            recent_text = " ".join(recent_messages).lower()
            
            # Score knowledge items by relevance
            scored_knowledge = []
            for item in knowledge:
                if isinstance(item, dict):
                    content = item.get("content", "")
                    topic = item.get("topic", "")
                    text_to_score = f"{topic} {content}".lower()
                else:
                    text_to_score = str(item).lower()
                    content = str(item)
                    
                # Simple relevance scoring based on word overlap
                score = self._calculate_relevance_score(recent_text, text_to_score)
                if score > 0.1:  # Threshold for relevance
                    scored_knowledge.append((score, content))
                    
            # Sort by relevance and take top items
            scored_knowledge.sort(reverse=True)
            
            relevant_items = []
            for score, content in scored_knowledge[:3]:  # Top 3 relevant items
                if isinstance(content, str) and len(content.strip()) > 0:
                    relevant_items.append(f"Relevant knowledge: {content}")
                    
            return relevant_items
            
        except Exception as e:
            logger.error(f"Error extracting relevant knowledge: {e}")
            return []
            
    def _calculate_relevance_score(self, query_text: str, knowledge_text: str) -> float:
        """Simple relevance scoring based on word overlap"""
        try:
            query_words = set(re.findall(r'\b\w+\b', query_text.lower()))
            knowledge_words = set(re.findall(r'\b\w+\b', knowledge_text.lower()))
            
            if not query_words or not knowledge_words:
                return 0.0
                
            intersection = query_words & knowledge_words
            union = query_words | knowledge_words
            
            # Jaccard similarity
            return len(intersection) / len(union) if union else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating relevance score: {e}")
            return 0.0
            
    def _build_relationship_context(self, relationships: dict, history: List[Dict[str, Any]]) -> str:
        """Build context about relevant relationships"""
        try:
            # Extract any mentioned names from conversation
            mentioned_names = set()
            for msg in history:
                content = msg.get("content", "")
                # Simple name extraction - look for capitalized words
                names = re.findall(r'\b[A-Z][a-z]+\b', content)
                mentioned_names.update(names)
                
            relevant_relationships = []
            for name, relationship in relationships.items():
                if name in mentioned_names or len(relevant_relationships) < 2:
                    if isinstance(relationship, dict):
                        rel_type = relationship.get("type", "acquaintance")
                        status = relationship.get("status", "neutral")
                        notes = relationship.get("notes", "")
                        
                        rel_desc = f"{name} ({rel_type}, {status})"
                        if notes:
                            rel_desc += f": {notes}"
                        relevant_relationships.append(rel_desc)
                    else:
                        relevant_relationships.append(f"{name}: {relationship}")
                        
            if relevant_relationships:
                return f"Relationships: {'; '.join(relevant_relationships)}"
                
            return ""
            
        except Exception as e:
            logger.error(f"Error building relationship context: {e}")
            return ""
            
    def _build_memory_context(self, memories: List[Dict[str, Any]], limit: int = 3) -> str:
        """Build context from recent or important memories"""
        try:
            if not memories:
                return ""
                
            # Sort memories by importance and recency
            sorted_memories = sorted(
                memories,
                key=lambda m: (
                    m.get("importance", 0),
                    m.get("timestamp", "")
                ),
                reverse=True
            )
            
            memory_texts = []
            for memory in sorted_memories[:limit]:
                if isinstance(memory, dict):
                    content = memory.get("content", "")
                    if content:
                        memory_texts.append(content)
                else:
                    memory_texts.append(str(memory))
                    
            if memory_texts:
                return f"Recent memories: {'; '.join(memory_texts)}"
                
            return ""
            
        except Exception as e:
            logger.error(f"Error building memory context: {e}")
            return ""
            
    def _format_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        """Format conversation history for context"""
        try:
            if not history:
                return ""
                
            # Take recent messages, prioritizing the most recent
            recent_history = history[-10:]  # Last 10 messages
            
            formatted_messages = []
            for msg in recent_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                
                if role == "user":
                    formatted_messages.append(f"User: {content}")
                elif role == "assistant":
                    formatted_messages.append(f"You: {content}")
                    
            if formatted_messages:
                return "\n".join(formatted_messages)
                
            return ""
            
        except Exception as e:
            logger.error(f"Error formatting conversation history: {e}")
            return ""
            
    def validate_context_size(self, context: str, max_tokens: int) -> bool:
        """Validate that context fits within token limit"""
        try:
            estimated_tokens = len(context) // 4  # Rough estimation
            return estimated_tokens <= max_tokens
        except Exception:
            return False
            
    def get_context_stats(self, system_prompt: str, context: str) -> Dict[str, int]:
        """Get statistics about the built context"""
        try:
            return {
                "system_prompt_chars": len(system_prompt),
                "system_prompt_tokens_est": len(system_prompt) // 4,
                "context_chars": len(context),
                "context_tokens_est": len(context) // 4,
                "total_chars": len(system_prompt) + len(context),
                "total_tokens_est": (len(system_prompt) + len(context)) // 4
            }
        except Exception as e:
            logger.error(f"Error getting context stats: {e}")
            return {}