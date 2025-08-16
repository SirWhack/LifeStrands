import asyncio
import logging
import os
from typing import List, Optional
import aiohttp

logger = logging.getLogger(__name__)

class LocalEmbeddingManager:
    """Manages embedding generation using the model service"""
    
    def __init__(self):
        self.embedding_enabled = os.getenv('ENABLE_EMBEDDINGS', 'false').lower() == 'true'
        self.model_service_url = os.getenv('MODEL_SERVICE_URL', 'http://host.docker.internal:8001')
        self.embedding_dimensions = int(os.getenv('EMBEDDING_DIMENSIONS', '384'))
        self.session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize the HTTP session for model service communication"""
        if not self.embedding_enabled:
            logger.info("Embeddings are disabled, skipping initialization")
            return
            
        async with self._lock:
            if self.session is None:
                logger.info(f"Initializing embedding manager with model service: {self.model_service_url}")
                try:
                    # Create HTTP session without testing (embeddings disabled)
                    self.session = aiohttp.ClientSession()
                    logger.info("Embedding manager initialized (embeddings disabled)")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize embedding manager: {e}")
                    if self.session:
                        await self.session.close()
                        self.session = None
                    raise
                    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text"""
        if not self.embedding_enabled:
            logger.debug("Embeddings disabled, returning dummy embedding")
            # Return a dummy embedding vector
            return [0.0] * self.embedding_dimensions
            
        if self.session is None:
            await self.initialize()
            
        try:
            # Clean and prepare text
            text = text.strip()
            if not text:
                raise ValueError("Text cannot be empty")
                
            # Call model service embedding endpoint
            async with self.session.post(
                f"{self.model_service_url}/embeddings",
                json={"texts": [text]},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Model service error {response.status}: {error_text}")
                
                result = await response.json()
                embeddings = result.get("embeddings", [])
                if not embeddings:
                    raise Exception("No embeddings returned from model service")
                    
                return embeddings[0]
            
        except Exception as e:
            logger.error(f"Failed to generate embedding for text: {e}")
            raise
            
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (more efficient)"""
        if self.session is None:
            await self.initialize()
            
        try:
            # Clean texts
            clean_texts = [text.strip() for text in texts if text.strip()]
            if not clean_texts:
                return []
                
            # Call model service embedding endpoint
            async with self.session.post(
                f"{self.model_service_url}/embeddings",
                json={"texts": clean_texts},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Model service error {response.status}: {error_text}")
                
                result = await response.json()
                embeddings = result.get("embeddings", [])
                if len(embeddings) != len(clean_texts):
                    raise Exception(f"Expected {len(clean_texts)} embeddings, got {len(embeddings)}")
                    
                return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise
            
    async def generate_npc_embedding(self, npc_data: dict) -> List[float]:
        """Generate comprehensive embedding for NPC personality and background"""
        try:
            # Extract relevant text fields for embedding
            text_components = []
            
            # Background information
            background = npc_data.get('background', {})
            if background.get('occupation'):
                text_components.append(f"Occupation: {background['occupation']}")
            if background.get('personality_summary'):
                text_components.append(f"Personality: {background['personality_summary']}")
            if background.get('history'):
                text_components.append(f"History: {background['history']}")
            if background.get('education'):
                text_components.append(f"Education: {background['education']}")
                
            # Personality traits
            personality = npc_data.get('personality', {})
            if personality.get('traits'):
                traits_text = ', '.join(personality['traits'])
                text_components.append(f"Traits: {traits_text}")
            if personality.get('motivations'):
                motivations_text = ', '.join(personality['motivations'])
                text_components.append(f"Motivations: {motivations_text}")
            if personality.get('values'):
                values_text = ', '.join(personality['values'])
                text_components.append(f"Values: {values_text}")
                
            # Current status
            status = npc_data.get('current_status', {})
            if status.get('location'):
                text_components.append(f"Location: {status['location']}")
            if status.get('current_activity'):
                text_components.append(f"Activity: {status['current_activity']}")
                
            # Combine all components
            combined_text = ' | '.join(text_components)
            
            if not combined_text:
                raise ValueError("No valid text found for NPC embedding generation")
                
            return await self.generate_embedding(combined_text)
            
        except Exception as e:
            logger.error(f"Failed to generate NPC embedding: {e}")
            raise
            
    def get_embedding_dimensions(self) -> int:
        """Get the embedding dimensions for this model"""
        return self.embedding_dimensions
        
    def get_model_info(self) -> dict:
        """Get information about the current model"""
        return {
            'model_service_url': self.model_service_url,
            'dimensions': self.embedding_dimensions,
            'is_initialized': self.session is not None
        }
        
    async def shutdown(self):
        """Clean shutdown of embedding manager"""
        async with self._lock:
            if self.session is not None:
                await self.session.close()
                self.session = None
                logger.info("Embedding manager shutdown completed")

# Global instance
embedding_manager = LocalEmbeddingManager()